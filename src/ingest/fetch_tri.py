"""
TRACE-ER Explorer — EPA TRI facility connector (via Envirofacts efservice).

TRI's own web download page ("TRI Basic Data Files") has a
JavaScript-driven download button with no static URL — there is no
direct zip link to verify or hardcode, unlike FRS and ECHO. Instead,
this connector uses EPA's documented Envirofacts efservice REST API,
which is queryable per state without downloading a national file.


    https://data.epa.gov/efservice/tri_facility/state_abbr/VA/CSV



Usage:
    python src/ingest/fetch_tri.py
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
RAW_DIR = REPO_ROOT / "data" / "raw" / "tri"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
SOURCE_VOLUME_LOG = REPO_ROOT / "validation" / "source_volume_log.csv"

TARGET_STATES = ["TX", "PA", "NM", "ME"]

REQUIRED_FIELDS = {"epa_registry_id", "state_abbr", "facility_name"}

COLUMN_CANDIDATES = {
    "tri_facility_id": ["tri_facility_id"],
    "epa_registry_id": ["epa_registry_id"],
    "frs_id": ["frs_id"],
    "facility_name": ["facility_name"],
    "address": ["street_address"],
    "city": ["city_name"],
    "county": ["county_name"],
    "state_abbr": ["state_abbr"],
    "postal_code": ["zip_code"],
    "region": ["region"],
    "fac_closed_ind": ["fac_closed_ind"],
    "parent_co_name": ["parent_co_name"],
    "latitude": ["fac_latitude"],
    "longitude": ["fac_longitude"],
    "pref_latitude": ["pref_latitude"],
    "pref_longitude": ["pref_longitude"],
    "coord_accuracy_value": ["pref_accuracy"],
    "coord_collect_method": ["pref_collect_meth"],
    "coord_datum": ["pref_horizontal_datum"],
}


def load_tri_config() -> dict:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["sources"]["epa_tri"]


def build_state_url(base_url: str, table: str, state: str, fmt: str = "CSV") -> str:
    """Function: build the confirmed URL pattern for a state-filtered pull."""
    return f"{base_url}/{table}/state_abbr/{state}/{fmt}"


def build_count_url(base_url: str, table: str, state: str | None = None) -> str:
    """Function: build the count-check URL, filtered or national."""
    if state:
        return f"{base_url}/{table}/state_abbr/{state}/COUNT/JSON"
    return f"{base_url}/{table}/COUNT/JSON"


def fetch_state_facility_data(base_url: str, table: str, state: str) -> pd.DataFrame:
    """
    Fetch one state's tri_facility data, with the mandatory count
    safety check applied BEFORE trusting the CSV body. Raises if the
    filtered count doesn't look like a real subset (see
    common.verify_filtered_count for exactly what that means and why).
    """
    unfiltered_count = get_efservice_count(build_count_url(base_url, table))
    filtered_count = get_efservice_count(build_count_url(base_url, table, state))
    verify_filtered_count(filtered_count, unfiltered_count, filter_description=f"state_abbr={state}")

    csv_url = build_state_url(base_url, table, state)
    logger.info("Fetching %s (expecting %d rows, confirmed via COUNT check)", csv_url, filtered_count)
    response = common.requests.get(csv_url, timeout=120)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text), dtype=str, low_memory=False)

    if len(df) != filtered_count:
        logger.warning(
            "Row count mismatch for %s: COUNT endpoint said %d, CSV body has %d rows. "
            "Proceeding, but this is worth investigating — the two are not guaranteed "
            "to be computed identically, but a large gap would be suspicious.",
            state, filtered_count, len(df),
        )
    return df


def resolve_and_standardize(df: pd.DataFrame, target_states: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """
    function: resolve confirmed columns and filter to target
    states (a no-op filter here since data is already fetched
    per-state, but kept for consistency with the other connectors and
    as a defensive double-check in case a national pull is ever used
    instead).
    """
    target_states = target_states or TARGET_STATES
    resolved = common.resolve_columns(list(df.columns), COLUMN_CANDIDATES, REQUIRED_FIELDS)
    standardized, stats = common.filter_and_standardize_by_state(
        df, resolved, target_states, state_field="state_abbr", lat_field="latitude", lon_field="longitude"
    )
    return standardized, stats


def main() -> None:
    source_config = load_tri_config()
    base_url = source_config.get("efservice_base_url")
    table = source_config.get("efservice_table_facility")
    if not base_url or not table:
        raise ValueError(
            "config/sources.yaml is missing efservice_base_url or efservice_table_facility "
            "for epa_tri. Set both before running this connector."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_states_dfs = []
    per_state_counts = {}

    for state in TARGET_STATES:
        df = fetch_state_facility_data(base_url, table, state)
        raw_path = RAW_DIR / f"tri_facility_{state}.csv"
        df.to_csv(raw_path, index=False)
        logger.info("Saved raw %s data to %s (%d rows)", state, raw_path, len(df))
        per_state_counts[state] = len(df)
        all_states_dfs.append(df)
        time.sleep(1)  # be a polite, non-hammering client to a public government API

    combined = pd.concat(all_states_dfs, ignore_index=True)
    downloaded_rows = len(combined)
    logger.info("Combined all target states: %d total rows. Per-state: %s", downloaded_rows, per_state_counts)

    resolved_preview = common.resolve_columns(list(combined.columns), COLUMN_CANDIDATES, REQUIRED_FIELDS)
    logger.info("Resolved columns (confirmed set): %s", resolved_preview)

    standardized, stats = resolve_and_standardize(combined)
    logger.info("State breakdown (accepted rows): %s", stats["state_breakdown"])
    logger.info(
        "Rows with missing/unusable coordinates: %d of %d",
        stats["missing_coords"],
        stats["accepted_rows"],
    )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / "tri_facility.csv"
    standardized.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", stats["accepted_rows"], out_path)

    append_source_volume_log(
        SOURCE_VOLUME_LOG,
        {
            "source": "epa_tri_facility",
            "run_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "downloaded_rows": downloaded_rows,
            "accepted_rows": stats["accepted_rows"],
            "rejected_or_quarantined": downloaded_rows - stats["accepted_rows"],
            "duplicate_rows": "",
            "linked_rows": "",
            "final_unique_entities": "",
            "notes": f"per_state_counts={per_state_counts}; missing_coords={stats['missing_coords']}; "
                     f"release-quantity data NOT included, see module docstring",
        },
    )


if __name__ == "__main__":
    main()
