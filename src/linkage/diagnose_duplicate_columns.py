"""
TRACE-ER Explorer — diagnostic: trace the duplicate 'coord_accuracy_value' column.

Usage:
    python src/linkage/diagnose_duplicate_columns.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))

import pandas as pd  # noqa: E402

import build_master_index as bmi  # noqa: E402


def find_duplicate_columns(columns: list[str]) -> dict[str, int]:
    """Pure function: return {name: count} for any column name appearing more than once."""
    counts = Counter(columns)
    return {name: n for name, n in counts.items() if n > 1}


# Fields expected to be fully suffixed (_frs/_echo/_tri) by this point in
# the pipeline.
SUSPECT_BARE_NAMES = ["latitude", "longitude", "coord_accuracy_value", "coord_collect_method", "coord_datum"]


def check_bare_survivors(columns: list[str], names: list[str] = SUSPECT_BARE_NAMES) -> list[str]:
    """Pure function: which of `names` appear, unsuffixed, in `columns`."""
    return [n for n in names if n in columns]


def report_stage(label: str, columns: list[str]) -> None:
    dupes = find_duplicate_columns(columns)
    bare_survivors = check_bare_survivors(columns)
    status_parts = []
    if dupes:
        status_parts.append(f"DUPLICATES: {dupes}")
    if bare_survivors:
        status_parts.append(f"BARE SURVIVOR (unsuffixed, will collide later): {bare_survivors}")
    status = "; ".join(status_parts) if status_parts else "clean"
    print(f"{label}: {len(columns)} columns — {status}")


def main() -> None:
    print(f"pandas version in this environment: {pd.__version__}")
    print()

    print("=== Stage 0: raw interim file headers (before any merge) ===")
    for label, path in [("FRS", bmi.FRS_INTERIM), ("ECHO", bmi.ECHO_INTERIM), ("TRI", bmi.TRI_INTERIM)]:
        if not path.exists():
            print(f"{label}: {path} not found, skipping")
            continue
        with open(path) as f:
            header = f.readline().strip().split(",")
        report_stage(label, header)

    print()
    print("=== Stage 1: after merge_frs_echo (FRS + ECHO only) ===")
    frs, echo, tri = bmi.load_interim_tables()
    two = bmi.merge_frs_echo(frs, echo)
    report_stage("two-way merge", list(two.columns))

    print()
    print("=== Stage 2: after merge_third_source (TRI added) ===")
    three = bmi.merge_third_source(two, tri, third_join_col="epa_registry_id", suffix="tri")
    report_stage("three-way merge", list(three.columns))

    print()
    print("=== Stage 3: inside build_master_index, step by step ===")
    df = three.copy()
    no_id_mask = df["registry_id"].isna()
    df = df[~no_id_mask].copy()
    report_stage("df after dropping null-ID rows (before coordinate selection)", list(df.columns))

    coord_cols = df.apply(bmi.choose_best_coordinate, axis=1)
    report_stage("coord_cols (choose_best_coordinate output, before concat)", list(coord_cols.columns))

    df_concatenated = pd.concat([df, coord_cols], axis=1)
    report_stage("df AFTER concat — this is where the duplicate would first appear", list(df_concatenated.columns))

    print()
    print("=== Stage 4: full build_master_index() output ===")
    index, dropped = bmi.build_master_index(three)
    report_stage("final index", list(index.columns))

    dupes = find_duplicate_columns(list(index.columns))
    if dupes:
        for name in dupes:
            matching = [c for c in index.columns if c == name]
            print(f"\nFound {len(matching)} columns named '{name}'. Inspecting both by position:")
            # Access by integer position since name-based access is ambiguous
            # when duplicate column names exist.
            col_positions = [i for i, c in enumerate(index.columns) if c == name]
            for pos in col_positions:
                col_data = index.iloc[:, pos]
                print(f"  Position {pos}: non-null count = {col_data.notna().sum()} of {len(col_data)}")


if __name__ == "__main__":
    main()