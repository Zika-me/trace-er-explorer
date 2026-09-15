"""
TRACE-ER Explorer — EPA FRS connector (facility master identity).

Downloads the EPA FRS "State Single File CSV" national product (one
flat CSV of facility name/address, geospatial, programs, NAICS/SIC for
every FRS facility), filters it to the project's target states, and
writes a standardized interim table for the master facility index.

  Landing page:    https://www.epa.gov/frs/epa-frs-facilities-state-single-file-csv-download
  Direct download: https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip

Usage:
    python src/ingest/fetch_frs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    append_source_volume_log,
    detect_column,
    discover_csv_files,
    download_file,
    logger,
    require_column,
    unzip_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw" / "frs"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
SOURCE_VOLUME_LOG = REPO_ROOT / "validation" / "source_volume_log.csv"

# Required three validation states plus the optional Maine case study.
TARGET_STATES = ["TX", "PA", "NM", "ME"]

REQUIRED_FIELDS = {"registry_id", "facility_name", "state"}


COLUMN_CANDIDATES = {
    "registry_id": ["REGISTRY_ID", "FRS_ID", "PGM_SYS_ID"],
    "facility_name": ["PRIMARY_NAME", "FAC_NAME", "FACILITY_NAME"],
    "latitude": ["LATITUDE83", "LATITUDE", "FAC_LAT", "LAT_DD"],
    "longitude": ["LONGITUDE83", "LONGITUDE", "FAC_LONG", "LONG_DD"],
    "state": ["STATE_CODE", "FAC_STATE", "STATE_ABBR", "STATE"],
    "county": ["COUNTY_NAME", "FAC_COUNTY"],
    "naics_codes_raw": ["NAICS_CODES", "PRIMARY_NAICS_CODE", "NAICS_CODE"],
    "sic_codes_raw": ["SIC_CODES", "PRIMARY_SIC_CODE", "SIC_CODE"],
    "address": ["LOCATION_ADDRESS", "FAC_ADDRESS"],
    "city": ["CITY_NAME", "FAC_CITY"],
    "postal_code": ["POSTAL_CODE", "FAC_ZIP"],
    "programs_raw": ["PGM_SYS_ACRNMS", "PROGRAMS"],
    "site_type": ["SITE_TYPE_NAME"],
    "huc_code": ["HUC_CODE"],
    "coord_accuracy_value": ["ACCURACY_VALUE"],
    "coord_collect_method": ["COLLECT_DESC"],
    "coord_reference_point": ["REF_POINT_DESC"],
    "coord_datum": ["HDATUM_DESC"],
}


def resolve_frs_columns(columns: list[str], candidates: dict[str, list[str]] | None = None) -> dict:
    """
    Match real column names against the candidate lists. Required
    fields raise immediately if unmatched; optional fields log a
    warning and resolve to None. Pure function, no I/O, so it can be
    unit tested against synthetic header lists.
    """
    candidates = candidates or COLUMN_CANDIDATES
    resolved: dict[str, str | None] = {}
    for field_name, field_candidates in candidates.items():
        if field_name in REQUIRED_FIELDS:
            resolved[field_name] = require_column(columns, field_candidates, field_name)
        else:
            match = detect_column(columns, field_candidates)
            if match is None:
                logger.warning(
                    "Optional column '%s' not found (tried %s). Continuing without it.",
                    field_name,
                    field_candidates,
                )
            resolved[field_name] = match
    return resolved


def filter_and_standardize(
    df: pd.DataFrame, resolved: dict, target_states: list[str] | None = None
) -> tuple[pd.DataFrame, dict]:
    """
    Filter to target states and rename columns to the standardized
    facility_site field names from docs/Analytical_Data_Model.md. Pure
    function (no I/O) so the filtering and stats logic is unit
    testable independent of the actual download.
    """
    target_states = target_states or TARGET_STATES
    state_col = resolved["state"]

    state_norm = df[state_col].astype(str).str.strip().str.upper()
    filtered = df[state_norm.isin(target_states)].copy()
    accepted_rows = len(filtered)

    lat_col = resolved.get("latitude")
    lon_col = resolved.get("longitude")
    if lat_col and lon_col:
        missing_coords = int((filtered[lat_col].isna() | filtered[lon_col].isna()).sum())
    else:
        # Can't even evaluate coordinate presence — treat all as unknown,
        # never as "present," per the missing-data rule in the scope doc.
        missing_coords = accepted_rows

    rename_map = {source_col: field_name for field_name, source_col in resolved.items() if source_col}
    standardized = filtered.rename(columns=rename_map)

    state_breakdown = state_norm[state_norm.isin(target_states)].value_counts().to_dict()

    stats = {
        "accepted_rows": accepted_rows,
        "missing_coords": missing_coords,
        "state_breakdown": state_breakdown,
    }
    return standardized, stats


def load_frs_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["sources"]["epa_frs"]


def main() -> None:
    source_config = load_frs_config()
    url = source_config.get("direct_download_url")
    if not url:
        raise ValueError(
            "config/sources.yaml has no direct_download_url set for epa_frs. "
            "Set it before running this connector."
        )

    zip_path = RAW_DIR / "national_single.zip"
    result = download_file(url, zip_path)
    provenance_note = (
        f"sha256={result.sha256} bytes={result.bytes_downloaded} accessed_at={result.accessed_at}"
    )
    logger.info("Provenance: %s", provenance_note)

    extracted = unzip_file(zip_path, RAW_DIR / "extracted")
    csv_files = discover_csv_files(RAW_DIR / "extracted")
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found after extracting {zip_path}. "
            f"Extracted files were: {extracted}. The archive format may have changed — "
            f"check the landing page manually before re-running."
        )
    if len(csv_files) > 1:
        logger.warning(
            "Expected a single CSV in the 'state single file' product but found %d: %s. "
            "Using the first one; inspect the others manually before trusting this run.",
            len(csv_files),
            csv_files,
        )

    csv_path = csv_files[0]
    logger.info("Reading %s", csv_path)
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)
    downloaded_rows = len(df)
    logger.info("Loaded %d rows, %d columns", downloaded_rows, len(df.columns))

    resolved = resolve_frs_columns(list(df.columns))
    logger.info("Resolved columns: %s", resolved)
    logger.info(
        "STOP AND CHECK before trusting downstream output: confirm each match above "
        "against the real header row, then remove this log line's warning in your "
        "own notes once confirmed."
    )

    standardized, stats = filter_and_standardize(df, resolved)
    logger.info("State breakdown (accepted rows): %s", stats["state_breakdown"])
    logger.info(
        "Rows with missing/unusable coordinates: %d of %d",
        stats["missing_coords"],
        stats["accepted_rows"],
    )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / "frs_facility_site.csv"
    standardized.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", stats["accepted_rows"], out_path)

    append_source_volume_log(
        SOURCE_VOLUME_LOG,
        {
            "source": "epa_frs",
            "run_timestamp_utc": result.accessed_at,
            "downloaded_rows": downloaded_rows,
            "accepted_rows": stats["accepted_rows"],
            "rejected_or_quarantined": downloaded_rows - stats["accepted_rows"],
            "duplicate_rows": "",  # dedup happens at master-index build time, Step 3
            "linked_rows": "",
            "final_unique_entities": "",
            "notes": f"{provenance_note}; missing_coords={stats['missing_coords']}",
        },
    )


if __name__ == "__main__":
    main()
