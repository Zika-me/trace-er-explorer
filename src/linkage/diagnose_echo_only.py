"""
TRACE-ER Explorer — diagnostic: investigate 'ECHO only' entities.

This script checks the "ECHO only" registry_ids from the master index
against FRS's FULL, UNFILTERED national extract (not the already
state-filtered interim table) to tell these two cases apart.

Usage:
    python src/linkage/diagnose_echo_only.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from common import logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_INDEX = REPO_ROOT / "data" / "processed" / "master_facility_index.csv"
FRS_NATIONAL_RAW = REPO_ROOT / "data" / "raw" / "frs" / "extracted" / "NATIONAL_SINGLE.CSV"
VALIDATION_DIR = REPO_ROOT / "validation"

TARGET_STATES = ["TX", "PA", "NM", "ME"]


def get_echo_only_ids(master_index: pd.DataFrame) -> list[str]:
    """Pure function: pull the registry_ids that only matched on the ECHO side."""
    return master_index[master_index["sources_present"] == "ECHO"]["master_id"].astype(str).tolist()


def check_against_national_frs(echo_only_ids: list[str], national_frs: pd.DataFrame) -> dict:
    """
    Pure function: for each ECHO-only ID, determine whether FRS has a
    record for it nationally, and if so, under which state. A record
    found under a TARGET state would indicate a bug (it should already
    have been in FRS's filtered subset and matched) — checked
    explicitly rather than assumed impossible.
    """
    national_frs = national_frs.copy()
    national_frs["REGISTRY_ID"] = national_frs["REGISTRY_ID"].astype(str)

    found = national_frs[national_frs["REGISTRY_ID"].isin(echo_only_ids)]
    found_ids = set(found["REGISTRY_ID"])
    not_found_ids = set(echo_only_ids) - found_ids

    state_norm = found["STATE_CODE"].astype(str).str.strip().str.upper()
    found_under_target_state = found[state_norm.isin(TARGET_STATES)]
    found_under_other_state = found[~state_norm.isin(TARGET_STATES)]

    other_state_breakdown = (
        found_under_other_state["STATE_CODE"].astype(str).str.strip().str.upper().value_counts().head(10).to_dict()
    )

    return {
        "total_echo_only": len(echo_only_ids),
        "found_in_national_frs": len(found_ids),
        "not_found_in_national_frs": len(not_found_ids),
        "found_under_target_state": len(found_under_target_state),
        "found_under_other_state": len(found_under_other_state),
        "other_state_breakdown_sample": other_state_breakdown,
        "not_found_sample": list(not_found_ids)[:10],
        "found_under_target_state_sample": found_under_target_state["REGISTRY_ID"].head(10).tolist(),
    }


def write_report(result: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ECHO-Only Entities Diagnostic Report",
        "",
        "Checks whether 'ECHO only' registry_ids from the master index truly",
        "have no FRS record anywhere, or exist in FRS under a different state",
        "than ECHO reports — which would explain the exclusion as a filtering",
        "artifact rather than a genuine data gap.",
        "",
        f"- Total ECHO-only entities: {result['total_echo_only']}",
        f"- Found in FRS's full national extract: {result['found_in_national_frs']}",
        f"- NOT found in FRS's full national extract at all: {result['not_found_in_national_frs']}",
        f"- Found under a TARGET state (TX/PA/NM/ME) — should be 0; nonzero means a bug in the state filter or join, not a data characteristic: {result['found_under_target_state']}",
        f"- Found under a different (non-target) state: {result['found_under_other_state']}",
        "",
        f"Sample of the non-target states found: {result['other_state_breakdown_sample']}",
        "",
    ]
    if result["found_under_target_state_sample"]:
        lines.append(
            f"**INVESTIGATE — found under a target state, which should not happen: "
            f"{result['found_under_target_state_sample']}**"
        )
        lines.append("")
    lines.append(f"Sample of registry_ids not found in FRS at all: {result['not_found_sample']}")
    out_path.write_text("\n".join(lines))
    logger.info("Wrote diagnostic report to %s", out_path)


def main() -> None:
    if not MASTER_INDEX.exists():
        raise FileNotFoundError(f"{MASTER_INDEX} not found. Run build_master_index.py first.")
    if not FRS_NATIONAL_RAW.exists():
        raise FileNotFoundError(
            f"{FRS_NATIONAL_RAW} not found. This is FRS's raw extracted national file from "
            f"fetch_frs.py — if data/raw/frs/ was deleted, re-run fetch_frs.py first."
        )

    master_index = pd.read_csv(MASTER_INDEX, dtype=str, low_memory=False)
    echo_only_ids = get_echo_only_ids(master_index)
    logger.info("Found %d ECHO-only entities to check.", len(echo_only_ids))

    national_frs = pd.read_csv(
        FRS_NATIONAL_RAW, dtype=str, usecols=["REGISTRY_ID", "STATE_CODE"], low_memory=False
    )
    logger.info("Loaded %d rows from FRS national extract (REGISTRY_ID, STATE_CODE only).", len(national_frs))

    result = check_against_national_frs(echo_only_ids, national_frs)
    logger.info("Diagnostic result: %s", result)

    write_report(result, VALIDATION_DIR / "echo_only_diagnostic_report.md")


if __name__ == "__main__":
    main()
