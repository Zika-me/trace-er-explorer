#!/usr/bin/env python3
"""
src/ingest/fetch_padep_wells.py

Downloads PA DEP Oil & Gas Well Locations (Conventional + Unconventional) from
PASDA and joins county-level well-density risk indicators to the master index.

Source:   Pennsylvania Department of Environmental Protection via PASDA
Data URL: https://www.pasda.psu.edu/spreadsheet/OilGasLocations_ConventionalUnconventional2025_09.csv
Entry:    https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=1088
Scope:    https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports

Dataset: all PA oil & gas wells with DEP location data — 222,000+ records
(conventional + unconventional) updated September 2025.

Join strategy: county-level aggregation. Well coordinates are available but
222k+ wells are contextual risk indicators for the county, not facility-level
links to master-index entities. County-level join is consistent with PHMSA
and TCEQ treatments and is more defensible for a risk screening tool.

Outputs:
    data/raw/padep/OilGasLocations_ConventionalUnconventional2025_09.csv
    data/interim/padep_wells.csv
    data/processed/padep_county_features.csv
    data/processed/master_facility_index_with_padep_features.csv
    validation/source_volume_log.csv  (appended)
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

# URL pattern: PASDA updates monthly; 2025_09 is the Sept 2025 release
CSV_URL      = (
    "https://www.pasda.psu.edu/spreadsheet/"
    "OilGasLocations_ConventionalUnconventional2025_09.csv"
)
RAW_DIR      = DATA_DIR / "raw" / "padep"
RAW_FILE     = RAW_DIR / "OilGasLocations_ConventionalUnconventional2025_09.csv"
INTERIM_OUT  = DATA_DIR / "interim"  / "padep_wells.csv"
COUNTY_OUT   = DATA_DIR / "processed" / "padep_county_features.csv"
MASTER_IN    = DATA_DIR / "processed" / "master_facility_index_with_tceq_features.csv"
MASTER_OUT   = DATA_DIR / "processed" / "master_facility_index_with_padep_features.csv"
VOL_LOG      = BASE_DIR / "validation" / "source_volume_log.csv"

HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Analysis period for "recent activity" flag
RECENT_YEAR_MIN = 2019
RECENT_YEAR_MAX = 2025

# WELL_STATU substrings that indicate plugged or abandoned wells
INACTIVE_STATUS_SUBSTRINGS = {"plug", "abandon", "inactive"}

# WELL_TYPE values to count as gas wells (WELL_TYPE column is truncated to 9 chars)
GAS_TYPE_SUBSTRINGS = {"gas", "coalbed", "methane"}

_COUNTY_SUFFIXES = [" COUNTY", " PARISH", " BOROUGH"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)



def normalize_county(name: object) -> str:
    if pd.isna(name) or str(name).strip() in {"", "nan"}:
        return ""
    s = str(name).upper().strip()
    for suffix in _COUNTY_SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s.replace("-", " ").strip()


def download_csv(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and not force:
        log.info("CSV already cached: %s (%.1f MB)", RAW_FILE, RAW_FILE.stat().st_size / 1e6)
        return RAW_FILE
    log.info("Downloading PA DEP well locations from %s", CSV_URL)
    r = requests.get(CSV_URL, headers=HDR, timeout=300, stream=True)
    r.raise_for_status()
    total = 0
    with open(RAW_FILE, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
            total += len(chunk)
    log.info("Downloaded %.1f MB → %s", total / 1e6, RAW_FILE)
    return RAW_FILE


def parse_wells(path: Path) -> pd.DataFrame:
    log.info("Reading %s...", path.name)
    df = pd.read_csv(path, dtype=str, low_memory=False)
    log.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    # Normalise column names: strip whitespace
    df.columns = [c.strip() for c in df.columns]

    # --- Status: active vs. inactive ---
    status = df["WELL_STATU"].fillna("").str.lower()
    df["is_active"] = ~status.str.contains("|".join(INACTIVE_STATUS_SUBSTRINGS), na=False)

    # --- Well type flags ---
    wtype = df["WELL_TYPE"].fillna("").str.lower()
    df["is_oil"]           = wtype.str.contains("oil", na=False)
    df["is_gas"]           = wtype.str.contains("|".join(GAS_TYPE_SUBSTRINGS), na=False)
    df["is_unconventional"] = df["UNCONVENTI"].fillna("N").str.upper() == "Y"

    # --- Permit year ---
    df["permit_year"] = pd.to_datetime(df["PERMIT_DAT"], errors="coerce").dt.year
    df["is_recent"]   = df["permit_year"].between(RECENT_YEAR_MIN, RECENT_YEAR_MAX)

    # --- County ---
    df["county_norm"] = df["COUNTY"].apply(normalize_county)
    df["state"]       = "PA"

    # Keep a lean interim file (not all 43 columns)
    keep = [
        "PERMIT_NUM", "WELL_NAME", "OPERATOR", "WELL_TYPE", "WELL_STATU",
        "PERMIT_DAT", "SPUD_DATE", "COUNTY", "county_norm", "state",
        "LATITUDE", "LONGITUDE", "UNCONVENTI",
        "is_active", "is_oil", "is_gas", "is_unconventional", "is_recent",
        "permit_year",
    ]
    return df[[c for c in keep if c in df.columns]].copy()


def aggregate_to_county(wells: pd.DataFrame) -> pd.DataFrame:
    """One row per county with well-density risk indicators."""
    grp = wells.groupby("county_norm", sort=True)

    agg = grp.agg(
        padep_total_wells=("PERMIT_NUM", "count"),
        padep_most_recent_permit_year=("permit_year", "max"),
    ).reset_index()

    def county_flag(mask: pd.Series, col_name: str) -> pd.DataFrame:
        sub = wells[mask].groupby("county_norm").size().reset_index(name=col_name)
        return sub

    for mask, col in [
        (wells["is_active"],          "padep_active_wells"),
        (~wells["is_active"],         "padep_plugged_abandoned_wells"),
        (wells["is_unconventional"],  "padep_unconventional_wells"),
        (wells["is_oil"],             "padep_oil_wells"),
        (wells["is_gas"],             "padep_gas_wells"),
        (wells["is_recent"],          "padep_recent_permit_count"),
    ]:
        sub = county_flag(mask, col)
        agg = agg.merge(sub, on="county_norm", how="left")
        agg[col] = agg[col].fillna(0).astype(int)

    agg["state"] = "PA"
    agg["has_padep_well_data"] = True

    log.info(
        "County features: %d PA counties  |  active wells: %d  |  "
        "unconventional: %d  |  recent permits (2019-2025): %d",
        len(agg),
        int(agg["padep_active_wells"].sum()),
        int(agg["padep_unconventional_wells"].sum()),
        int(agg["padep_recent_permit_count"].sum()),
    )
    return agg


def join_to_master(
    county_features: pd.DataFrame,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    master = master.copy()
    master["_county_norm"] = master["county"].apply(normalize_county)
    master["_state"]       = master["state"].str.strip().str.upper()

    feat = county_features.rename(columns={
        "county_norm": "_county_norm",
        "state":       "_state",
    })

    master_out = master.merge(feat, on=["_state", "_county_norm"], how="left")
    master_out = master_out.drop(columns=["_county_norm", "_state"])
    master_out["has_padep_well_data"] = master_out["has_padep_well_data"].fillna(False)

    matched = int(master_out["has_padep_well_data"].sum())
    assert len(master_out) == len(master), (
        f"Row count changed: {len(master)} → {len(master_out)}"
    )

    stats = {
        "padep_total_well_rows": None,   # filled by caller
        "padep_counties_covered": len(county_features),
        "master_rows_with_padep_data": matched,
    }
    return master_out, stats


def append_volume_log(total_rows: int, stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "padep_oil_gas_wells",
        "row_count": total_rows,
        "notes": (
            f"release=2025_09; conventional+unconventional; "
            f"pa_counties={stats['padep_counties_covered']}; "
            f"master_rows_with_padep={stats['master_rows_with_padep_data']}"
        ),
    }
    with open(VOL_LOG, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    log.info("Logged volume entry → %s", VOL_LOG)


def main() -> None:
    # 1. Download
    raw_path = download_csv(force=False)

    # 2. Parse
    wells = parse_wells(raw_path)
    active_ct = wells["is_active"].sum()
    uncv_ct   = wells["is_unconventional"].sum()
    recent_ct = wells["is_recent"].sum()
    log.info(
        "Wells: %d total  |  %d active  |  %d unconventional  |  %d recent permits",
        len(wells), active_ct, uncv_ct, recent_ct,
    )

    # 3. Save interim
    DATA_DIR.joinpath("interim").mkdir(parents=True, exist_ok=True)
    wells.to_csv(INTERIM_OUT, index=False)
    log.info("Wrote %d well rows → %s", len(wells), INTERIM_OUT)

    # 4. County aggregation
    county_features = aggregate_to_county(wells)
    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    county_features.to_csv(COUNTY_OUT, index=False)
    log.info("Wrote %d county feature rows → %s", len(county_features), COUNTY_OUT)

    # 5. Join to master
    log.info("Loading master index: %s", MASTER_IN)
    master = pd.read_csv(MASTER_IN, dtype=str)
    log.info("  %d rows  |  %d columns", len(master), len(master.columns))

    master_out, stats = join_to_master(county_features, master)
    stats["padep_total_well_rows"] = len(wells)

    master_out.to_csv(MASTER_OUT, index=False)
    log.info(
        "Wrote extended master index: %d rows  |  %d columns → %s",
        len(master_out), len(master_out.columns), MASTER_OUT,
    )

    append_volume_log(len(wells), stats)

    log.info("Done. Summary:")
    log.info("  PA DEP well rows:                %d", len(wells))
    log.info("  Active wells:                    %d", active_ct)
    log.info("  Unconventional wells:            %d", uncv_ct)
    log.info("  Recent permits (2019-2025):      %d", recent_ct)
    log.info("  PA counties with well data:      %d", stats["padep_counties_covered"])
    log.info("  Master rows with PA DEP data:    %d", stats["master_rows_with_padep_data"])
    log.info("  Master column count:             %d", len(master_out.columns))


if __name__ == "__main__":
    main()