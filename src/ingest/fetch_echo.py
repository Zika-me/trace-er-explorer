"""
TRACE-ER Explorer — EPA ECHO Exporter connector (compliance history).

Downloads the EPA ECHO Exporter (one row per regulated facility,
130+ summary fields covering inspections, violations, enforcement,
and penalties across CAA/CWA/RCRA/SDWA/TRI), filters it to the
project's target states, and joins to FRS via REGISTRY_ID.


  Landing page:    https://echo.epa.gov/tools/data-downloads
  Direct download: https://echo.epa.gov/files/echodownloads/echo_exporter.zip

Usage:
    python src/ingest/fetch_echo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import (  # noqa: E402
    append_source_volume_log,
    discover_columns_by_keyword,
    discover_csv_files,
    download_file,
    logger,
    unzip_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw" / "echo"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
VALIDATION_DIR = REPO_ROOT / "validation"
SOURCE_VOLUME_LOG = REPO_ROOT / "validation" / "source_volume_log.csv"

TARGET_STATES = ["TX", "PA", "NM", "ME"]

REQUIRED_FIELDS = {"registry_id", "state"}

# CORE fields only — the ones needed for the FRS join and state
# filtering. NOT confirmed against a live download from this
# environment (no network path to echo.epa.gov from here). Confirm
# the 'Resolved core columns' log line against the real header on
# first live run, exactly as was done for FRS.
CORE_COLUMN_CANDIDATES = {
    "registry_id": ["REGISTRY_ID", "FRS_ID"],
    "facility_name": ["FAC_NAME", "PRIMARY_NAME", "FACILITY_NAME"],
    "state": ["FAC_STATE", "STATE_CODE"],
    "latitude": ["FAC_LAT", "LATITUDE83", "LATITUDE"],
    "longitude": ["FAC_LONG", "LONGITUDE83", "LONGITUDE"],
    "county": ["FAC_COUNTY", "COUNTY_NAME"],
}

# Keyword buckets for discovering the ~120+ compliance-summary fields
# whose exact names are not confirmed. This does NOT rename or
# standardize these columns — it only reports which real columns
# contain each keyword, so a human can confirm the mapping before any
# feature gets built on top of it.
KEYWORD_BUCKETS = {
    "program_flags": ["FLAG"],
    "inspections": ["INSPECTION"],
    "violations": ["VIOLATION", "NONCOMPLIANCE", "SNC"],
    "enforcement": ["ENFORCEMENT", "FORMAL", "INFORMAL"],
    "penalties": ["PENALT"],
    "compliance_history_qtrs": ["COMPL", "QTR"],
}


def resolve_echo_core_columns(columns: list[str]) -> dict:
    """Thin wrapper around common.resolve_columns for ECHO's core fields."""
    return common.resolve_columns(columns, CORE_COLUMN_CANDIDATES, REQUIRED_FIELDS)


def filter_and_standardize(df: pd.DataFrame, resolved: dict, target_states: list[str] | None = None):
    """Thin wrapper around common.filter_and_standardize_by_state."""
    return common.filter_and_standardize_by_state(df, resolved, target_states or TARGET_STATES)


def write_discovery_report(discovery: dict, all_columns: list[str], out_path: Path) -> None:
    """
    Write a human-readable Markdown report of the keyword-discovered
    columns, so the connector's guesswork is visible and reviewable
    rather than silently baked into downstream code.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EPA ECHO Exporter — Discovered Column Report",
        "",
        "Generated automatically by `fetch_echo.py`. This is NOT a confirmed",
        "crosswalk — it lists every real column whose name contains a likely",
        "keyword, for human review. Confirm against the official column",
        "reference spreadsheet (see `column_reference_url` in",
        "`config/sources.yaml`) before treating any of these as final.",
        "",
        f"Total columns in file: {len(all_columns)}",
        "",
    ]
    for bucket, matches in discovery.items():
        lines.append(f"## {bucket} ({len(matches)} matches)")
        lines.append("")
        if matches:
            for col in matches:
                lines.append(f"- `{col}`")
        else:
            lines.append("*(no columns matched this keyword bucket — the naming convention")
            lines.append("may differ from what was guessed; check the full column list below)*")
        lines.append("")

    lines.append("## Full column list (for reference)")
    lines.append("")
    for col in all_columns:
        lines.append(f"- `{col}`")

    out_path.write_text("\n".join(lines))
    logger.info("Wrote discovery report to %s", out_path)


def load_echo_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["sources"]["epa_echo"]


def main() -> None:
    source_config = load_echo_config()
    url = source_config.get("direct_download_url")
    if not url:
        raise ValueError(
            "config/sources.yaml has no direct_download_url set for epa_echo. "
            "Set it before running this connector."
        )

    zip_path = RAW_DIR / "echo_exporter.zip"
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
            f"Extracted files were: {extracted}. The archive format may have changed."
        )
    if len(csv_files) > 1:
        logger.warning(
            "Expected a single CSV but found %d: %s. Using the first one; "
            "inspect the others manually before trusting this run.",
            len(csv_files),
            csv_files,
        )

    csv_path = csv_files[0]
    logger.info("Reading %s (this is a large file, may take a while)", csv_path)
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)
    downloaded_rows = len(df)
    all_columns = list(df.columns)
    logger.info("Loaded %d rows, %d columns", downloaded_rows, len(all_columns))

    resolved = resolve_echo_core_columns(all_columns)
    logger.info("Resolved core columns: %s", resolved)
    logger.info(
        "STOP AND CHECK before trusting downstream output: confirm each core match "
        "above against the real header row."
    )

    discovery = discover_columns_by_keyword(all_columns, KEYWORD_BUCKETS)
    for bucket, matches in discovery.items():
        logger.info("Keyword bucket '%s': %d columns matched", bucket, len(matches))
    write_discovery_report(discovery, all_columns, VALIDATION_DIR / "echo_column_discovery.md")

    standardized, stats = filter_and_standardize(df, resolved)
    logger.info("State breakdown (accepted rows): %s", stats["state_breakdown"])
    logger.info(
        "Rows with missing/unusable coordinates: %d of %d",
        stats["missing_coords"],
        stats["accepted_rows"],
    )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / "echo_facility_summary.csv"
    standardized.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", stats["accepted_rows"], out_path)

    append_source_volume_log(
        SOURCE_VOLUME_LOG,
        {
            "source": "epa_echo",
            "run_timestamp_utc": result.accessed_at,
            "downloaded_rows": downloaded_rows,
            "accepted_rows": stats["accepted_rows"],
            "rejected_or_quarantined": downloaded_rows - stats["accepted_rows"],
            "duplicate_rows": "",
            "linked_rows": "",  # actual FRS join happens at Step 3
            "final_unique_entities": "",
            "notes": (
                f"{provenance_note}; missing_coords={stats['missing_coords']}; "
                f"see validation/echo_column_discovery.md for unconfirmed compliance fields"
            ),
        },
    )


if __name__ == "__main__":
    main()
