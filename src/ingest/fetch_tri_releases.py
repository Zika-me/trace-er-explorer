"""
TRACE-ER Explorer — EPA TRI release-quantity connector.

Usage:
    python src/ingest/fetch_tri_releases.py
"""

from __future__ import annotations

import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import (  # noqa: E402
    append_source_volume_log,
    get_efservice_count,
    logger,
    verify_filtered_count,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw" / "tri_releases"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
SOURCE_VOLUME_LOG = REPO_ROOT / "validation" / "source_volume_log.csv"

TARGET_STATES = ["TX", "PA", "NM", "ME"]

ANALYTICAL_YEARS = list(range(2019, 2026))  # 2019 through 2025 inclusive

REQUIRED_FIELDS = {"reporting_year", "tri_facility_id", "state", "chemical_or_parameter"}

COLUMN_CANDIDATES = {
    "reporting_year": ["year"],
    "tri_facility_id": ["trifd"],
    "frs_id": ["frs id"],
    "facility_name": ["facility name"],
    "state": ["st"],
    "county": ["county"],
    "city": ["city"],
    "latitude": ["latitude"],
    "longitude": ["longitude"],
    "horizontal_datum": ["horizontal datum"],
    "chemical_or_parameter": ["chemical"],
    "cas_number": ["cas#"],
    "clean_air_act_chemical": ["clean air act chemical"],
    "classification": ["classification"],
    "is_metal": ["metal"],
    "is_carcinogen": ["carcinogen"],
    "is_pbt": ["pbt"],
    "is_pfas": ["pfas"],
    "form_type": ["form type"],
    "unit_of_measure": ["unit of measure"],
    "on_site_release_total": ["on-site release total"],
    "off_site_release_total": ["off-site release total"],
    "total_releases": ["total releases"],
    "production_waste_total": ["production wste (8.1-8.7)"],
    "industry_sector": ["industry sector"],
    "primary_naics": ["primary naics"],
    "primary_sic": ["primary sic"],
    "parent_co_name": ["parent co name"],
}


def load_tri_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["sources"]["epa_tri"]


def build_query_url(base_url: str, table: str, state: str, year: int, fmt: str = "CSV") -> str:
    """Pure function: build the confirmed state+year query URL pattern."""
    return f"{base_url}/{table}/st/{state}/year/{year}/{fmt}"


def build_year_count_url(base_url: str, table: str, year: int) -> str:
    """Pure function: build the year-only (national) count URL, used as the unfiltered baseline."""
    return f"{base_url}/{table}/year/{year}/COUNT/JSON"


def build_state_year_count_url(base_url: str, table: str, state: str, year: int) -> str:
    """Pure function: build the state+year filtered count URL."""
    return f"{base_url}/{table}/st/{state}/year/{year}/COUNT/JSON"


def fetch_state_year_releases(base_url: str, table: str, state: str, year: int) -> pd.DataFrame:
    """
    Fetch one state's TRI releases for one year, with the mandatory
    count safety check applied before trusting the CSV body. Uses the
    YEAR-ONLY national count as the unfiltered baseline, since a fully
    unfiltered (no year, no state) count would always trivially pass
    and wouldn't actually test whether the state filter took effect.
    """
    unfiltered_count = get_efservice_count(build_year_count_url(base_url, table, year))
    filtered_count = get_efservice_count(build_state_year_count_url(base_url, table, state, year))
    verify_filtered_count(filtered_count, unfiltered_count, filter_description=f"st={state}, year={year}")

    csv_url = build_query_url(base_url, table, state, year)
    logger.info("Fetching %s (expecting %d rows, confirmed via COUNT check)", csv_url, filtered_count)
    response = common.requests.get(csv_url, timeout=180)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text), dtype=str, low_memory=False)

    if len(df) != filtered_count:
        logger.warning(
            "Row count mismatch for st=%s year=%d: COUNT endpoint said %d, CSV body has %d rows. "
            "Proceeding, but worth investigating.",
            state, year, filtered_count, len(df),
        )
    return df


def resolve_and_standardize(df: pd.DataFrame) -> dict:
    """
    function: resolve confirmed columns and rename to standardized
    names.
    """
    resolved = common.resolve_columns(list(df.columns), COLUMN_CANDIDATES, REQUIRED_FIELDS)
    rename_map = {source_col: field_name for field_name, source_col in resolved.items() if source_col}
    standardized = df.rename(columns=rename_map)
    return {"data": standardized, "resolved": resolved}


def main() -> None:
    source_config = load_tri_config()
    base_url = source_config.get("efservice_base_url")
    table = source_config.get("efservice_table_releases")
    if not base_url or not table:
        raise ValueError(
            "config/sources.yaml is missing efservice_base_url or efservice_table_releases "
            "for epa_tri. Set both before running this connector."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs = []
    per_combo_counts = {}
    failed_combos = []
    resolved_example = None

    total_combos = len(TARGET_STATES) * len(ANALYTICAL_YEARS)
    combo_num = 0

    for state in TARGET_STATES:
        for year in ANALYTICAL_YEARS:
            combo_num += 1
            logger.info("[%d/%d] Fetching st=%s year=%d", combo_num, total_combos, state, year)
            try:
                df = fetch_state_year_releases(base_url, table, state, year)
            except Exception as exc:  # noqa: BLE001 — deliberately broad: one bad combo must not abort the run
                logger.error("FAILED for st=%s year=%d: %s. Skipping, continuing with remaining combos.", state, year, exc)
                failed_combos.append((state, year, str(exc)))
                continue

            raw_path = RAW_DIR / f"tri_releases_{state}_{year}.csv"
            df.to_csv(raw_path, index=False)
            per_combo_counts[f"{state}_{year}"] = len(df)

            result = resolve_and_standardize(df)
            if resolved_example is None:
                resolved_example = result["resolved"]
            all_dfs.append(result["data"])

            time.sleep(1)  # polite pacing against a public government API

    if not all_dfs:
        raise RuntimeError(
            f"No state-year combinations succeeded. Failed combos: {failed_combos}. "
            f"Check the connector against the live API before retrying."
        )

    combined = pd.concat(all_dfs, ignore_index=True)
    downloaded_rows = len(combined)
    logger.info(
        "Combined %d state-year combinations: %d total rows. Per-combo counts: %s",
        len(all_dfs), downloaded_rows, per_combo_counts,
    )
    logger.info("Resolved columns (from first successful combo): %s", resolved_example)
    if failed_combos:
        logger.warning(
            "%d of %d combinations FAILED and were skipped: %s",
            len(failed_combos), total_combos, failed_combos,
        )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / "tri_releases.csv"
    combined.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", downloaded_rows, out_path)

    append_source_volume_log(
        SOURCE_VOLUME_LOG,
        {
            "source": "epa_tri_releases",
            "run_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "downloaded_rows": downloaded_rows,
            "accepted_rows": downloaded_rows,
            "rejected_or_quarantined": "",
            "duplicate_rows": "",
            "linked_rows": "",
            "final_unique_entities": "",
            "notes": f"per_combo_counts={per_combo_counts}; failed_combos={failed_combos}; "
                     f"~90 granular per-method waste-transfer columns NOT extracted, see module docstring",
        },
    )


if __name__ == "__main__":
    main()