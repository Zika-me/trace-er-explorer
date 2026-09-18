"""
TRACE-ER Explorer — aggregate TRI release records into per-entity features.


Usage:
    python src/features/aggregate_tri_release_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from common import logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TRI_RELEASES_ENRICHED = REPO_ROOT / "data" / "processed" / "tri_releases_enriched.csv"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
VALIDATION_DIR = REPO_ROOT / "validation"

NUMERIC_COLS = ["on_site_release_total", "off_site_release_total", "total_releases", "production_waste_total"]


def load_enriched_releases() -> pd.DataFrame:
    if not TRI_RELEASES_ENRICHED.exists():
        raise FileNotFoundError(
            f"{TRI_RELEASES_ENRICHED} not found. Run src/linkage/join_tri_releases_to_facility.py first."
        )
    return pd.read_csv(TRI_RELEASES_ENRICHED, dtype=str, low_memory=False)


def is_yes(series: pd.Series) -> pd.Series:
    """
    Pure function: normalize and compare a TRI hazard-flag column
    against the confirmed real value "YES". Returns False (not NaN)
    for missing/unparseable values, since "not confirmed yes" is the
    correct conservative reading for a flag we cannot verify true.
    """
    return series.astype(str).str.strip().str.upper() == "YES"


def parse_numeric_with_tracking(series: pd.Series) -> tuple[pd.Series, int]:
    """
    Pure function: coerce to numeric, returning both the parsed series
    and a count of values that were PRESENT but could not be parsed —
    distinct from values that were simply missing. A present-but-bad
    value is a data-quality signal; a missing value is not the same
    thing and should not be conflated with it.
    """
    parsed = pd.to_numeric(series, errors="coerce")
    unparseable = int((parsed.isna() & series.notna()).sum())
    return parsed, unparseable


def aggregate_release_features(enriched: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Pure function: aggregate release records by epa_registry_id.
    Rows with no epa_registry_id are excluded (and counted) rather
    than silently grouped under a NaN key, which pandas would
    otherwise do without complaint.

    Returns (per_entity_features, stats).
    """
    df = enriched.copy()
    input_rows = len(df)

    has_id = df["epa_registry_id"].notna() if "epa_registry_id" in df.columns else pd.Series(False, index=df.index)
    rows_missing_id = int((~has_id).sum())
    df = df[has_id].copy()

    unparseable_counts = {}
    for col in NUMERIC_COLS:
        if col in df.columns:
            parsed, unparseable = parse_numeric_with_tracking(df[col])
            df[f"_parsed_{col}"] = parsed
            unparseable_counts[col] = unparseable
        else:
            df[f"_parsed_{col}"] = pd.NA
            unparseable_counts[col] = 0

    df["_is_metal"] = is_yes(df["is_metal"]) if "is_metal" in df.columns else False
    df["_is_carcinogen"] = is_yes(df["is_carcinogen"]) if "is_carcinogen" in df.columns else False
    df["_is_pbt"] = is_yes(df["is_pbt"]) if "is_pbt" in df.columns else False
    df["_is_pfas"] = is_yes(df["is_pfas"]) if "is_pfas" in df.columns else False
    df["_is_form_a"] = (
        df["form_type"].astype(str).str.strip().str.upper() == "A" if "form_type" in df.columns else False
    )

    # reporting_year as a real number for max(), not a string comparison
    # that happens to work only because these particular years are all
    # the same digit length — explicit rather than relying on that.
    df["_reporting_year_numeric"] = pd.to_numeric(df.get("reporting_year"), errors="coerce")

    grouped = df.groupby("epa_registry_id")

    features = grouped.agg(
        distinct_chemical_count=("chemical_or_parameter", "nunique"),
        distinct_reporting_years=("reporting_year", "nunique"),
        most_recent_reporting_year=("_reporting_year_numeric", "max"),
        total_on_site_release=("_parsed_on_site_release_total", "sum"),
        total_off_site_release=("_parsed_off_site_release_total", "sum"),
        total_releases_sum=("_parsed_total_releases", "sum"),
        total_production_waste=("_parsed_production_waste_total", "sum"),
        any_carcinogen=("_is_carcinogen", "any"),
        any_pbt=("_is_pbt", "any"),
        any_pfas=("_is_pfas", "any"),
        any_metal=("_is_metal", "any"),
        form_a_row_count=("_is_form_a", "sum"),
    )
    features["total_release_records"] = grouped.size()
    features["form_r_row_count"] = features["total_release_records"] - features["form_a_row_count"]
    features = features.reset_index()

    stats = {
        "input_rows": input_rows,
        "rows_missing_epa_registry_id": rows_missing_id,
        "unique_entities_after_aggregation": len(features),
        "unparseable_value_counts": unparseable_counts,
    }
    return features, stats


def write_feature_report(stats: dict, features: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TRI Release Feature Aggregation Report",
        "",
        "Generated automatically by `aggregate_tri_release_features.py`.",
        "",
        f"- Input release records: {stats['input_rows']}",
        f"- Rows missing epa_registry_id (excluded): {stats['rows_missing_epa_registry_id']}",
        f"- Unique entities after aggregation: {stats['unique_entities_after_aggregation']}",
        "",
        "## Unparseable numeric values (present but not a valid number)",
        "",
    ]
    for col, count in stats["unparseable_value_counts"].items():
        lines.append(f"- {col}: {count}")
    lines += [
        "",
        "## Summary of aggregated features",
        "",
        f"- Entities with at least one carcinogen: {int(features['any_carcinogen'].sum())}",
        f"- Entities with at least one PBT chemical: {int(features['any_pbt'].sum())}",
        f"- Entities with at least one PFAS chemical: {int(features['any_pfas'].sum())}",
        f"- Entities with at least one metal: {int(features['any_metal'].sum())}",
        f"- Total on-site release volume across all entities: {features['total_on_site_release'].sum()}",
        f"- Entities with at least one Form A (below-threshold) submission: "
        f"{int((features['form_a_row_count'] > 0).sum())}",
    ]
    out_path.write_text("\n".join(lines))
    logger.info("Wrote feature aggregation report to %s", out_path)


def main() -> None:
    enriched = load_enriched_releases()
    logger.info("Loaded %d enriched release rows.", len(enriched))

    features, stats = aggregate_release_features(enriched)
    logger.info("Aggregation stats: %s", stats)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "tri_release_features.csv"
    features.to_csv(out_path, index=False)
    logger.info("Wrote %d entity-level feature rows to %s", len(features), out_path)

    write_feature_report(stats, features, VALIDATION_DIR / "tri_release_features_report.md")


if __name__ == "__main__":
    main()