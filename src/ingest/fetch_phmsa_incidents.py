"""
Downloads the PHMSA Pipeline Safety Flagged Incidents ZIP, normalises all
five pipeline system types (Gas Distribution, Gas Transmission & Gathering,
Hazardous Liquid, LNG, Gas Gathering Type-R), filters to the TRACE-ER
study states and period, and produces:

"""
from __future__ import annotations

import csv
import importlib
import logging
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _ensure_openpyxl() -> None:
    try:
        importlib.import_module("openpyxl")
    except ImportError:
        log.info("openpyxl not found — installing into active environment...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "openpyxl", "-q"],
        )
        log.info("openpyxl installed.")

_ensure_openpyxl()

import pandas as pd  # noqa: E402 — imported after openpyxl is guaranteed



BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

ZIP_URL      = (
    "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/"
    "pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
)
RAW_DIR      = DATA_DIR / "raw" / "phmsa"
ZIP_PATH     = RAW_DIR / "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
EXTRACT_DIR  = RAW_DIR / "extracted"
INTERIM_OUT  = DATA_DIR / "interim"  / "phmsa_incidents.csv"
COUNTY_OUT   = DATA_DIR / "processed" / "phmsa_county_features.csv"
MASTER_IN    = DATA_DIR / "processed" / "master_facility_index_with_rrc_features.csv"
MASTER_OUT   = DATA_DIR / "processed" / "master_facility_index_with_phmsa_features.csv"
VOL_LOG      = BASE_DIR / "validation" / "source_volume_log.csv"

TARGET_STATES = {"TX", "PA", "NM", "ME"}
YEAR_MIN      = 2019
YEAR_MAX      = 2024

# Map filename fragments (lowercase) - pipeline system type tag.
# Checked in order; first match wins.
SYSTEM_TYPE_PATTERNS: list[tuple[str, str]] = [
    # Short PHMSA filename prefixes — checked first so gd*/gtgg*/hl* match correctly
    ("gtggungs",         "GT"),   # Gas T&G + Unregulated Gas Systems
    ("gtgg",             "GT"),   # Gas Transmission & Gathering
    ("gd",               "GD"),   # Gas Distribution
    ("hl",               "HL"),   # Hazardous Liquid
    ("lng",              "LNG"),  # LNG Facilities
    # Longer words as fallback for differently named future files
    ("gas_dist",         "GD"),
    ("distribution",     "GD"),
    ("gas_trans",        "GT"),
    ("transmission",     "GT"),
    ("hazardous_liquid", "HL"),
    ("gathering",        "GG"),
]

