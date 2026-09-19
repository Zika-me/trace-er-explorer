"""
TRACE-ER Explorer — join TRI release features into the master facility index.

Adds `tri_release_features.csv` (one row per epa_registry_id, built by
aggregate_tri_release_features.py) onto `master_facility_index.csv`
(one row per master_id, built by build_master_index.py — master_id
IS epa_registry_id, just renamed during that build).

Writes to a SEPARATE output file rather than overwriting
master_facility_index.csv in place. The base index is a validated
artifact from extensive real-data QA this session (null-ID exclusion,
presence-detection fix, coordinate-duplication fix, freshness checks)
— silently mutating it in place would make that validation history
harder to trust and reproduce. This is the first of what will
eventually be several feature layers (ECHO compliance-derived
features, incident data, etc.); each gets its own explicit join
rather than accumulating undocumented mutations to one file.

IMPORTANT — entities with no TRI release history are KEPT, not
dropped, with every release-feature column left NULL (never filled
with 0) and has_tri_release_data = False. A null total_on_site_release
means "no TRI release data exists for this entity," not "confirmed
zero release" — most entities in the master index are not
TRI-reporting facilities at all (TRI only covers a specific set of
industrial chemical users/handlers). Filling with 0 would misrepresent
missing data as a real zero finding, contradicting the
missing-data-is-not-zero-risk principle this project has followed
throughout (see the Feature and Indicator Register's data-confidence
component).

IMPORTANT — 34 known registry_ids have MULTIPLE master_facility_index
rows each (the confirmed multi-tenant-site pattern from 2026-09-17:
several different companies co-located at one physical site, sharing
one registry_id, because TRI's own facility table had duplicate
epa_registry_id rows that a plain merge does not deduplicate). Since
TRI release data is aggregated at the registry_id (site) level, not
the tenant level, every one of those tenant rows will show the SAME
shared site-level release total after this join. That is a correct
reflection of how TRI reports releases — per site, not per tenant —
not a bug introduced here. Documented rather than left as a silent
surprise.

Usage:
    python src/features/join_tri_features_to_master_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from common import logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_INDEX = REPO_ROOT / "data" / "processed" / "master_facility_index.csv"
TRI_RELEASE_FEATURES = REPO_ROOT / "data" / "processed" / "tri_release_features.csv"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
VALIDATION_DIR = REPO_ROOT / "validation"


def load_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    for path, script in [
        (MASTER_INDEX, "src/linkage/build_master_index.py"),
        (TRI_RELEASE_FEATURES, "src/features/aggregate_tri_release_features.py"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run {script} first.")
    master = pd.read_csv(MASTER_INDEX, dtype=str, low_memory=False)
    features = pd.read_csv(TRI_RELEASE_FEATURES, dtype=str, low_memory=False)
    return master, features


def check_features_key_uniqueness(features: pd.DataFrame) -> int:
    """
    Pure function: tri_release_features.csv is built by a pandas
    groupby().agg(), which cannot produce duplicate keys by
    construction — checked explicitly anyway rather than trusted
    silently, consistent with never assuming a join key is clean
    without verifying it, no matter how it was produced.
    """
    return int(features["epa_registry_id"].duplicated().sum())


def join_features_into_master_index(master: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function: left join, keeping every master index row
    regardless of whether it has TRI release data. No column-name
    collisions exist between these two tables (verified by
    inspection), so no suffixing is needed beyond consolidating the
    join key itself.
    """
    features_renamed = features.rename(columns={"epa_registry_id": "master_id"})
    merged = pd.merge(
        master, features_renamed, on="master_id", how="left", indicator="_merge_tri_features"
    )
    merged["has_tri_release_data"] = merged["_merge_tri_features"] == "both"
    merged = merged.drop(columns=["_merge_tri_features"])
    return merged


def build_join_stats(merged: pd.DataFrame) -> dict:
    """Pure function: summarize how many master index rows gained real TRI release data."""
    total = len(merged)
    with_data = int(merged["has_tri_release_data"].sum())
    return {
        "total_master_index_rows": total,
        "rows_with_tri_release_data": with_data,
        "rows_without_tri_release_data": total - with_data,
    }


def write_join_report(stats: dict, dupe_count: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Master Index + TRI Release Features Join Report",
        "",
        "Generated automatically by `join_tri_features_to_master_index.py`.",
        "",
        f"- tri_release_features.csv key (epa_registry_id) duplicate check: {dupe_count} "
        f"(should always be 0 — this table is built by groupby(), which cannot produce "
        f"duplicate keys; a nonzero value here means something upstream is broken)",
        "",
        f"- Total master index rows: {stats['total_master_index_rows']}",
        f"- Rows with real TRI release data attached: {stats['rows_with_tri_release_data']}",
        f"- Rows with NO TRI release data (left null, never zero-filled): "
        f"{stats['rows_without_tri_release_data']}",
        "",
        "A row with no TRI release data means this entity has never reported to TRI in the "
        "2019-2024 window covered so far. Most entities in the master index are not "
        "TRI-reporting facilities at all (TRI only covers specific industrial chemical "
        "users/handlers), so a low match rate here is expected, not an error.",
        "",
        "Note: 34 known registry_ids have multiple rows each in the master index (the "
        "confirmed multi-tenant-site pattern). Every tenant row at a shared site will show "
        "the SAME site-level release total after this join, since TRI reports releases per "
        "site, not per tenant company — a correct reflection of the source data, not a bug.",
    ]
    out_path.write_text("\n".join(lines))
    logger.info("Wrote join report to %s", out_path)


def main() -> None:
    master, features = load_tables()
    logger.info(
        "Loaded master index: %d rows. TRI release features: %d rows.", len(master), len(features)
    )

    dupe_count = check_features_key_uniqueness(features)
    if dupe_count > 0:
        raise ValueError(
            f"tri_release_features.csv has {dupe_count} duplicate epa_registry_id values — "
            f"this should be impossible given it's built by groupby(). Investigate before "
            f"proceeding; do not silently join against a table with a broken key."
        )

    merged = join_features_into_master_index(master, features)
    stats = build_join_stats(merged)
    logger.info("Join stats: %s", stats)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_facility_index_with_tri_features.csv"
    merged.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(merged), out_path)

    write_join_report(stats, dupe_count, VALIDATION_DIR / "master_index_tri_features_join_report.md")


if __name__ == "__main__":
    main()