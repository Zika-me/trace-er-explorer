"""
TRACE-ER Explorer — diagnostic: check for duplicate IDs.

This matters well beyond the ECHO-only bucket: if either source has
duplicate keys for entities that DO match both sources, the "both"
and "frs_only" counts from build_master_index.py could also be
inflated. This script checks all three files (FRS interim, ECHO
interim, and the master index itself) rather than assuming the
problem is confined to where it was first noticed.

Usage:
    python src/linkage/check_duplicate_ids.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from common import logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FRS_INTERIM = REPO_ROOT / "data" / "interim" / "frs_facility_site.csv"
ECHO_INTERIM = REPO_ROOT / "data" / "interim" / "echo_facility_summary.csv"
TRI_INTERIM = REPO_ROOT / "data" / "interim" / "tri_facility.csv"
MASTER_INDEX = REPO_ROOT / "data" / "processed" / "master_facility_index.csv"
VALIDATION_DIR = REPO_ROOT / "validation"


def check_duplicate_ids(df: pd.DataFrame, id_col: str) -> dict:
    """
    Pure function: quantify duplicate key rows in a dataframe.
    extra_rows_from_duplicates should always equal total_rows minus
    unique_ids exactly — this is a mathematical identity, checked by
    a dedicated test rather than assumed.
    """
    total_rows = len(df)
    raw = df[id_col]
    null_id_count = int(raw.isna().sum())

    non_null = raw.dropna().astype(str)
    counts = non_null.value_counts()
    duplicated = counts[counts > 1]
    unique_non_null_ids = int(non_null.nunique())
    extra_rows_from_duplicates = int((duplicated - 1).sum()) if len(duplicated) else 0

    accounted_rows = null_id_count + unique_non_null_ids + extra_rows_from_duplicates
    assert accounted_rows == total_rows, (
        f"Accounting identity failed: {null_id_count} + {unique_non_null_ids} + "
        f"{extra_rows_from_duplicates} = {accounted_rows}, expected {total_rows}. "
        f"This should be mathematically impossible — investigate immediately."
    )

    return {
        "total_rows": total_rows,
        "null_id_count": null_id_count,
        "unique_non_null_ids": unique_non_null_ids,
        "duplicate_id_count": int(len(duplicated)),
        "extra_rows_from_duplicates": extra_rows_from_duplicates,
        "sample_duplicated_ids": duplicated.head(10).to_dict(),
    }


def get_rows_for_id(df: pd.DataFrame, id_col: str, target_id: str) -> pd.DataFrame:
    """Return every row sharing a given ID, for visual before/after inspection."""
    return df[df[id_col].astype(str) == str(target_id)]


def write_report(results: list[tuple[str, dict]], sample_text: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Duplicate ID Diagnostic Report",
        "",
        "Checks whether duplicate keys exist in FRS, ECHO, TRI, or the master",
        "index — originally triggered by the ECHO-only 440-row gap (which turned",
        "out to be null IDs, not duplicates), extended to TRI after",
        "a real 3-way master index build showed a 40-row gap unexplained by the",
        "null-ID fix alone.",
        "",
    ]
    for label, result in results:
        lines.append(f"## {label}")
        lines.append("")
        for k, v in result.items():
            lines.append(f"- {k}: {v}")
        if result["null_id_count"] > 0:
            lines.append(
                f"  **{result['null_id_count']} rows have a BLANK/missing ID — these have "
                f"no usable identifier at all, which is different from and likely more "
                f"important than duplication.**"
            )
        if result["duplicate_id_count"] > 0:
            lines.append(
                f"  **{result['duplicate_id_count']} distinct IDs appear more than once, "
                f"accounting for {result['extra_rows_from_duplicates']} extra rows.**"
            )
        lines.append("")

    if sample_text:
        lines.append("## Sample duplicate rows (for visual inspection)")
        lines.append("")
        lines.append(sample_text)

    out_path.write_text("\n".join(lines))
    logger.info("Wrote duplicate diagnostic report to %s", out_path)


def main() -> None:
    for path in [FRS_INTERIM, ECHO_INTERIM, TRI_INTERIM, MASTER_INDEX]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run the earlier pipeline steps first.")

    frs = pd.read_csv(FRS_INTERIM, dtype=str, low_memory=False)
    echo = pd.read_csv(ECHO_INTERIM, dtype=str, low_memory=False)
    tri = pd.read_csv(TRI_INTERIM, dtype=str, low_memory=False)
    master = pd.read_csv(MASTER_INDEX, dtype=str, low_memory=False)

    sources = [
        ("FRS interim table (key: registry_id)", frs, "registry_id"),
        ("ECHO interim table (key: registry_id)", echo, "registry_id"),
        ("TRI interim table (key: epa_registry_id)", tri, "epa_registry_id"),
        ("Master facility index (key: master_id)", master, "master_id"),
    ]

    results = []
    for label, df, id_col in sources:
        result = check_duplicate_ids(df, id_col)
        logger.info("%s duplicate check: %s", label, result)
        results.append((label, result))

    sample_text = ""
    for (label, df, id_col), (_, result) in zip(sources, results):
        if result["sample_duplicated_ids"]:
            first_dup_id = list(result["sample_duplicated_ids"].keys())[0]
            rows = get_rows_for_id(df, id_col, first_dup_id)
            sample_text += f"\n### {label} — all rows sharing ID {first_dup_id}\n\n```\n{rows.to_string()}\n```\n"

    write_report(results, sample_text, VALIDATION_DIR / "duplicate_id_diagnostic_report.md")


if __name__ == "__main__":
    main()