# For each semantic field, ordered list of possible raw column names.
# Column resolution is case-insensitive; first match wins.
COLUMN_ALIASES: dict[str, list[str]] = {
    "year": [
        "IYEAR", "YEAR", "INCIDENT_YEAR", "REPORT_YEAR",
        "LOCAL_DATETIME",           # fallback: 4-digit year extracted by regex
    ],
    "state": [
        "STATE", "LOCATION_STATE_ABBREVIATION", "STATE_ABBREVIATION",
        "REPORT_STATE", "FACILITY_STATE",          # LNG Facilities form
        "ONSHORE_STATE_ABBREVIATION",       # GT/HL 2010-present forms
    ],
    "county": [
        "COUNTY_PARISH_NAME", "COUNTY", "COUNTY_NAME",
        "LOCATION_COUNTY", "PARISH",
        "ONSHORE_COUNTY_NAME",   # GT/HL 2010-present forms
        "LOCATION_COUNTY_NAME",  # GD 2010-present form
    ],
    "operator_name": ["OPERATOR_NAME", "OPNAME", "OPERATOR"],
    "operator_id":   ["OPERATOR_ID", "OPID"],
    "latitude":      ["LOCATION_LATITUDE", "LATITUDE", "FACILITY_LATITUDE"],
    "longitude":     ["LOCATION_LONGITUDE", "LONGITUDE", "FACILITY_LONGITUDE"],
    "cause":         ["CAUSE", "FLAGGED_CAUSE", "CAUSE_CATEGORY"],
    "subcause":      ["SUBCAUSE", "FLAGGED_SUBCAUSE", "SUB_CAUSE"],
    "significant":   ["SIGNIFICANT"],
    "serious":       ["SERIOUS"],
    "fatalities": [
        "TOTAL_DEATH", "TOTAL_FATALITIES", "DEATHS",
        "FATALITIES", "TOTAL_DEATHS", "FATAL",  # LNG form
    ],
    "injuries": [
        "TOTAL_INJURIES", "INJURIES", "TOTAL_INJURY", "INJURE",  # LNG form
    ],
    "gas_released_mcf": [
        "TOTAL_RELEASE_CALCULATED_MCF", "GAS_RELEASED_MCFE",
        "GAS_MCF", "MSCFE_RELEASED", "RELEASE_MCF",
        "TOTAL_RELEASE_MCF", "UNINTENTIONAL_RELEASE",  # GT 2010+
    ],
    "liquid_released_bbl": [
        "TOTAL_RELEASE_CALCULATED_BBL", "NET_LOSS_CALCULATED_BBL",
        "TOTAL_SPILL_CALCULATED_BBL", "BARRELS_RELEASED",
        "RELEASE_BBL",
        "UNINTENTIONAL_RELEASE_BBLS", "NET_LOSS_BBLS",  # HL 2010+
    ],
    "total_cost": [
        "TOTAL_COST_CURRENT", "TOTAL_COSTS_CURRENT",
        "PROPERTY_DAMAGE_CURRENT", "TOTAL_DAMAGE_CURRENT",
        "TOTAL_COST",
    ],
}

_COUNTY_SUFFIXES = [" COUNTY", " PARISH", " BOROUGH", " CENSUS AREA", " MUNICIPALITY"]



def normalize_county(name: object) -> str:
    """Uppercase, strip, and remove administrative suffixes."""
    if pd.isna(name) or str(name).strip() in {"", "nan", "NAN"}:
        return ""
    s = str(name).upper().strip()
    for suffix in _COUNTY_SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s.replace("-", " ").strip()


def resolve_col(df_cols_upper: dict[str, str], field: str) -> str | None:
    """Return the actual column name for a semantic field, or None."""
    for alias in COLUMN_ALIASES.get(field, []):
        if alias.upper() in df_cols_upper:
            return df_cols_upper[alias.upper()]
    return None



