"""
TRACE-ER Explorer — Step 3: Master Facility Index (FRS + ECHO + TRI).

Joins the standardized FRS, ECHO, and TRI interim tables on their
shared national registry ID and produces an analysis-ready master
facility index, plus a QA report.

Usage:
    python src/linkage/build_master_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
import common  # noqa: E402
from common import haversine_distance_km, logger  # noqa: E402
import fetch_frs  # noqa: E402
import fetch_echo  # noqa: E402
import fetch_tri  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FRS_INTERIM = REPO_ROOT / "data" / "interim" / "frs_facility_site.csv"
ECHO_INTERIM = REPO_ROOT / "data" / "interim" / "echo_facility_summary.csv"
TRI_INTERIM = REPO_ROOT / "data" / "interim" / "tri_facility.csv"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
VALIDATION_DIR = REPO_ROOT / "validation"

# Coordinate-agreement thresholds used only for QA reporting bands —
# not a pass/fail gate, just a way to summarize a distribution.
AGREEMENT_BANDS_KM = [1, 5, 10, 50]


def load_interim_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    dtype=str is not optional here. Re-reading a written CSV without
    forcing string dtype risks pandas silently inferring registry_id
    as float64 (e.g. "110072186793" -> 110072186793.0 -> back to
    "110072186793.0" on comparison)
    """
    for path, connector in [
        (FRS_INTERIM, "src/ingest/fetch_frs.py"),
        (ECHO_INTERIM, "src/ingest/fetch_echo.py"),
        (TRI_INTERIM, "src/ingest/fetch_tri.py"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run {connector} first.")
    frs = pd.read_csv(FRS_INTERIM, dtype=str, low_memory=False)
    echo = pd.read_csv(ECHO_INTERIM, dtype=str, low_memory=False)
    tri = pd.read_csv(TRI_INTERIM, dtype=str, low_memory=False)

    # Freshness check
    common.check_interim_freshness(list(frs.columns), list(fetch_frs.COLUMN_CANDIDATES.keys()), "FRS")
    common.check_interim_freshness(list(echo.columns), list(fetch_echo.ALL_COLUMN_CANDIDATES.keys()), "ECHO")
    common.check_interim_freshness(list(tri.columns), list(fetch_tri.COLUMN_CANDIDATES.keys()), "TRI")

    return frs, echo, tri


def merge_frs_echo(frs: pd.DataFrame, echo: pd.DataFrame) -> pd.DataFrame:
    """
    Outer join on registry_id, suffixing every overlapping column so
    nothing from either source is silently overwritten. 
    
    """
    merged = pd.merge(
        frs,
        echo,
        on="registry_id",
        how="outer",
        suffixes=("_frs", "_echo"),
        indicator=True,
    )
    return merged


def merge_third_source(
    merged_two: pd.DataFrame, third_df: pd.DataFrame, third_join_col: str, suffix: str
) -> pd.DataFrame:
    """
    Extend an already-merged two-source frame with a third source.
    """
    third = third_df.rename(columns={third_join_col: "registry_id"})
    rename_map = {c: f"{c}_{suffix}" for c in third.columns if c != "registry_id"}
    third = third.rename(columns=rename_map)
    merged = pd.merge(
        merged_two,
        third,
        on="registry_id",
        how="outer",
        indicator=f"_merge_{suffix}",
    )
    return merged


def compute_match_stats(merged: pd.DataFrame) -> dict:
    """Pure function: summarize how the outer join broke down."""
    counts = merged["_merge"].value_counts().to_dict()
    return {
        "both": int(counts.get("both", 0)),
        "frs_only": int(counts.get("left_only", 0)),
        "echo_only": int(counts.get("right_only", 0)),
        "total": len(merged),
    }


def check_state_agreement(merged: pd.DataFrame) -> dict:
    """
    For rows matched in both sources, check whether FRS's and ECHO's
    reported state agree.

    """
    both = merged[merged["_merge"] == "both"].copy()
    if len(both) == 0:
        return {"checked": 0, "agree": 0, "disagree": 0, "disagree_sample": []}

    state_frs = both.get("state_frs")
    state_echo = both.get("state_echo")
    if state_frs is None or state_echo is None:
        return {"checked": 0, "agree": 0, "disagree": 0, "disagree_sample": [],
                "note": "state_frs/state_echo columns not both present"}

    agree_mask = state_frs.str.strip().str.upper() == state_echo.str.strip().str.upper()
    disagree = both[~agree_mask]
    sample = disagree[["registry_id", "state_frs", "state_echo"]].head(10).to_dict("records")
    return {
        "checked": len(both),
        "agree": int(agree_mask.sum()),
        "disagree": int((~agree_mask).sum()),
        "disagree_sample": sample,
    }


def check_coordinate_agreement(merged: pd.DataFrame) -> dict:
    """
    For rows matched in both sources with usable coordinates from
    both, compute the great-circle distance between FRS's and ECHO's
    reported location.

    """
    both = merged[merged["_merge"] == "both"].copy()
    for col in ["latitude_frs", "longitude_frs", "latitude_echo", "longitude_echo"]:
        if col not in both.columns:
            return {"checked": 0, "note": f"column {col} not present"}

    usable = both.dropna(subset=["latitude_frs", "longitude_frs", "latitude_echo", "longitude_echo"]).copy()
    if len(usable) == 0:
        return {"checked": 0, "note": "no rows with coordinates from both sources"}

    distances = []
    for _, row in usable.iterrows():
        try:
            d = haversine_distance_km(
                float(row["latitude_frs"]), float(row["longitude_frs"]),
                float(row["latitude_echo"]), float(row["longitude_echo"]),
            )
            distances.append(d)
        except (ValueError, TypeError):
            continue

    if not distances:
        return {"checked": 0, "note": "no rows with parseable coordinates on both sides"}

    distances_series = pd.Series(distances)
    band_counts = {
        f"under_{band}km": int((distances_series < band).sum()) for band in AGREEMENT_BANDS_KM
    }
    band_counts[f"over_{AGREEMENT_BANDS_KM[-1]}km"] = int((distances_series >= AGREEMENT_BANDS_KM[-1]).sum())

    return {
        "checked": len(distances),
        "min_km": round(float(distances_series.min()), 3),
        "median_km": round(float(distances_series.median()), 3),
        "max_km": round(float(distances_series.max()), 3),
        **band_counts,
    }


def choose_best_coordinate(row: pd.Series) -> pd.Series:
    """
    Among every source that has a usable coordinate for this entity,
    prefer whichever has the lowest (best) coord_accuracy_value. When
    only one source has a usable coordinate, use that one. When
    multiple sources have coordinates but none has a parseable
    accuracy value, default to the first candidate in priority order
    (FRS > ECHO > TRI).
    """
    candidates = [
        ("frs", row.get("latitude_frs"), row.get("longitude_frs"), row.get("coord_accuracy_value_frs")),
        ("echo", row.get("latitude_echo"), row.get("longitude_echo"), row.get("coord_accuracy_value_echo")),
        ("tri", row.get("pref_latitude_tri"), row.get("pref_longitude_tri"), row.get("coord_accuracy_value_tri")),
    ]

    usable = [(src, lat, lon, acc) for src, lat, lon, acc in candidates if pd.notna(lat) and pd.notna(lon)]
    if not usable:
        return pd.Series({"latitude": None, "longitude": None, "coord_accuracy_value": None, "coord_source": None})

    def parsed_accuracy(acc):
        try:
            return float(acc) if pd.notna(acc) else None
        except (ValueError, TypeError):
            return None

    # Sort by (has-no-parseable-accuracy last, accuracy value ascending),
    # with original candidate order as a stable tie-break
    def sort_key(item):
        _, _, _, acc = item
        parsed = parsed_accuracy(acc)
        return (parsed is None, parsed if parsed is not None else 0.0)

    best_source, best_lat, best_lon, best_acc = sorted(usable, key=sort_key)[0]
    return pd.Series({
        "latitude": best_lat, "longitude": best_lon,
        "coord_accuracy_value": best_acc, "coord_source": best_source,
    })


def build_master_index(merged: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Build the final standardized master index from the merged frame.
    """
    df = merged.copy()

    no_id_mask = df["registry_id"].isna()
    dropped_no_id_count = int(no_id_mask.sum())
    df = df[~no_id_mask].copy()

    coord_cols = df.apply(choose_best_coordinate, axis=1)
    df = pd.concat([df, coord_cols], axis=1)

    if "_merge" in df.columns:
        frs_present = df["_merge"].isin(["both", "left_only"])
        echo_present = df["_merge"].isin(["both", "right_only"])
    else:
        frs_present = pd.Series(False, index=df.index)
        echo_present = pd.Series(False, index=df.index)

    if "_merge_tri" in df.columns:
        tri_present = df["_merge_tri"].isin(["both", "right_only"])
    else:
        tri_present = pd.Series(False, index=df.index)

    def sources_label(row_idx):
        parts = []
        if frs_present.loc[row_idx]:
            parts.append("FRS")
        if echo_present.loc[row_idx]:
            parts.append("ECHO")
        if tri_present.loc[row_idx]:
            parts.append("TRI")
        return ",".join(parts)

    df["sources_present"] = df.index.map(sources_label)
    df["source_count"] = frs_present.astype(int) + echo_present.astype(int) + tri_present.astype(int)

    df["linkage_confidence"] = "EXACT_ID"

    # Prefer FRS for identity fields (the richer identity source),
    # then ECHO, then TRI, falling back only when the preferred
    # source is absent for that row.
    def coalesce(*cols):
        result = None
        for col in cols:
            if col not in df.columns:
                continue
            result = df[col] if result is None else result.where(result.notna(), df[col])
        return result

    df["facility_name"] = coalesce("facility_name_frs", "facility_name_echo", "facility_name_tri")
    df["state"] = coalesce("state_frs", "state_echo", "state_abbr_tri")
    df["county"] = coalesce("county_frs", "county_echo", "county_tri")

    keep_cols = [
        "registry_id", "facility_name", "address", "city", "postal_code", "state", "county",
        "latitude", "longitude", "coord_accuracy_value", "coord_source",
        "sources_present", "source_count", "linkage_confidence",
        "naics_codes_raw_frs", "sic_codes_raw_frs", "programs_raw", "site_type", "huc_code",
        "fac_inspection_count", "fac_formal_action_count", "fac_informal_count",
        "fac_total_penalties", "fac_qtrs_with_nc", "fac_compliance_status", "fac_snc_flag",
        "caa_hpv_flag", "air_flag", "npdes_flag", "sdwis_flag", "rcra_flag", "tri_flag", "ghg_flag",
        "detail_report_url",
        "tri_facility_id_tri", "region_tri", "parent_co_name_tri", "fac_closed_ind_tri",
    ]
    existing_cols = [c for c in keep_cols if c in df.columns]
    index_df = df[existing_cols].rename(columns={"registry_id": "master_id"})
    return index_df, dropped_no_id_count


def write_build_report(
    match_stats: dict,
    state_check: dict,
    coord_check: dict,
    dropped_no_id_count: int,
    three_way_breakdown: dict,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Master Facility Index Build Report (FRS + ECHO + TRI)",
        "",
        "Generated automatically by `build_master_index.py`.",
        "",
        "## FRS/ECHO match statistics (from the two-way join, before TRI is added)",
        "",
        f"- Total rows in FRS+ECHO outer join: {match_stats['total']}",
        f"- Matched in both FRS and ECHO (EXACT_ID, full data): {match_stats['both']}",
        f"- FRS only (no ECHO compliance data): {match_stats['frs_only']}",
        f"- ECHO only (no FRS identity record — unusual, worth investigating if non-trivial): {match_stats['echo_only']}",
        "",
        f"- Rows with NO registry_id at all, excluded from the final index (fixed 2026-09-16, "
        f"see check_duplicate_ids.py): {dropped_no_id_count}",
    ]
    if dropped_no_id_count > 0:
        lines.append(
            "  These rows have no usable identifier and cannot be indexed by one — "
            "excluded rather than mislabeled EXACT_ID or dropped without a count."
        )
    lines += [
        "",
        "## Final three-way source breakdown (FRS + ECHO + TRI, after TRI is added)",
        "",
    ]
    for combo, count in sorted(three_way_breakdown.items()):
        lines.append(f"- {combo or '(none — should not happen)'}: {count}")
    lines += [
        "",
        "**Scope note:** the state-agreement and coordinate-agreement checks below compare "
        "FRS against ECHO only — they were NOT extended to cross-check TRI in this build. "
        "TRI's identity and coordinate data are folded into the index (see coord_source, "
        "which can be 'tri'), but TRI has not been independently QA'd against the other two "
        "sources the way FRS and ECHO were QA'd against each other. This is a stated scope "
        "limitation, not an oversight to be assumed away.",
        "",
        "## State agreement check (FRS vs ECHO, matched rows only)",
        "",
        f"- Checked: {state_check.get('checked', 0)}",
        f"- Agree: {state_check.get('agree', 0)}",
        f"- Disagree: {state_check.get('disagree', 0)}",
    ]
    if state_check.get("disagree_sample"):
        lines.append("")
        lines.append("Sample of disagreements (registry_id, FRS state, ECHO state):")
        for rec in state_check["disagree_sample"]:
            lines.append(f"- {rec}")

    lines.append("")
    lines.append("## Coordinate agreement check (FRS vs ECHO, matched rows with coordinates from both)")
    lines.append("")
    if coord_check.get("checked", 0) > 0:
        for k, v in coord_check.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append(f"- {coord_check.get('note', 'no comparable rows')}")

    out_path.write_text("\n".join(lines))
    logger.info("Wrote build report to %s", out_path)


def main() -> None:
    frs, echo, tri = load_interim_tables()
    logger.info(
        "Loaded FRS interim: %d rows. ECHO interim: %d rows. TRI interim: %d rows.",
        len(frs), len(echo), len(tri),
    )

    two_way = merge_frs_echo(frs, echo)
    match_stats = compute_match_stats(two_way)
    logger.info("FRS/ECHO match stats: %s", match_stats)

    state_check = check_state_agreement(two_way)
    logger.info("State agreement (FRS vs ECHO): %s", state_check)

    coord_check = check_coordinate_agreement(two_way)
    logger.info("Coordinate agreement (FRS vs ECHO): %s", coord_check)

    three_way = merge_third_source(two_way, tri, third_join_col="epa_registry_id", suffix="tri")

    master_index, dropped_no_id_count = build_master_index(three_way)
    if dropped_no_id_count:
        logger.warning(
            "%d rows had no registry_id at all and were excluded from the master index.",
            dropped_no_id_count,
        )

    three_way_breakdown = master_index["sources_present"].value_counts().to_dict()
    logger.info("Final three-way source breakdown: %s", three_way_breakdown)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_facility_index.csv"
    master_index.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(master_index), out_path)

    write_build_report(
        match_stats, state_check, coord_check, dropped_no_id_count,
        three_way_breakdown, VALIDATION_DIR / "master_index_build_report.md",
    )


if __name__ == "__main__":
    main()
