from pathlib import Path

import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ingest"))
import fetch_echo  # noqa: E402
import common  # noqa: E402


def test_resolve_echo_core_columns_happy_path():
    columns = [
        "REGISTRY_ID", "FAC_NAME", "FAC_STATE", "FAC_LAT", "FAC_LONG", "FAC_COUNTY",
        "AIR_FLAG", "NPDES_FLAG", "SOME_PENALTY_FIELD",
    ]
    resolved = fetch_echo.resolve_echo_core_columns(columns)
    assert resolved["registry_id"] == "REGISTRY_ID"
    assert resolved["facility_name"] == "FAC_NAME"
    assert resolved["state"] == "FAC_STATE"
    assert resolved["latitude"] == "FAC_LAT"
    assert resolved["longitude"] == "FAC_LONG"
    assert resolved["county"] == "FAC_COUNTY"


def test_resolve_echo_core_columns_raises_when_registry_id_missing():
    columns = ["FAC_NAME", "FAC_STATE"]
    with pytest.raises(ValueError) as exc_info:
        fetch_echo.resolve_echo_core_columns(columns)
    assert "registry_id" in str(exc_info.value)


def test_filter_and_standardize_echo_filters_target_states():
    df = pd.DataFrame(
        {
            "REGISTRY_ID": ["1", "2", "3"],
            "FAC_NAME": ["A", "B", "C"],
            "FAC_STATE": ["TX", "CA", "PA"],
            "FAC_LAT": ["29.0", "34.0", "40.0"],
            "FAC_LONG": ["-95.0", "-118.0", "-79.0"],
        }
    )
    resolved = fetch_echo.resolve_echo_core_columns(list(df.columns))
    standardized, stats = fetch_echo.filter_and_standardize(df, resolved)
    assert stats["accepted_rows"] == 2  # CA excluded
    assert set(standardized["state"]) == {"TX", "PA"}


def test_discover_columns_by_keyword_finds_expected_buckets():
    columns = [
        "AIR_FLAG", "NPDES_FLAG", "CAA_INSPECTION_COUNT", "CWA_VIOLATION_COUNT",
        "RCRA_FORMAL_ACTION_COUNT", "CAA_INFORMAL_COUNT", "FAC_TOTAL_PENALTIES",
        "CAA_3YR_COMPL_QTRS_HISTORY", "UNRELATED_COLUMN",
    ]
    buckets = {
        "program_flags": ["FLAG"],
        "inspections": ["INSPECTION"],
        "violations": ["VIOLATION"],
        "enforcement": ["FORMAL", "INFORMAL"],
        "penalties": ["PENALT"],
        "compliance_history_qtrs": ["COMPL", "QTR"],
    }
    result = common.discover_columns_by_keyword(columns, buckets)
    assert result["program_flags"] == ["AIR_FLAG", "NPDES_FLAG"]
    assert result["inspections"] == ["CAA_INSPECTION_COUNT"]
    assert result["violations"] == ["CWA_VIOLATION_COUNT"]
    assert set(result["enforcement"]) == {"RCRA_FORMAL_ACTION_COUNT", "CAA_INFORMAL_COUNT"}
    assert result["penalties"] == ["FAC_TOTAL_PENALTIES"]
    assert result["compliance_history_qtrs"] == ["CAA_3YR_COMPL_QTRS_HISTORY"]
    assert "UNRELATED_COLUMN" not in [c for matches in result.values() for c in matches]


def test_discover_columns_by_keyword_empty_bucket_when_nothing_matches():
    columns = ["A", "B", "C"]
    buckets = {"penalties": ["PENALT"]}
    result = common.discover_columns_by_keyword(columns, buckets)
    assert result["penalties"] == []


def test_write_discovery_report_creates_readable_file(tmp_path):
    discovery = {"penalties": ["FAC_TOTAL_PENALTIES"], "inspections": []}
    all_columns = ["REGISTRY_ID", "FAC_TOTAL_PENALTIES"]
    out_path = tmp_path / "report.md"
    fetch_echo.write_discovery_report(discovery, all_columns, out_path)
    content = out_path.read_text()
    assert "FAC_TOTAL_PENALTIES" in content
    assert "penalties" in content
    assert "REGISTRY_ID" in content  # full column list included
