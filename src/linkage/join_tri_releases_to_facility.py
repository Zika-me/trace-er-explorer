"""
TRACE-ER Explorer — join TRI release records to TRI facility identity.


Usage:
    python src/linkage/join_tri_releases_to_facility.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
import common  # noqa: E402
from common import logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TRI_FACILITY_INTERIM = REPO_ROOT / "data" / "interim" / "tri_facility.csv"
TRI_RELEASES_INTERIM = REPO_ROOT / "data" / "interim" / "tri_releases.csv"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
VALIDATION_DIR = REPO_ROOT / "validation"


def load_tri_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """dtype=str forced for the same reason as everywhere else in this pipeline — see build_master_index.py."""
    for path, connector in [
        (TRI_RELEASES_INTERIM, "src/ingest/fetch_tri_releases.py"),
        (TRI_FACILITY_INTERIM, "src/ingest/fetch_tri.py"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run {connector} first.")
    releases = pd.read_csv(TRI_RELEASES_INTERIM, dtype=str, low_memory=False)
    facility = pd.read_csv(TRI_FACILITY_INTERIM, dtype=str, low_memory=False)
    return releases, facility


def merge_releases_with_facility(releases: pd.DataFrame, facility: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function: left-join releases to facility on tri_facility_id,
    with every facility column (except the join key) explicitly
    suffixed "_facility" first, to avoid ambiguity from the multiple
    genuinely-overlapping standardized field names between these two
    TRI-derived tables.
    """
    facility_renamed = facility.rename(
        columns={c: f"{c}_facility" for c in facility.columns if c != "tri_facility_id"}
    )
    merged = pd.merge(
        releases, facility_renamed, on="tri_facility_id", how="left", indicator="_merge_facility"
    )
    return merged


def build_match_stats(merged: pd.DataFrame) -> dict:
    """
    Pure function: quantify how well the join worked. Two DIFFERENT
    things are checked, deliberately kept separate: whether a release
    row found ANY facility match at all, and — among those that did —
    whether that facility record actually has a usable
    epa_registry_id. A facility match with a blank epa_registry_id is
    a different problem from no match at all, and conflating them
    would hide which fix is actually needed.
    """
    total = len(merged)
    matched = int((merged["_merge_facility"] == "both").sum())
    unmatched = total - matched

    matched_rows = merged[merged["_merge_facility"] == "both"]
    registry_col = "epa_registry_id_facility"
    if registry_col in matched_rows.columns:
        matched_with_registry_id = int(matched_rows[registry_col].notna().sum())
    else:
        matched_with_registry_id = 0
    matched_missing_registry_id = matched - matched_with_registry_id

    unmatched_tri_facility_ids = sorted(
        set(merged.loc[merged["_merge_facility"] == "left_only", "tri_facility_id"].dropna())
    )

    return {
        "total_release_rows": total,
        "matched_to_facility": matched,
        "unmatched_no_facility_record": unmatched,
        "matched_but_facility_missing_registry_id": matched_missing_registry_id,
        "usable_for_master_index_join": matched_with_registry_id,
        "unmatched_tri_facility_id_sample": unmatched_tri_facility_ids[:10],
    }


def build_enriched_output(merged: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function: select and rename the final enriched release table.
    """
    df = merged.copy()

    def coalesce(a: str, b: str):
        if a in df.columns and b in df.columns:
            return df[a].where(df[a].notna(), df[b])
        return df.get(a, df.get(b))

    df["epa_registry_id"] = df.get("epa_registry_id_facility")
    df["facility_name"] = coalesce("facility_name_facility", "facility_name")
    df["state"] = coalesce("state_abbr_facility", "state")
    df["county"] = coalesce("county_facility", "county")
    df["city"] = coalesce("city_facility", "city")
    df["latitude"] = coalesce("pref_latitude_facility", "latitude")
    df["longitude"] = coalesce("pref_longitude_facility", "longitude")
    df["coord_accuracy_value"] = df.get("coord_accuracy_value_facility")
    df["has_facility_match"] = df["_merge_facility"] == "both"

    keep_cols = [
        "tri_facility_id", "epa_registry_id", "has_facility_match",
        "reporting_year", "chemical_or_parameter", "cas_number", "classification",
        "is_metal", "is_carcinogen", "is_pbt", "is_pfas", "form_type", "unit_of_measure",
        "on_site_release_total", "off_site_release_total", "total_releases",
        "production_waste_total", "industry_sector", "primary_naics", "primary_sic",
        "facility_name", "state", "county", "city", "latitude", "longitude",
        "coord_accuracy_value",
    ]
    existing_cols = [c for c in keep_cols if c in df.columns]
    return df[existing_cols]


def write_join_report(stats: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TRI Releases-to-Facility Join Report",
        "",
        "Generated automatically by `join_tri_releases_to_facility.py`.",
        "",
        f"- Total release rows: {stats['total_release_rows']}",
        f"- Matched to a facility record: {stats['matched_to_facility']}",
        f"- NOT matched to any facility record: {stats['unmatched_no_facility_record']}",
    ]
    if stats["unmatched_no_facility_record"] > 0:
        lines.append(
            "  This can happen when a facility that reported releases in an earlier "
            "year is no longer in the current facility snapshot (e.g. deregistered "
            "or reorganized since). Worth spot-checking a few of the sampled IDs "
            "below rather than assuming the cause."
        )
    lines += [
        f"- Matched to a facility, but that facility record has NO usable epa_registry_id: "
        f"{stats['matched_but_facility_missing_registry_id']}",
        f"- Usable for joining into the master facility index (has epa_registry_id): "
        f"{stats['usable_for_master_index_join']}",
        "",
    ]
    if stats["unmatched_tri_facility_id_sample"]:
        lines.append("Sample of unmatched tri_facility_id values (for spot-checking):")
        for tid in stats["unmatched_tri_facility_id_sample"]:
            lines.append(f"- {tid}")

    out_path.write_text("\n".join(lines))
    logger.info("Wrote join report to %s", out_path)


def main() -> None:
    releases, facility = load_tri_tables()
    logger.info(
        "Loaded TRI releases: %d rows. TRI facility: %d rows. "
        "(This script does not itself check tri_facility_id for duplicates — "
        "run check_duplicate_ids.py first if that hasn't been verified recently, "
        "since a duplicate there would inflate this join's row counts.)",
        len(releases), len(facility),
    )

    merged = merge_releases_with_facility(releases, facility)
    stats = build_match_stats(merged)
    logger.info("Match stats: %s", stats)

    enriched = build_enriched_output(merged)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "tri_releases_enriched.csv"
    enriched.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(enriched), out_path)

    write_join_report(stats, VALIDATION_DIR / "tri_releases_join_report.md")


if __name__ == "__main__":
    main()