def download_zip(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists() and not force:
        log.info("ZIP already cached: %s", ZIP_PATH)
        return ZIP_PATH
    log.info("Downloading PHMSA flagged incidents ZIP...")
    r = requests.get(
        ZIP_URL,
        timeout=300,
        stream=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TRACE-ER-Explorer/1.0)"},
    )
    r.raise_for_status()
    total = 0
    with open(ZIP_PATH, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
            total += len(chunk)
    log.info("Downloaded %.1f MB → %s", total / 1e6, ZIP_PATH)
    return ZIP_PATH


def extract_zip(zip_path: Path) -> Path:
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        log.info("ZIP contains %d entries:", len(names))
        for n in names:
            log.info("  %s", n)
        zf.extractall(EXTRACT_DIR)
    return EXTRACT_DIR


def detect_system_type(path: Path) -> str | None:
    stem = path.stem.lower()
    for fragment, tag in SYSTEM_TYPE_PATTERNS:
        if fragment in stem:
            return tag
    return None


def read_and_normalise(xlsx_path: Path, system_type: str) -> pd.DataFrame | None:
    log.info("Reading %s (type=%s)...", xlsx_path.name, system_type)
    try:
        # sheet_name=None returns a dict {sheet_name: df}; handles single- and
        # multi-sheet workbooks (some PHMSA files split data by year into sheets)
        sheets: dict = pd.read_excel(xlsx_path, sheet_name=None, dtype=str)
    except Exception as exc:
        log.error("  Cannot read %s: %s — skipping.", xlsx_path.name, exc)
        return None

    frames = [df for df in sheets.values() if len(df) > 0]
    if not frames:
        log.warning("  No non-empty sheets found in %s — skipping.", xlsx_path.name)
        return None

    raw = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0].copy()
    raw = raw.reset_index(drop=True)
    log.info("  Raw shape: %s", raw.shape)
    log.info("  Columns (%d): %s", len(raw.columns), list(raw.columns[:12]))

    # Case-insensitive column lookup map: UPPER_NAME → original name
    cols_upper = {c.upper(): c for c in raw.columns}

    # --- Resolve required columns ---
    year_col  = resolve_col(cols_upper, "year")
    state_col = resolve_col(cols_upper, "state")

    if year_col is None:
        log.error(
            "  REQUIRED column YEAR not found in %s — skipping.\n  All columns: %s",
            xlsx_path.name, list(raw.columns),
        )
        return None
    if state_col is None:
        log.error(
            "  REQUIRED column STATE not found in %s — skipping.\n  All columns: %s",
            xlsx_path.name, list(raw.columns),
        )
        return None

    # --- Resolve optional columns (None = not present in this system type) ---
    county_col        = resolve_col(cols_upper, "county")
    operator_col      = resolve_col(cols_upper, "operator_name")
    operator_id_col   = resolve_col(cols_upper, "operator_id")
    lat_col           = resolve_col(cols_upper, "latitude")
    lon_col           = resolve_col(cols_upper, "longitude")
    cause_col         = resolve_col(cols_upper, "cause")
    subcause_col      = resolve_col(cols_upper, "subcause")
    significant_col   = resolve_col(cols_upper, "significant")
    serious_col       = resolve_col(cols_upper, "serious")
    fatalities_col    = resolve_col(cols_upper, "fatalities")
    injuries_col      = resolve_col(cols_upper, "injuries")
    gas_vol_col       = resolve_col(cols_upper, "gas_released_mcf")
    liquid_vol_col    = resolve_col(cols_upper, "liquid_released_bbl")
    cost_col          = resolve_col(cols_upper, "total_cost")

    log.info(
        "  Resolved — year=%s state=%s county=%s significant=%s serious=%s "
        "fatalities=%s gas_vol=%s liquid_vol=%s cost=%s",
        year_col, state_col, county_col, significant_col, serious_col,
        fatalities_col, gas_vol_col, liquid_vol_col, cost_col,
    )

    # --- Filter: state ---
    state_clean = raw[state_col].str.strip().str.upper()
    df = raw[state_clean.isin(TARGET_STATES)].copy().reset_index(drop=True)
    if df.empty:
        log.info("  No rows for TARGET_STATES %s — skipping.", TARGET_STATES)
        return None

    # --- Filter: year ---
    # Year may be an integer (e.g. 2023), a string ("2023"), or a timestamp
    # ("2023-07-15").  Extract the first 4-digit year matching 19xx or 20xx.
    raw_year = df[year_col].astype(str)
    year_int = pd.to_numeric(
        raw_year.str.extract(r'\b((?:19|20)\d{2})\b')[0],
        errors="coerce",
    )
    df = df[year_int.between(YEAR_MIN, YEAR_MAX)].copy().reset_index(drop=True)
    year_int = year_int[year_int.between(YEAR_MIN, YEAR_MAX)].reset_index(drop=True)

    if df.empty:
        log.info(
            "  No rows remain after year filter %d–%d — skipping.", YEAR_MIN, YEAR_MAX
        )
        return None

    n = len(df)

    # --- Helper lambdas for optional columns ---
    def str_col(col: str | None, default: str = "") -> pd.Series:
        return df[col].fillna(default) if col else pd.Series([default] * n)

    def num_col(col: str | None) -> pd.Series:
        return (
            pd.to_numeric(df[col], errors="coerce")
            if col
            else pd.Series([float("nan")] * n)
        )

    def bool_col(col: str | None) -> pd.Series:
        if col is None:
            return pd.Series([False] * n)
        return df[col].str.strip().str.upper() == "Y"

    # --- Build normalised output ---
    out = pd.DataFrame({
        "phmsa_system_type":    [system_type] * n,
        "incident_year":        year_int.astype("Int64"),
        "state":                df[state_col].str.strip().str.upper(),
        "county_raw":           str_col(county_col),
        "county_norm":          str_col(county_col).apply(normalize_county),
        "operator_name":        str_col(operator_col),
        "operator_id":          str_col(operator_id_col),
        "latitude":             num_col(lat_col),
        "longitude":            num_col(lon_col),
        "cause":                str_col(cause_col),
        "subcause":             str_col(subcause_col),
        "significant":          bool_col(significant_col),
        "serious":              bool_col(serious_col),
        "fatalities":           num_col(fatalities_col).fillna(0),
        "injuries":             num_col(injuries_col).fillna(0),
        "gas_released_mcf":     num_col(gas_vol_col),
        "liquid_released_bbl":  num_col(liquid_vol_col),
        "total_cost_current":   num_col(cost_col),
    })

    log.info(
        "  %s: %d incidents — states %s — years %d–%d",
        system_type, n,
        dict(out["state"].value_counts().to_dict()),
        int(out["incident_year"].min()),
        int(out["incident_year"].max()),
    )
    return out



