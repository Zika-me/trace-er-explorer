#!/usr/bin/env python3
"""
src/ingest/fetch_nmocd_wells.py

Fetches New Mexico OCD oil and gas well data via the UNM NHNM ArcGIS REST
API (the publicly accessible mirror of OCD's permitting database) and joins
county-level well-density risk indicators to the master index.

Source:   NM OCD via UNM New Mexico Heritage Network / NMEDB
API:      https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/ActiveOilandGasWells/MapServer/3
Scope:    https://www.emnrd.nm.gov/ocd/ocd-data/

55,572 wells (all statuses: active, plugged, abandoned) as of the query date.
Paginated at 1,000 records per request (server MaxRecordCount).

Join strategy: county-level aggregation, consistent with PHMSA and PA DEP.
Wells provide contextual risk density — every master-index NM facility in a
county inherits that county's well activity indicators.

Note: OCD's FTP server is not publicly accessible over HTTPS; this ArcGIS
endpoint is the documented public-access substitute.

Outputs:
    data/raw/nmocd/nmocd_wells.json              cached raw pages
    data/interim/nmocd_wells.csv                 one row per well
    data/processed/nmocd_county_features.csv     one row per county
    data/processed/master_facility_index_with_nmocd_features.csv
    validation/source_volume_log.csv             appended
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

API_BASE     = (
    "https://nhnm-gisweb.unm.edu/arcgis/rest/services/"
    "NMEDB/ActiveOilandGasWells/MapServer/3"
)
RAW_DIR      = DATA_DIR / "raw" / "nmocd"
RAW_CACHE    = RAW_DIR / "nmocd_wells.jsonl"
INTERIM_OUT  = DATA_DIR / "interim"  / "nmocd_wells.csv"
COUNTY_OUT   = DATA_DIR / "processed" / "nmocd_county_features.csv"
MASTER_IN    = DATA_DIR / "processed" / "master_facility_index_with_padep_features.csv"
MASTER_OUT   = DATA_DIR / "processed" / "master_facility_index_with_nmocd_features.csv"
VOL_LOG      = BASE_DIR / "validation" / "source_volume_log.csv"

HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

PAGE_SIZE       = 1000
REQUEST_DELAY_S = 1.5          # polite pause between pages
MAX_RETRIES     = 4               # per-page retry attempts
BACKOFF_BASE_S  = 3               # seconds; doubles on each retry
RECENT_MIN      = 2019
RECENT_MAX      = 2025

_COUNTY_SUFFIXES = [" COUNTY", " PARISH", " BOROUGH"]

OUT_FIELDS = (
    "id,name,type,status,county,county_code,district,"
    "latitude,longitude,year_spudded,last_production_date,plug_date"
)

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



def _fetch_page(offset: int) -> list[dict]:
    """Fetch one page with retry + exponential backoff."""
    params = {
        "where":             "1=1",
        "outFields":         OUT_FIELDS,
        "returnGeometry":    "false",
        "resultOffset":      offset,
        "resultRecordCount": PAGE_SIZE,
        "f":                 "json",
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                f"{API_BASE}/query", params=params, headers=HDR, timeout=90
            )
            resp.raise_for_status()
            data = resp.json()
            return [feat["attributes"] for feat in data.get("features", [])]
        except Exception as exc:
            wait = BACKOFF_BASE_S * (2 ** attempt)
            if attempt < MAX_RETRIES - 1:
                log.warning(
                    "  Page at offset=%d failed (attempt %d/%d): %s — retrying in %ds",
                    offset, attempt + 1, MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Page at offset={offset} failed after {MAX_RETRIES} attempts: {exc}"
                ) from exc
    return []


def fetch_all_wells(force: bool = False) -> list[dict]:
    """
    Fetch all wells with per-page retry and incremental JSONL caching so
    a restart resumes from the last successfully saved offset.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Resume: count already-saved lines
    resume_offset = 0
    all_features: list[dict] = []
    if RAW_CACHE.exists() and not force:
        with open(RAW_CACHE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_features.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        resume_offset = (len(all_features) // PAGE_SIZE) * PAGE_SIZE
        if all_features:
            log.info(
                "Resuming from offset=%d (%d records already cached)",
                resume_offset, len(all_features),
            )

    if resume_offset == 0 and not all_features:
        log.info("Fetching NM OCD wells from ArcGIS REST API (paginated)...")

    # Get total count
    r = requests.get(
        f"{API_BASE}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        headers=HDR, timeout=30,
    )
    r.raise_for_status()
    total = r.json().get("count", 0)
    log.info("Total wells reported by API: %d  |  Resuming at offset: %d", total, resume_offset)

    offset = resume_offset
    page = resume_offset // PAGE_SIZE

    # Open cache in append mode (resume adds new lines; fresh start truncates)
    cache_mode = "a" if resume_offset > 0 else "w"
    with open(RAW_CACHE, cache_mode) as cache_fh:
        while True:
            page += 1
            features = _fetch_page(offset)
            if not features:
                break

            all_features.extend(features)
            for feat in features:
                cache_fh.write(json.dumps(feat) + "\n")
            cache_fh.flush()

            log.info(
                "  Page %d: offset=%d  got=%d  running_total=%d",
                page, offset, len(features), len(all_features),
            )

            if len(features) < PAGE_SIZE:
                break   # last page

            offset += PAGE_SIZE
            time.sleep(REQUEST_DELAY_S)

    log.info("Fetched %d wells total across %d pages", len(all_features), page)
    return all_features



def parse_wells(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw)
    log.info("Loaded %d rows from raw data", len(df))

    # County normalisation
    df["county_norm"] = df["county"].apply(normalize_county)
    df["state"] = "NM"

    # Active status
    status_lower = df["status"].fillna("").str.lower()
    df["is_active"] = ~status_lower.str.contains("plug|abandon|cancel|inject", na=False)

    # Well type
    type_lower = df["type"].fillna("").str.lower()
    df["is_gas"]  = type_lower.str.contains("gas|coalbed|methane|co2", na=False)
    df["is_oil"]  = type_lower.str.contains("oil", na=False)

    # Spud year — stored as string; coerce to int
    df["year_spudded_int"] = pd.to_numeric(df["year_spudded"], errors="coerce")
    df["is_recent"] = df["year_spudded_int"].between(RECENT_MIN, RECENT_MAX)

    # Last production date — ArcGIS epoch ms; sentinel 253402239599000 ≈ year 9999 → null
    def safe_year(ms):
        if pd.isna(ms) or ms > 4_000_000_000_000:   # > year 2096 → sentinel
            return None
        try:
            return datetime.utcfromtimestamp(ms / 1000).year
        except Exception:
            return None

    df["last_prod_year"] = df["last_production_date"].apply(safe_year)

    log.info(
        "Wells: %d total  |  %d active  |  %d gas  |  %d oil  |  %d recent spud",
        len(df),
        df["is_active"].sum(),
        df["is_gas"].sum(),
        df["is_oil"].sum(),
        df["is_recent"].sum(),
    )
    return df



def aggregate_to_county(wells: pd.DataFrame) -> pd.DataFrame:
    grp = wells.groupby("county_norm", sort=True)

    agg = grp.agg(
        nmocd_total_wells=("id", "count"),
        nmocd_most_recent_spud_year=("year_spudded_int", "max"),
        nmocd_most_recent_prod_year=("last_prod_year", "max"),
    ).reset_index()

    def sub_count(mask: pd.Series, col: str) -> pd.DataFrame:
        return wells[mask].groupby("county_norm").size().reset_index(name=col)

    for mask, col in [
        (wells["is_active"],  "nmocd_active_wells"),
        (~wells["is_active"], "nmocd_plugged_abandoned_wells"),
        (wells["is_gas"],     "nmocd_gas_wells"),
        (wells["is_oil"],     "nmocd_oil_wells"),
        (wells["is_recent"],  "nmocd_recent_spud_count"),
    ]:
        sub = sub_count(mask, col)
        agg = agg.merge(sub, on="county_norm", how="left")
        agg[col] = agg[col].fillna(0).astype(int)

    agg["state"] = "NM"
    agg["has_nmocd_well_data"] = True

    log.info(
        "County features: %d NM counties  |  active: %d  |  recent spud: %d",
        len(agg),
        int(agg["nmocd_active_wells"].sum()),
        int(agg["nmocd_recent_spud_count"].sum()),
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
    master_out["has_nmocd_well_data"] = (
        master_out["has_nmocd_well_data"].fillna(False)
    )

    matched = int(master_out["has_nmocd_well_data"].sum())
    assert len(master_out) == len(master), (
        f"Row count changed: {len(master)} → {len(master_out)}"
    )

    stats = {
        "nmocd_total_well_rows":      None,
        "nmocd_counties_covered":     len(county_features),
        "master_rows_with_nmocd":     matched,
    }
    return master_out, stats



def append_volume_log(total: int, stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "nmocd_oil_gas_wells",
        "row_count": total,
        "notes": (
            f"source=UNM-NHNM-ArcGIS; "
            f"nm_counties={stats['nmocd_counties_covered']}; "
            f"master_rows_with_nmocd={stats['master_rows_with_nmocd']}"
        ),
    }
    with open(VOL_LOG, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    log.info("Logged volume entry → %s", VOL_LOG)



def main() -> None:
    # 1. Fetch
    raw = fetch_all_wells(force=False)

    # 2. Parse
    wells = parse_wells(raw)
    DATA_DIR.joinpath("interim").mkdir(parents=True, exist_ok=True)
    wells.to_csv(INTERIM_OUT, index=False)
    log.info("Wrote %d well rows → %s", len(wells), INTERIM_OUT)

    # 3. County aggregation
    county_features = aggregate_to_county(wells)
    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    county_features.to_csv(COUNTY_OUT, index=False)
    log.info("Wrote %d county rows → %s", len(county_features), COUNTY_OUT)

    # 4. Join to master
    log.info("Loading master index: %s", MASTER_IN)
    master = pd.read_csv(MASTER_IN, dtype=str)
    log.info("  %d rows  |  %d columns", len(master), len(master.columns))

    master_out, stats = join_to_master(county_features, master)
    stats["nmocd_total_well_rows"] = len(wells)

    master_out.to_csv(MASTER_OUT, index=False)
    log.info(
        "Wrote extended master index: %d rows  |  %d columns → %s",
        len(master_out), len(master_out.columns), MASTER_OUT,
    )

    append_volume_log(len(wells), stats)

    log.info("Done. Summary:")
    log.info("  NM OCD well rows:                %d", len(wells))
    log.info("  Active wells:                    %d", wells["is_active"].sum())
    log.info("  Recent spud (2019-2025):         %d", wells["is_recent"].sum())
    log.info("  NM counties covered:             %d", stats["nmocd_counties_covered"])
    log.info("  Master rows with NM OCD data:   %d", stats["master_rows_with_nmocd"])
    log.info("  Master column count:             %d", len(master_out.columns))


if __name__ == "__main__":
    main()