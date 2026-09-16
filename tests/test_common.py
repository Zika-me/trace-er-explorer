import csv
import hashlib
import zipfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ingest"))
import common  # noqa: E402


def test_sha256_checksum_matches_hashlib(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"trace-er explorer test content")
    expected = hashlib.sha256(b"trace-er explorer test content").hexdigest()
    assert common.sha256_checksum(f) == expected


def test_sha256_checksum_is_deterministic_across_chunk_sizes(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"x" * 5000)
    a = common.sha256_checksum(f, chunk_size=64)
    b = common.sha256_checksum(f, chunk_size=4096)
    assert a == b


def test_detect_column_matches_case_insensitively():
    columns = ["Facility_Name", "REGISTRY_ID", "  Latitude83  "]
    assert common.detect_column(columns, ["facility_name"]) == "Facility_Name"
    assert common.detect_column(columns, ["registry_id", "frs_id"]) == "REGISTRY_ID"
    assert common.detect_column(columns, ["latitude83"]) == "  Latitude83  "


def test_detect_column_returns_none_when_missing():
    columns = ["A", "B", "C"]
    assert common.detect_column(columns, ["D", "E"]) is None


def test_require_column_raises_with_actionable_message():
    columns = ["A", "B"]
    with pytest.raises(ValueError) as exc_info:
        common.require_column(columns, ["Z"], label="widget_id")
    message = str(exc_info.value)
    assert "widget_id" in message
    assert "A" in message and "B" in message  # actual columns listed for debugging


def test_unzip_file_extracts_expected_contents(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "data.csv").write_text("a,b\n1,2\n")

    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(src_dir / "data.csv", arcname="data.csv")

    extract_dir = tmp_path / "extracted"
    extracted = common.unzip_file(zip_path, extract_dir)

    assert len(extracted) == 1
    assert (extract_dir / "data.csv").exists()
    assert (extract_dir / "data.csv").read_text() == "a,b\n1,2\n"


def test_unzip_file_rejects_zip_slip(tmp_path):
    # Build a malicious zip whose entry tries to escape the extraction dir.
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "should not escape")

    extract_dir = tmp_path / "safe_extract"
    with pytest.raises(ValueError):
        common.unzip_file(zip_path, extract_dir)


def test_discover_csv_files_finds_nested_csvs(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "top.csv").write_text("x")
    (tmp_path / "sub" / "nested.CSV").write_text("y")
    (tmp_path / "not_a_csv.txt").write_text("z")

    found = common.discover_csv_files(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["nested.CSV", "top.csv"]


def test_resolve_columns_generic_required_and_optional():
    columns = ["REGISTRY_ID", "FAC_NAME", "SOME_OTHER_FIELD"]
    candidates = {
        "registry_id": ["REGISTRY_ID"],
        "facility_name": ["FAC_NAME", "PRIMARY_NAME"],
        "county": ["COUNTY_NAME"],  # not present, optional
    }
    resolved = common.resolve_columns(columns, candidates, required_fields=["registry_id", "facility_name"])
    assert resolved["registry_id"] == "REGISTRY_ID"
    assert resolved["facility_name"] == "FAC_NAME"
    assert resolved["county"] is None


def test_resolve_columns_generic_raises_for_missing_required_field():
    columns = ["A", "B"]
    candidates = {"widget_id": ["WIDGET_ID"]}
    with pytest.raises(ValueError):
        common.resolve_columns(columns, candidates, required_fields=["widget_id"])


def test_filter_and_standardize_by_state_excludes_before_checking_coords():
    import pandas as pd

    df = pd.DataFrame(
        {
            "ID": ["1", "2", "3"],
            "LAT": ["30.0", None, "40.0"],
            "LON": ["-97.0", "-75.0", None],
            "ST": ["TX", "PA", "CA"],  # CA is out of scope
        }
    )
    resolved = {"registry_id": "ID", "latitude": "LAT", "longitude": "LON", "state": "ST"}
    standardized, stats = common.filter_and_standardize_by_state(df, resolved, target_states=["TX", "PA"])

    # CA excluded entirely — its missing longitude must NOT be counted
    assert stats["accepted_rows"] == 2
    assert stats["missing_coords"] == 1  # only PA's missing latitude counts
    assert set(standardized["state"]) == {"TX", "PA"}


def test_append_source_volume_log_writes_header_once(tmp_path):
    log_path = tmp_path / "log.csv"
    common.append_source_volume_log(log_path, {"source": "epa_frs", "downloaded_rows": 100})
    common.append_source_volume_log(log_path, {"source": "epa_frs", "downloaded_rows": 200})

    with open(log_path) as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["downloaded_rows"] == "100"
    assert rows[1]["downloaded_rows"] == "200"
    # header fields present even for keys we didn't pass
    assert "final_unique_entities" in rows[0]
