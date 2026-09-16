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
MASTER_INDEX = REPO_ROOT / "data" / "processed" / "master_facility_index.csv"
VALIDATION_DIR = REPO_ROOT / "validation"


def check_duplicate_ids(df: pd.DataFrame, id_col: str) -> dict:
    """
    Pure function: quantify duplicate key rows in a dataframe.
    extra_rows_from_duplicates should always equal total_rows minus
    unique_ids exactly — this is a mathematical identity, checked by
    a dedicated test rather than assumed.
    """
    ids = df[id_col].astype(str)
    counts = ids.value_counts()
    duplicated = counts[counts > 1]
    return {
        "total_rows": len(df),
        "unique_ids": int(ids.nunique()),
        "duplicate_id_count": int(len(duplicated)),
        "extra_rows_from_duplicates": int((duplicated - 1).sum()) if len(duplicated) else 0,
        "sample_duplicated_ids": duplicated.head(10).to_dict(),
    }


def get_rows_for_id(df: pd.DataFrame, id_col: str, target_id: str) -> pd.DataFrame:
    """Return every row sharing a given ID, for visual before/after inspection."""
    return df[df[id_col].astype(str) == str(target_id)]


def write_report(
    frs_result: dict, echo_result: dict, master_result: dict, sample_text: str, out_path: Path
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Duplicate ID Diagnostic Report",
        "",
        "Triggered by an arithmetic gap in the ECHO-only diagnostic (1,368 rows",
        "vs 928 unique IDs found+not_found). Checks whether duplicate keys exist",
        "in FRS, ECHO, or the master index — and, if in FRS or ECHO, whether they",
        "could also be inflating the 'both' and 'frs_only' match counts, not just",
        "the ECHO-only bucket where the gap was first noticed.",
        "",
    ]
    for label, result in [
        ("FRS interim table (key: registry_id)", frs_result),
        ("ECHO interim table (key: registry_id)", echo_result),
        ("Master facility index (key: master_id)", master_result),
    ]:
        lines.append(f"## {label}")
        lines.append("")
        for k, v in result.items():
            lines.append(f"- {k}: {v}")
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
    for path in [FRS_INTERIM, ECHO_INTERIM, MASTER_INDEX]:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run the earlier pipeline steps first.")

    frs = pd.read_csv(FRS_INTERIM, dtype=str, low_memory=False)
    echo = pd.read_csv(ECHO_INTERIM, dtype=str, low_memory=False)
    master = pd.read_csv(MASTER_INDEX, dtype=str, low_memory=False)

    frs_result = check_duplicate_ids(frs, "registry_id")
    echo_result = check_duplicate_ids(echo, "registry_id")
    master_result = check_duplicate_ids(master, "master_id")

    logger.info("FRS duplicate check: %s", frs_result)
    logger.info("ECHO duplicate check: %s", echo_result)
    logger.info("Master index duplicate check: %s", master_result)

    sample_text = ""
    for label, df, result, id_col in [
        ("FRS", frs, frs_result, "registry_id"),
        ("ECHO", echo, echo_result, "registry_id"),
    ]:
        if result["sample_duplicated_ids"]:
            first_dup_id = list(result["sample_duplicated_ids"].keys())[0]
            rows = get_rows_for_id(df, id_col, first_dup_id)
            sample_text += f"\n### {label} — all rows sharing ID {first_dup_id}\n\n```\n{rows.to_string()}\n```\n"

    write_report(frs_result, echo_result, master_result, sample_text, VALIDATION_DIR / "duplicate_id_diagnostic_report.md")


if __name__ == "__main__":
    main()