def aggregate_to_county(incidents: pd.DataFrame) -> pd.DataFrame:
    """One row per (state, county_norm) with pipeline-risk indicators.

    Incidents without a county (county_norm == "") are excluded: they cannot
    be matched to master-index facilities and would create spurious county-wide
    joins if left in.
    """
    incidents = incidents[incidents["county_norm"] != ""].copy()
    if incidents.empty:
        raise RuntimeError(
            "No incidents with a resolvable county. "
            "Check column resolution logs — county aliases may need updating."
        )
    grp = incidents.groupby(["state", "county_norm"], sort=True)

    agg = grp.agg(
        phmsa_incident_count        =("phmsa_system_type", "count"),
        phmsa_significant_count     =("significant", "sum"),
        phmsa_serious_count         =("serious", "sum"),
        phmsa_fatalities_total      =("fatalities", "sum"),
        phmsa_injuries_total        =("injuries", "sum"),
        phmsa_total_cost_current    =("total_cost_current", "sum"),
        phmsa_gas_released_mcf      =("gas_released_mcf", "sum"),
        phmsa_liquid_released_bbl   =("liquid_released_bbl", "sum"),
        phmsa_most_recent_year      =("incident_year", "max"),
    ).reset_index()

    # Per-system-type incident counts
    for stype in ["GD", "GT", "HL", "LNG", "GG"]:
        col = f"phmsa_{stype.lower()}_incidents"
        counts = (
            incidents[incidents["phmsa_system_type"] == stype]
            .groupby(["state", "county_norm"])
            .size()
            .reset_index(name=col)
        )
        agg = agg.merge(counts, on=["state", "county_norm"], how="left")
        agg[col] = agg[col].fillna(0).astype(int)

    agg["has_phmsa_incidents"] = True

    log.info(
        "County features: %d state+county rows — states %s",
        len(agg), sorted(agg["state"].unique().tolist()),
    )
    return agg


