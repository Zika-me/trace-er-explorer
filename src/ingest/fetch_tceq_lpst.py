#!/usr/bin/env python3
"""
src/ingest/fetch_tceq_lpst.py

Downloads TCEQ Leaking Petroleum Storage Tank (LPST) site data from
TCEQ's own public server and joins to the master facility index.

Source:   TCEQ Office of Waste, Remediation Division
Data URL: https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt
Entry:    https://www.tceq.texas.gov/agency/data/lookup-data/pst-datasets-records.html
Scope:    https://www.tceq.texas.gov/agency/data/lookup-data/download-data.html

LPST sites are fixed contamination points, not time-series events.
Unlike pipeline incident data (filtered to 2019-2024), ALL LPST records
are included: an active site from 1985 poses current risk just as much
as one opened in 2022. Status code 6A = case closed; all other codes
indicate active or in-progress corrective action.

Join strategy: county-level. LPST records carry county name (field 21)
but no lat/lon coordinates. Every master-index facility in a county
inherits that county's LPST contamination burden indicators.

Inputs:
    data/processed/master_facility_index_with_phmsa_features.csv

Outputs:
    data/raw/tceq/lpst.txt                        cached raw download
    data/interim/tceq_lpst_sites.csv              one row per LPST case
    data/processed/tceq_lpst_county_features.csv  one row per county
    data/processed/master_facility_index_with_tceq_features.csv
    validation/source_volume_log.csv              appended
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

LPST_URL    = "https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt"
RAW_DIR     = DATA_DIR / "raw" / "tceq"
RAW_FILE    = RAW_DIR / "lpst.txt"
INTERIM_OUT = DATA_DIR / "interim" / "tceq_lpst_sites.csv"
COUNTY_OUT  = DATA_DIR / "processed" / "tceq_lpst_county_features.csv"
MASTER_IN   = DATA_DIR / "processed" / "master_facility_index_with_phmsa_features.csv"
MASTER_OUT  = DATA_DIR / "processed" / "master_facility_index_with_tceq_features.csv"
VOL_LOG     = BASE_DIR / "validation" / "source_volume_log.csv"

HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# STAT-CD values that mean "case closed / no further action required"
CLOSED_STATUS_CODES = {"6A", "6B", "6C", "6D", "6E", "6F", "6G", "6H", "NFA"}

# Field positions (1-indexed, per lpst_readme.txt)
# There are 25 documented fields; the file may have additional undocumented
# trailing fields which are read but ignored.
FIELD_NAMES = [
    "lpst_id",        # 1  LPST-ID
    "reported_date",  # 2  REPORTED
    "entered_date",   # 3  ENTERED
    "priority_code",  # 4  PRIO-CD
    "status_code",    # 5  STAT-CD
    "primcoor",       # 6  PRIMCOOR
    "rprcoord",       # 7  RPRCOORD
    "pstcoord",       # 8  PSTCOORD
    "prp_name",       # 9  PRP-NAME
    "prp_city",       # 10 PRP-CITY
    "prp_state",      # 11 PRPSTATE
    "prp_zip1",       # 12 PRP-ZIP1
    "prp_zip2",       # 13 PRP-ZIP2
    "fac_id",         # 14 FAC-ID
    "fac_name",       # 15 FAC-NAME
    "fac_loc",        # 16 FAC-LOC
    "fac_city",       # 17 FAC-CITY
    "fac_zip1",       # 18 FAC-ZIP1
    "fac_zip2",       # 19 FAC-ZIP2
    "cnty_cd",        # 20 CNTY-CD
    "county",         # 21 COUNTY       ← join key to master index
    "region",         # 22 REGION
    "region_city",    # 23 REGION CITY
    "prp_address",    # 24 PRP-ADDRESS
    "prp_contact",    # 25 PRP-CONTACT
]

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


def download_lpst(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and not force:
        log.info("LPST file already cached: %s", RAW_FILE)
        return RAW_FILE
    log.info("Downloading LPST data from %s", LPST_URL)
    r = requests.get(LPST_URL, headers=HDR, timeout=120)
    r.raise_for_status()
    RAW_FILE.write_bytes(r.content)
    log.info("Downloaded %.2f MB → %s", len(r.content) / 1e6, RAW_FILE)
    return RAW_FILE


def parse_lpst(path: Path) -> pd.DataFrame:
    """
    Parse lpst.txt: comma-separated, caret (^) as quotechar.
    Returns one row per LPST case with standardised column names.
    """
    rows: list[dict] = []
    n_fields = len(FIELD_NAMES)
    skipped = 0

    with open(path, encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter=",", quotechar="^", skipinitialspace=True)
        for lineno, raw_row in enumerate(reader, start=1):
            if not raw_row:
                continue
            # Strip any stray whitespace from each cell
            row = [cell.strip() for cell in raw_row]
            if len(row) < 5:   # too few fields to be a real record
                skipped += 1
                continue
            record: dict = {}
            for i, name in enumerate(FIELD_NAMES):
                record[name] = row[i] if i < len(row) else ""
            rows.append(record)

    if skipped:
        log.warning("Skipped %d short/empty lines during parse.", skipped)

    df = pd.DataFrame(rows)
    log.info("Parsed %d LPST records from %s", len(df), path.name)

    # Add derived columns
    df["reported_date_parsed"] = pd.to_datetime(df["reported_date"], errors="coerce", format="%m/%d/%Y")
    df["reported_year"] = df["reported_date_parsed"].dt.year
    df["status_closed"] = df["status_code"].str.upper().isin(CLOSED_STATUS_CODES)
    df["county_norm"] = df["county"].apply(normalize_county)
    df["state"] = "TX"   # LPST is Texas-only

    return df


def aggregate_to_county(sites: pd.DataFrame) -> pd.DataFrame:
    """One row per county with LPST contamination-burden indicators."""
    active   = sites[~sites["status_closed"]]
    recent   = sites[sites["reported_year"].between(2019, 2025)]
    high_pri = sites[sites["priority_code"].str[:1].isin({"1", "2"})]

    agg = sites.groupby("county_norm", sort=True).agg(
        tceq_lpst_total_sites=("lpst_id", "count"),
        tceq_lpst_most_recent_reported_year=("reported_year", "max"),
    ).reset_index()

    # Active (not closed) sites
    act_agg = (
        active.groupby("county_norm")
        .agg(tceq_lpst_active_sites=("lpst_id", "count"))
        .reset_index()
    )
    agg = agg.merge(act_agg, on="county_norm", how="left")
    agg["tceq_lpst_active_sites"] = agg["tceq_lpst_active_sites"].fillna(0).astype(int)

    # Sites reported in the primary analysis window (2019-2025)
    rec_agg = (
        recent.groupby("county_norm")
        .agg(tceq_lpst_recent_sites_2019_2025=("lpst_id", "count"))
        .reset_index()
    )
    agg = agg.merge(rec_agg, on="county_norm", how="left")
    agg["tceq_lpst_recent_sites_2019_2025"] = (
        agg["tceq_lpst_recent_sites_2019_2025"].fillna(0).astype(int)
    )

    # High-priority sites (priority codes 1.x or 2.x)
    pri_agg = (
        high_pri.groupby("county_norm")
        .agg(tceq_lpst_high_priority_sites=("lpst_id", "count"))
        .reset_index()
    )
    agg = agg.merge(pri_agg, on="county_norm", how="left")
    agg["tceq_lpst_high_priority_sites"] = (
        agg["tceq_lpst_high_priority_sites"].fillna(0).astype(int)
    )

    agg["state"] = "TX"
    agg["has_tceq_lpst_data"] = True

    log.info(
        "County features: %d Texas counties with LPST data  |  "
        "active sites total: %d  |  recent (2019-2025): %d",
        len(agg),
        agg["tceq_lpst_active_sites"].sum(),
        agg["tceq_lpst_recent_sites_2019_2025"].sum(),
    )
    return agg


def join_to_master(
    county_features: pd.DataFrame,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    master = master.copy()
    master["_county_norm"] = master["county"].apply(normalize_county)
    master["_state"] = master["state"].str.strip().str.upper()

    feat = county_features.rename(columns={
        "county_norm": "_county_norm",
        "state":       "_state",
    })

    master_out = master.merge(feat, on=["_state", "_county_norm"], how="left")
    master_out = master_out.drop(columns=["_county_norm", "_state"])
    master_out["has_tceq_lpst_data"] = master_out["has_tceq_lpst_data"].fillna(False)

    matched = int(master_out["has_tceq_lpst_data"].sum())
    assert len(master_out) == len(master), (
        f"Row count changed: {len(master)} → {len(master_out)}"
    )

    stats = {
        "tceq_lpst_total_sites": None,    # filled by caller
        "tceq_counties_with_lpst_data": len(county_features),
        "master_rows_with_tceq_data": matched,
    }
    return master_out, stats


def append_volume_log(total_sites: int, stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "tceq_lpst_sites",
        "row_count": total_sites,
        "notes": (
            f"all_historical_records=True; "
            f"tx_counties_with_lpst={stats['tceq_counties_with_lpst_data']}; "
            f"master_rows_with_tceq={stats['master_rows_with_tceq_data']}"
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
    raw_path = download_lpst(force=False)

    # 2. Parse
    sites = parse_lpst(raw_path)
    closed_ct = sites["status_closed"].sum()
    active_ct = (~sites["status_closed"]).sum()
    log.info(
        "LPST sites: %d total  |  %d active  |  %d closed",
        len(sites), active_ct, closed_ct,
    )
    log.info(
        "Reported year range: %d – %d",
        int(sites["reported_year"].min()), int(sites["reported_year"].max()),
    )

    # 3. Save interim
    DATA_DIR.joinpath("interim").mkdir(parents=True, exist_ok=True)
    sites.to_csv(INTERIM_OUT, index=False)
    log.info("Wrote %d LPST site rows → %s", len(sites), INTERIM_OUT)

    # 4. County aggregation
    county_features = aggregate_to_county(sites)
    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    county_features.to_csv(COUNTY_OUT, index=False)
    log.info("Wrote %d county feature rows → %s", len(county_features), COUNTY_OUT)

    # 5. Join to master
    log.info("Loading master index: %s", MASTER_IN)
    master = pd.read_csv(MASTER_IN, dtype=str)
    log.info("  %d rows  |  %d columns", len(master), len(master.columns))

    master_out, stats = join_to_master(county_features, master)
    stats["tceq_lpst_total_sites"] = len(sites)

    master_out.to_csv(MASTER_OUT, index=False)
    log.info(
        "Wrote extended master index: %d rows  |  %d columns → %s",
        len(master_out), len(master_out.columns), MASTER_OUT,
    )

    append_volume_log(len(sites), stats)

    log.info("Done. Summary:")
    log.info("  LPST total sites:                %d", len(sites))
    log.info("  Active sites (not closed):       %d", active_ct)
    log.info("  TX counties with LPST data:      %d", stats["tceq_counties_with_lpst_data"])
    log.info("  Master rows with TCEQ data:      %d", stats["master_rows_with_tceq_data"])
    log.info("  Master column count:             %d", len(master_out.columns))


if __name__ == "__main__":
    main()