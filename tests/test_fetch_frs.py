from pathlib import Path

import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ingest"))
import fetch_frs  # noqa: E402


def test_resolve_frs_columns_happy_path():
    # A plausible real header row using the most likely candidate names.
    columns = [
        "REGISTRY_ID",
        "PRIMARY_NAME",
        "LATITUDE83",
        "LONGITUDE83",
        "STATE_CODE",
        "COUNTY_NAME",
        "PRIMARY_NAICS_CODE",
        "PRIMARY_SIC_CODE",
        "SOME_UNRELATED_COLUMN",
    ]
    resolved = fetch_frs.resolve_frs_columns(columns)
    assert resolved["registry_id"] == "REGISTRY_ID"
    assert resolved["facility_name"] == "PRIMARY_NAME"
    assert resolved["latitude"] == "LATITUDE83"
    assert resolved["longitude"] == "LONGITUDE83"
    assert resolved["state"] == "STATE_CODE"
    assert resolved["county"] == "COUNTY_NAME"


def test_resolve_frs_columns_alternate_names_still_match():
    # A plausible alternate header row, second-choice candidates.
    columns = ["FRS_ID", "FAC_NAME", "FAC_LAT", "FAC_LONG", "FAC_STATE"]
    resolved = fetch_frs.resolve_frs_columns(columns)
    assert resolved["registry_id"] == "FRS_ID"
    assert resolved["facility_name"] == "FAC_NAME"
    assert resolved["state"] == "FAC_STATE"
    # optional fields not present should resolve to None, not raise
    assert resolved["county"] is None
    assert resolved["naics_codes_raw"] is None


def test_resolve_frs_columns_raises_when_required_field_missing():
    # No plausible state column anywhere in this header row.
    columns = ["REGISTRY_ID", "PRIMARY_NAME", "LATITUDE83", "LONGITUDE83"]
    with pytest.raises(ValueError) as exc_info:
        fetch_frs.resolve_frs_columns(columns)
    assert "state" in str(exc_info.value)


def test_resolve_frs_columns_matches_confirmed_real_schema():
    # This is the ACTUAL header row from a real FRS national_single.csv
    # sample, provided by the project owner on 2026-09-14. This test
    # exists so no future edit to COLUMN_CANDIDATES can silently break
    # a mapping that's already been confirmed against ground truth.
    real_header = [
        "FRS_FACILITY_DETAIL_REPORT_URL", "REGISTRY_ID", "PRIMARY_NAME", "LOCATION_ADDRESS",
        "SUPPLEMENTAL_LOCATION", "CITY_NAME", "COUNTY_NAME", "FIPS_CODE", "STATE_CODE",
        "STATE_NAME", "COUNTRY_NAME", "POSTAL_CODE", "FEDERAL_FACILITY_CODE",
        "FEDERAL_AGENCY_NAME", "TRIBAL_LAND_CODE", "TRIBAL_LAND_NAME",
        "CONGRESSIONAL_DIST_NUM", "CENSUS_BLOCK_CODE", "HUC_CODE", "EPA_REGION_CODE",
        "SITE_TYPE_NAME", "LOCATION_DESCRIPTION", "CREATE_DATE", "UPDATE_DATE",
        "US_MEXICO_BORDER_IND", "PGM_SYS_ACRNMS", "INTEREST_TYPES", "NAICS_CODES",
        "NAICS_CODE_DESCRIPTIONS", "SIC_CODES", "SIC_CODE_DESCRIPTIONS", "LATITUDE83",
        "LONGITUDE83", "CONVEYOR", "COLLECT_DESC", "ACCURACY_VALUE", "REF_POINT_DESC",
        "HDATUM_DESC", "SOURCE_DESC",
    ]
    resolved = fetch_frs.resolve_frs_columns(real_header)
    assert resolved["registry_id"] == "REGISTRY_ID"
    assert resolved["facility_name"] == "PRIMARY_NAME"
    assert resolved["latitude"] == "LATITUDE83"
    assert resolved["longitude"] == "LONGITUDE83"
    assert resolved["state"] == "STATE_CODE"
    assert resolved["county"] == "COUNTY_NAME"
    assert resolved["naics_codes_raw"] == "NAICS_CODES"
    assert resolved["sic_codes_raw"] == "SIC_CODES"
    assert resolved["address"] == "LOCATION_ADDRESS"
    assert resolved["city"] == "CITY_NAME"
    assert resolved["postal_code"] == "POSTAL_CODE"
    assert resolved["programs_raw"] == "PGM_SYS_ACRNMS"
    assert resolved["site_type"] == "SITE_TYPE_NAME"
    assert resolved["huc_code"] == "HUC_CODE"
    assert resolved["coord_accuracy_value"] == "ACCURACY_VALUE"
    assert resolved["coord_collect_method"] == "COLLECT_DESC"
    assert resolved["coord_reference_point"] == "REF_POINT_DESC"
    assert resolved["coord_datum"] == "HDATUM_DESC"


def test_filter_and_standardize_filters_target_states_and_renames():
    df = pd.DataFrame(
        {
            "REGISTRY_ID": ["1", "2", "3", "4", "5"],
            "PRIMARY_NAME": ["A Corp", "B Inc", "C LLC", "D Co", "E Ltd"],
            "LATITUDE83": ["30.1", "40.2", None, "44.0", "36.0"],
            "LONGITUDE83": ["-97.1", "-75.2", "-106.0", None, "-119.0"],
            # lowercase 'me' should still match; CA is not a target state and
            # must be excluded BEFORE the coordinate check ever looks at it
            "STATE_CODE": ["TX", "PA", "NM", "me", "CA"],
        }
    )
    resolved = fetch_frs.resolve_frs_columns(list(df.columns))
    standardized, stats = fetch_frs.filter_and_standardize(df, resolved)

    # CA should be excluded; TX, PA, NM, ME (case-insensitive) retained
    assert stats["accepted_rows"] == 4
    assert "registry_id" in standardized.columns
    assert "facility_name" in standardized.columns
    assert set(standardized["state"].str.upper()) == {"TX", "PA", "NM", "ME"}

    # of the 4 ACCEPTED rows: NM is missing latitude, ME is missing longitude
    assert stats["missing_coords"] == 2

    assert stats["state_breakdown"]["TX"] == 1
    assert stats["state_breakdown"]["ME"] == 1


def test_filter_and_standardize_marks_all_missing_when_no_coord_columns():
    df = pd.DataFrame(
        {
            "REGISTRY_ID": ["1", "2"],
            "PRIMARY_NAME": ["A Corp", "B Inc"],
            "STATE_CODE": ["TX", "PA"],
        }
    )
    resolved = fetch_frs.resolve_frs_columns(list(df.columns))
    standardized, stats = fetch_frs.filter_and_standardize(df, resolved)
    # No lat/lon columns at all -> treated as unknown/missing, never as present
    assert stats["missing_coords"] == stats["accepted_rows"] == 2