def join_to_master(
    county_features: pd.DataFrame,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Join on (state, normalised_county).  Master row count is preserved exactly.
    Every facility in a county that had pipeline incidents inherits the
    county's aggregate risk indicators.
    """
    master = master.copy()
    master["_county_norm"] = master["county"].apply(normalize_county)
    master["_state"]       = master["state"].str.strip().str.upper()

    # Rename join keys on features side to avoid column collision
    feat = county_features.rename(columns={
        "county_norm": "_county_norm",
        "state":       "_state",
    })

    master_out = master.merge(feat, on=["_state", "_county_norm"], how="left")
    master_out = master_out.drop(columns=["_county_norm", "_state"])
    master_out["has_phmsa_incidents"] = (
        master_out["has_phmsa_incidents"].fillna(False)
    )

    matched = int(master_out["has_phmsa_incidents"].sum())
    assert len(master_out) == len(master), (
        f"Row count changed after PHMSA join: {len(master)} → {len(master_out)}"
    )

    stats = {
        "raw_incident_rows":            None,   # filled by caller
        "state_county_combos":          len(county_features),
        "master_rows_with_phmsa_data":  matched,
    }
    return master_out, stats


def append_volume_log(raw_rows: int, stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "phmsa_pipeline_incidents",
        "row_count": raw_rows,
        "notes": (
            f"study_states={sorted(TARGET_STATES)}; "
            f"years={YEAR_MIN}-{YEAR_MAX}; "
            f"county_combos={stats['state_county_combos']}; "
            f"master_rows_with_phmsa={stats['master_rows_with_phmsa_data']}"
        ),
    }
    with open(VOL_LOG, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    log.info("Logged volume entry → %s", VOL_LOG)


def main() -> None:
    # 1. Download
    zip_path = download_zip(force=False)

    # 2. Extract
    extract_dir = extract_zip(zip_path)

    # 3. Find all Excel files and determine system types
    xlsx_files = sorted(extract_dir.rglob("*.xlsx"))
    if not xlsx_files:
        raise RuntimeError(
            f"No .xlsx files found under {extract_dir}.\n"
            "The ZIP may use a different format — inspect contents above."
        )
    log.info("Found %d .xlsx file(s) to process:", len(xlsx_files))
    for f in xlsx_files:
        stype = detect_system_type(f)
        log.info("  %-60s → type=%s", f.name, stype or "UNRECOGNISED")

    # 4. Read and normalise each file
    all_incidents: list[pd.DataFrame] = []
    skipped: list[str] = []

    for xlsx in xlsx_files:
        stype = detect_system_type(xlsx)
        if stype is None:
            log.warning("Skipping unrecognised filename: %s", xlsx.name)
            skipped.append(xlsx.name)
            continue
        df = read_and_normalise(xlsx, stype)
        if df is not None and len(df) > 0:
            all_incidents.append(df)

    if not all_incidents:
        raise RuntimeError(
            "No incident rows extracted after all filters.\n"
            "Review the column-resolution log above for each file."
        )

    incidents = pd.concat(all_incidents, ignore_index=True)
    log.info(
        "Combined: %d incident rows — types: %s — states: %s",
        len(incidents),
        dict(incidents["phmsa_system_type"].value_counts().to_dict()),
        dict(incidents["state"].value_counts().to_dict()),
    )
    if skipped:
        log.warning("Skipped files with unrecognised names: %s", skipped)

    # 5. Save interim
    DATA_DIR.joinpath("interim").mkdir(parents=True, exist_ok=True)
    incidents.to_csv(INTERIM_OUT, index=False)
    log.info("Wrote %d incident rows → %s", len(incidents), INTERIM_OUT)

    # 6. County aggregation
    county_features = aggregate_to_county(incidents)
    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    county_features.to_csv(COUNTY_OUT, index=False)
    log.info("Wrote %d county feature rows → %s", len(county_features), COUNTY_OUT)

    # 7. Join to master index
    log.info("Loading master index: %s", MASTER_IN)
    master = pd.read_csv(MASTER_IN, dtype=str)
    log.info("  %d rows  |  %d columns", len(master), len(master.columns))

    master_out, stats = join_to_master(county_features, master)
    stats["raw_incident_rows"] = len(incidents)

    master_out.to_csv(MASTER_OUT, index=False)
    log.info(
        "Wrote extended master index: %d rows  |  %d columns → %s",
        len(master_out), len(master_out.columns), MASTER_OUT,
    )

    append_volume_log(len(incidents), stats)

    log.info("Done. Summary:")
    log.info("  Raw incident rows:               %d", len(incidents))
    log.info("  State+county combinations:       %d", stats["state_county_combos"])
    log.info("  Master rows with PHMSA data:     %d", stats["master_rows_with_phmsa_data"])
    log.info("  Master column count:             %d", len(master_out.columns))


if __name__ == "__main__":
    main()