"""
TRACE-ER Explorer — Step 3: Master Facility Index (FRS + ECHO).

Joins the standardized FRS and ECHO interim tables on registry_id (the
one identifier both sources natively share) and produces an
analysis-ready master facility index, plus a QA report.


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

REPO_ROOT = Path(__file__).resolve().parents[2]
FRS_INTERIM = REPO_ROOT / "data" / "interim" / "frs_facility_site.csv"
ECHO_INTERIM = REPO_ROOT / "data" / "interim" / "echo_facility_summary.csv"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
VALIDATION_DIR = REPO_ROOT / "validation"

# Coordinate-agreement thresholds used only for QA reporting bands —
# not a pass/fail gate, just a way to summarize a distribution.
AGREEMENT_BANDS_KM = [1, 5, 10, 50]


def load_interim_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    dtype=str is not optional here. Re-reading a written CSV without
    forcing string dtype risks pandas silently inferring registry_id
    as float64 (e.g. "110072186793" -> 110072186793.0 -> back to
    "110072186793.0" on comparison)
    """
    if not FRS_INTERIM.exists():
        raise FileNotFoundError(
            f"{FRS_INTERIM} not found. Run src/ingest/fetch_frs.py first."
        )
    if not ECHO_INTERIM.exists():
        raise FileNotFoundError(
            f"{ECHO_INTERIM} not found. Run src/ingest/fetch_echo.py first."
        )
    frs = pd.read_csv(FRS_INTERIM, dtype=str, low_memory=False)
    echo = pd.read_csv(ECHO_INTERIM, dtype=str, low_memory=False)
    return frs, echo


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
    When both sources have a coordinate for the same entity, prefer
    whichever has the lower (better) coord_accuracy_value. When only
    one side has a usable coordinate, use that one. When neither
    side has a numeric accuracy value but both have coordinates,
    default to FRS (the identity anchor) rather than guessing.
    """
    lat_frs, lon_frs = row.get("latitude_frs"), row.get("longitude_frs")
    lat_echo, lon_echo = row.get("latitude_echo"), row.get("longitude_echo")
    acc_frs = row.get("coord_accuracy_value_frs")
    acc_echo = row.get("coord_accuracy_value_echo")

    has_frs = pd.notna(lat_frs) and pd.notna(lon_frs)
    has_echo = pd.notna(lat_echo) and pd.notna(lon_echo)

    if has_frs and not has_echo:
        source = "frs"
    elif has_echo and not has_frs:
        source = "echo"
    elif has_frs and has_echo:
        try:
            acc_frs_f = float(acc_frs) if pd.notna(acc_frs) else None
            acc_echo_f = float(acc_echo) if pd.notna(acc_echo) else None
        except (ValueError, TypeError):
            acc_frs_f = acc_echo_f = None

        if acc_frs_f is not None and acc_echo_f is not None:
            source = "frs" if acc_frs_f <= acc_echo_f else "echo"
        elif acc_frs_f is not None:
            source = "frs"
        elif acc_echo_f is not None:
            source = "echo"
        else:
            source = "frs"  # neither has an accuracy value — default to the identity anchor
    else:
        source = None

    if source == "frs":
        return pd.Series({
            "latitude": lat_frs, "longitude": lon_frs,
            "coord_accuracy_value": acc_frs, "coord_source": "frs",
        })
    elif source == "echo":
        return pd.Series({
            "latitude": lat_echo, "longitude": lon_echo,
            "coord_accuracy_value": acc_echo, "coord_source": "echo",
        })
    else:
        return pd.Series({
            "latitude": None, "longitude": None,
            "coord_accuracy_value": None, "coord_source": None,
        })


def build_master_index(merged: pd.DataFrame) -> pd.DataFrame:
    """
    Build the final standardized master index from the merged frame.
    """
    df = merged.copy()

    coord_cols = df.apply(choose_best_coordinate, axis=1)
    df = pd.concat([df, coord_cols], axis=1)

    df["sources_present"] = df["_merge"].map({
        "both": "FRS,ECHO", "left_only": "FRS", "right_only": "ECHO",
    })
    df["source_count"] = df["_merge"].map({"both": 2, "left_only": 1, "right_only": 1})

    # Every entity here shares EPA's national REGISTRY_ID
    df["linkage_confidence"] = "EXACT_ID"

    # Prefer FRS for identity fields
    def coalesce(a, b):
        return df[a].where(df[a].notna(), df[b]) if a in df.columns and b in df.columns else df.get(a, df.get(b))

    df["facility_name"] = coalesce("facility_name_frs", "facility_name_echo")
    df["state"] = coalesce("state_frs", "state_echo")
    df["county"] = coalesce("county_frs", "county_echo")

    keep_cols = [
        "registry_id", "facility_name", "address", "city", "postal_code", "state", "county",
        "latitude", "longitude", "coord_accuracy_value", "coord_source",
        "sources_present", "source_count", "linkage_confidence",
        "naics_codes_raw_frs", "sic_codes_raw_frs", "programs_raw", "site_type", "huc_code",
        "fac_inspection_count", "fac_formal_action_count", "fac_informal_count",
        "fac_total_penalties", "fac_qtrs_with_nc", "fac_compliance_status", "fac_snc_flag",
        "caa_hpv_flag", "air_flag", "npdes_flag", "sdwis_flag", "rcra_flag", "tri_flag", "ghg_flag",
        "detail_report_url",
    ]
    existing_cols = [c for c in keep_cols if c in df.columns]
    return df[existing_cols].rename(columns={"registry_id": "master_id"})


def write_build_report(match_stats: dict, state_check: dict, coord_check: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Master Facility Index Build Report (FRS + ECHO)",
        "",
        "Generated automatically by `build_master_index.py`.",
        "",
        "## Match statistics",
        "",
        f"- Total rows in outer join: {match_stats['total']}",
        f"- Matched in both FRS and ECHO (EXACT_ID, full data): {match_stats['both']}",
        f"- FRS only (no ECHO compliance data): {match_stats['frs_only']}",
        f"- ECHO only (no FRS identity record — unusual, worth investigating if non-trivial): {match_stats['echo_only']}",
        "",
        "## State agreement check (matched rows only)",
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
    lines.append("## Coordinate agreement check (matched rows with coordinates from both sources)")
    lines.append("")
    if coord_check.get("checked", 0) > 0:
        for k, v in coord_check.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append(f"- {coord_check.get('note', 'no comparable rows')}")

    out_path.write_text("\n".join(lines))
    logger.info("Wrote build report to %s", out_path)


def main() -> None:
    frs, echo = load_interim_tables()
    logger.info("Loaded FRS interim: %d rows. ECHO interim: %d rows.", len(frs), len(echo))

    merged = merge_frs_echo(frs, echo)
    match_stats = compute_match_stats(merged)
    logger.info("Match stats: %s", match_stats)

    state_check = check_state_agreement(merged)
    logger.info("State agreement: %s", state_check)

    coord_check = check_coordinate_agreement(merged)
    logger.info("Coordinate agreement: %s", coord_check)

    master_index = build_master_index(merged)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_facility_index.csv"
    master_index.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(master_index), out_path)

    write_build_report(match_stats, state_check, coord_check, VALIDATION_DIR / "master_index_build_report.md")


if __name__ == "__main__":
    main()
