# TRACE-ER Explorer — Technical Implementation Guide

**Version:** 1.0  
**Date:** September 20, 2026  
**Prepared by:** TRACE-ER Explorer Project Team  
**Scope document reference:** TRACE-ER Explorer Prototype Development Project Scope v1.2  

---

## 1. Overview

This guide describes the full data engineering pipeline for the TRACE-ER Explorer prototype: from raw public source downloads through the integrated, scored master facility index delivered to Power BI. It is intended for practitioners who need to reproduce, refresh, or extend the dataset.

The pipeline is implemented entirely in Python 3.14 and runs on a standard laptop. All source data is public and freely accessible without API keys or authentication. Total storage for raw, interim, and processed outputs is approximately 4–6 GB. A full cold-start run (all sources downloaded fresh) takes 2–3 hours, dominated by network transfers and the NM OCD paginated API. Subsequent incremental refreshes of individual sources take minutes.

**States covered:** Texas (TX), Pennsylvania (PA), New Mexico (NM), Maine (ME)  
**Primary analysis period:** 2019–2024  
**Master index size:** 527,983 facility rows × 111 columns (scored)

---

## 2. Repository Layout

```
trace-er-explorer/
├── src/
│   ├── ingest/                     # Source connectors and join scripts
│   │   ├── fetch_frs.py
│   │   ├── fetch_echo.py
│   │   ├── build_master_index.py
│   │   ├── fetch_tri_facility.py
│   │   ├── fetch_tri_releases.py
│   │   ├── build_tri_release_features.py
│   │   ├── join_tri_features_to_master.py
│   │   ├── fetch_rrc_r3_gas_plants.py
│   │   ├── join_rrc_r3_to_master.py
│   │   ├── fetch_phmsa_incidents.py
│   │   ├── fetch_tceq_lpst.py
│   │   ├── fetch_padep_wells.py
│   │   └── fetch_nmocd_wells.py
│   └── features/
│       └── build_risk_scores.py    # Composite risk scoring
├── data/
│   ├── raw/                        # Cached source downloads (unmodified)
│   │   ├── echo/extracted/
│   │   ├── frs/
│   │   ├── phmsa/extracted/
│   │   ├── tceq/
│   │   ├── padep/
│   │   └── nmocd/
│   ├── interim/                    # Cleaned single-source tables
│   └── processed/                  # Joined outputs and final deliverables
├── docs/                           # Project documentation
│   ├── TRACE_ER_Explorer_Data_Dictionary_v1_0.md
│   ├── TRACE_ER_Explorer_Validation_Report_v1_0.md
│   └── TRACE_ER_Explorer_Technical_Implementation_Guide_v1_0.md
├── validation/
│   └── source_volume_log.csv       # Timestamped ingest audit log
└── venv/                           # Python virtual environment
```

---

## 3. Environment Setup

### 3.1 Python Version

The pipeline was developed and tested on **Python 3.14**. Python 3.11 or higher is required per the project scope.

### 3.2 Virtual Environment

```bash
cd /path/to/trace-er-explorer
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate.bat    # Windows
```

### 3.3 Dependencies

Install all required packages:

```bash
pip install pandas geopandas pyproj shapely pyogrio \
            requests pyarrow numpy duckdb openpyxl \
            python-dateutil pyyaml
```

The `openpyxl` package is required by `fetch_phmsa_incidents.py` to read the PHMSA Excel files. If not installed, the script will attempt to install it automatically using `subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])`.

### 3.4 Directory Initialisation

All scripts create their output directories on first run. No manual directory creation is needed beyond the repository root.

---

## 4. Pipeline Architecture

The pipeline follows a linear dependency chain. Every step reads from files written by previous steps. The master index row count (527,983) is established at Step 3 and never changes: all subsequent join steps use left joins that preserve every row.

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1-3: Foundation — EPA FRS + ECHO → Master Index           │
│                                                                 │
│  fetch_frs.py  ──┐                                              │
│                  ├──► build_master_index.py ──► master_index    │
│  fetch_echo.py ──┘     (527,983 rows, 38 cols)                  │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4-7: EPA TRI — facility identity + release features       │
│                                                                 │
│  fetch_tri_facility.py ──┐                                      │
│                          ├──► join_tri ──► +tri_features        │
│  fetch_tri_releases.py ──┘   (53 cols)                          │
│  build_tri_release_features.py                                  │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ (each step adds columns, row count stays 527,983)
┌─────────────────────────────────────────────────────────────────┐
│  STEP 8-9: Texas RRC R-3 — spatial join (500 m, UTM 14N)        │
│  STEP 10:  PHMSA incidents — county-level left join             │
│  STEP 11:  TCEQ LPST sites — county-level left join (TX)        │
│  STEP 12:  PA DEP wells — county-level left join (PA)           │
│  STEP 13:  NM OCD wells — county-level left join (NM)           │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 14: Risk Scoring                                          │
│                                                                 │
│  build_risk_scores.py ──► master_risk_scores.csv (111 cols)     │
│                       ──► facility_risk_summary.csv (53 cols)   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Column Growth by Step

| After step | Script | Columns | New columns |
|---|---|---|---|
| 3 | `build_master_index.py` | 38 | Foundation (identity + ECHO compliance) |
| 7 | `join_tri_features_to_master.py` | 53 | +15 TRI release features |
| 9 | `join_rrc_r3_to_master.py` | 65 | +12 RRC R-3 features |
| 10 | `fetch_phmsa_incidents.py` | 80 | +15 PHMSA county features |
| 11 | `fetch_tceq_lpst.py` | 86 | +6 TCEQ LPST county features |
| 12 | `fetch_padep_wells.py` | 95 | +9 PA DEP county features |
| 13 | `fetch_nmocd_wells.py` | 104 | +9 NM OCD county features |
| 14 | `build_risk_scores.py` | 111 | +7 risk score columns |

---

## 5. Step-by-Step Execution

Run each script in the order shown. All scripts must be run from the repository root with the virtual environment active.

```bash
cd /path/to/trace-er-explorer
source venv/bin/activate
```

### Step 1 — EPA FRS

Downloads the national FRS facility file (~336 MB), filters to TX/PA/NM/ME.

```bash
python src/ingest/fetch_frs.py
```

**Output:** `data/interim/frs_facility_site.csv` (526,992 rows)  
**Source:** https://www.epa.gov/frs (bulk download)  
**Cache behaviour:** Cached. Re-run with `force=True` (modify the script constant) to refresh.  
**Runtime:** ~5 minutes (download-dominated)

### Step 2 — EPA ECHO

Downloads the ECHO Exporter ZIP (~408 MB), extracts, filters to study states.

```bash
python src/ingest/fetch_echo.py
```

**Output:** `data/interim/echo_facility_summary.csv` (311,717 rows)  
**Source:** https://echo.epa.gov/tools/data-downloads  
**Note:** The ECHO file was re-run once during the project after a schema expansion added 24 compliance columns that were missing from the initial download. The freshness check now embedded in the connector will detect stale interim files automatically.

### Step 3 — Build Master Index

Joins FRS and ECHO on EPA registry ID. Establishes the 527,983-row master index.

```bash
python src/ingest/build_master_index.py
```

**Output:** `data/processed/master_facility_index.csv` (527,983 rows, 38 cols)  
**Join logic:** Left join FRS → ECHO on `epa_registry_id`. ECHO-only records (927 genuine, 441 blank-ID excluded) appended. Coordinates: FRS preferred; ECHO used as fallback where FRS coordinates are absent.  
**Runtime:** ~3 minutes

### Step 4 — EPA TRI Facility Identity

Queries the EPA Envirofacts REST API for TRI-registered facilities in the four states.

```bash
python src/ingest/fetch_tri_facility.py
```

**Output:** `data/interim/tri_facility_{TX,PA,NM,ME}.csv` (8,361 rows total)  
**Source:** `https://data.epa.gov/efservice/` (REST API, paginated)  
**Note:** Some facilities have multiple TRI entries due to co-located operators at a shared address (e.g., multiple chemical companies at one industrial site). This is a real-world modelling case, not a data error.

### Step 5 — EPA TRI Release Quantities

Queries TRI release data per state per year (2019–2024) via the Envirofacts API. Implements retry-with-backoff and resume-from-cache because this step is network-intensive (24 state-year combinations).

```bash
python src/ingest/fetch_tri_releases.py
```

**Output:** `data/raw/tri_releases/tri_releases_{state}_{year}.csv` (24 files, 79,601 rows total)  
**Runtime:** 30–60 minutes depending on network conditions  
**Resumability:** The script caches each state-year file individually. If the run is interrupted, re-running continues from where it left off without re-downloading completed combinations.  
**Known limitation:** Year 2025 returns zero records for all states. This is a TRI reporting-cycle constraint (prior-year data is published after year close), not a data error. Confirmed across all four states.

### Step 6 — Build TRI Release Features

Aggregates 79,601 chemical-year release rows into one row per TRI facility, computing totals and hazard flags.

```bash
python src/ingest/build_tri_release_features.py
```

**Output:** `data/processed/tri_release_features.csv` (3,919 rows)

### Step 7 — Join TRI Features to Master Index

Left-joins TRI release features onto the master index via the shared EPA registry ID.

```bash
python src/ingest/join_tri_features_to_master.py
```

**Output:** `data/processed/master_facility_index_with_tri_features.csv` (527,983 rows, 53 cols)  
**Match rate:** 3,919 of 527,983 rows (0.74%) receive TRI release data. The low rate is expected — TRI covers only facilities that meet industry, employee size, and chemical-use thresholds.

### Step 8 — Texas RRC R-3 Gas Processing Plants

Downloads the R-3 Gas Processing Plants report from the Texas RRC website. The listing page uses relative hrefs with CMS-assigned slugs; the connector discovers all available months by parsing the page.

```bash
python src/ingest/fetch_rrc_r3_gas_plants.py
```

**Output:** `data/interim/rrc_r3_gas_plants.csv` (6,343 monthly rows, 13 months)  
**Source:** https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report  
**Coverage:** Aug 2025–Aug 2026 (13 months available at time of run)  
**Known issues resolved:** The connector's regex initially required absolute URLs but RRC serves relative hrefs (`/media/<slug>/r3dataload-<month>-<year>.zip`). Fixed with case-insensitive partial match. A module-level constant (`REQUIRED_FIELDS`) was accidentally removed during the regex fix; restored.

### Step 9 — Join RRC R-3 to Master Index

Aggregates 6,343 monthly rows into 1,451 plant-level rows, then performs a nearest-neighbour spatial join to the master index.

```bash
python src/ingest/join_rrc_r3_to_master.py
```

**Output:** `data/processed/master_facility_index_with_rrc_features.csv` (527,983 rows, 65 cols)  
**Join method:** UTM Zone 14N (EPSG:32614) nearest-neighbour via `geopandas.sjoin_nearest`, threshold 500 m. Plants with placeholder coordinates (30.0°N, −100.0°W) are excluded from the spatial join.  
**Match rate:** 410 plants matched; 20 collision resolutions (two plants competing for the same master row; the closer plant wins).

### Step 10 — PHMSA Pipeline Incidents

Downloads the PHMSA Flagged Incidents ZIP, processes all five pipeline system types, and joins county-level incident indicators to the master index.

```bash
python src/ingest/fetch_phmsa_incidents.py
```

**Output:**  
- `data/interim/phmsa_incidents.csv` (1,230 rows)  
- `data/processed/phmsa_county_features.csv` (223 state+county rows)  
- `data/processed/master_facility_index_with_phmsa_features.csv` (527,983 rows, 80 cols)  
**Source:** https://www.phmsa.dot.gov/...pipeline... (single ZIP, ~XX MB)  
**Join method:** Left join on normalised (state, county) — incidents occur along pipeline routes, not at fixed facility points.  
**Known issues resolved (3 iterations):**  
  1. Filename detection patterns matched long descriptive names ("distribution", "transmission") but PHMSA uses short prefixes (`gd*`, `gtgg*`, `hl*`). Fixed by adding short-prefix patterns first.  
  2. GT and HL forms use `ONSHORE_STATE_ABBREVIATION` (not `STATE`) and `ONSHORE_COUNTY_NAME` (not `COUNTY_PARISH_NAME`). Column aliases updated.  
  3. GD and LNG forms have no county field, producing blank `county_norm` values. A filter was added to exclude blank-county rows from the county aggregation, preventing spurious county-wide joins.

### Step 11 — TCEQ Leaking Petroleum Storage Tanks

Downloads the LPST flat file from TCEQ's own server (Socrata portals returned 403), parses the caret-delimited format, and joins county-level contamination indicators.

```bash
python src/ingest/fetch_tceq_lpst.py
```

**Output:**  
- `data/interim/tceq_lpst_sites.csv` (26,884 rows)  
- `data/processed/tceq_lpst_county_features.csv` (257 TX county rows)  
- `data/processed/master_facility_index_with_tceq_features.csv` (527,983 rows, 86 cols)  
**Source:** `https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt`  
**File format:** Comma-separated with `^` as the quotechar (Python `csv.reader(quotechar="^")`)  
**Date range:** All historical records (1983 to present) — LPST is a site registry, so historical sites remain risk-relevant.  
**Data quality note:** Some records carry REPORTED year `2103` (likely 2023, data-entry error in TCEQ's system). The `tceq_lpst_recent_sites_2019_2025` column reads zero for all counties as a result. This is a confirmed source anomaly.

### Step 12 — PA DEP Oil and Gas Wells

Downloads the PA DEP well locations CSV from PASDA (~74 MB), derives well type and status flags, and joins county-level well-density indicators.

```bash
python src/ingest/fetch_padep_wells.py
```

**Output:**  
- `data/interim/padep_wells.csv` (222,649 rows)  
- `data/processed/padep_county_features.csv` (57 PA county rows)  
- `data/processed/master_facility_index_with_padep_features.csv` (527,983 rows, 95 cols)  
**Source:** `https://www.pasda.psu.edu/spreadsheet/OilGasLocations_ConventionalUnconventional2025_09.csv`  
**Note:** The PASDA URL includes the release date (`2025_09`). When a newer release is available, update the `CSV_URL` constant in the script and set `force=True`.

### Step 13 — NM OCD Oil and Gas Wells

Fetches all 55,572 NM OCD active wells from the UNM NHNM ArcGIS REST API using paginated requests (1,000 records per page, 56 pages). Implements per-page retry with exponential backoff because the server rate-limits sustained requests, and incremental JSONL caching so a restart resumes from the last successful page.

```bash
python src/ingest/fetch_nmocd_wells.py
```

**Output:**  
- `data/raw/nmocd/nmocd_wells.jsonl` (cached; one JSON object per line)  
- `data/interim/nmocd_wells.csv` (55,572 rows)  
- `data/processed/nmocd_county_features.csv` (12 NM county rows)  
- `data/processed/master_facility_index_with_nmocd_features.csv` (527,983 rows, 104 cols)  
**Source:** `https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/ActiveOilandGasWells/MapServer/3`  
**Runtime:** 35–60 minutes (server imposes ~1.5 s inter-page delay; one timeout per ~6 pages is normal and handled by retry logic)  
**Access note:** NM OCD's own FTP server and REST API (`api.emnrd.nm.gov`) were inaccessible at ingestion time. The UNM NHNM endpoint is the documented public-access substitute and mirrors OCD's permitting database. The endpoint serves active wells only.  
**Resumability:** Delete `data/raw/nmocd/nmocd_wells.jsonl` to force a full re-download; otherwise the script resumes from the last fully cached page.

### Step 14 — Risk Scoring

Computes four component scores and a composite score for all 527,983 facilities, then produces the lean Power BI summary table.

```bash
python src/features/build_risk_scores.py
```

**Output:**  
- `data/processed/master_risk_scores.csv` (527,983 rows, 111 cols)  
- `data/processed/facility_risk_summary.csv` (527,983 rows, 53 cols — Power BI input)  
**Runtime:** ~5 minutes  
**Score columns added:** `compliance_risk_score`, `tri_release_score`, `pipeline_context_score`, `state_resource_score`, `composite_risk_score`, `composite_percentile_rank`, `risk_tier`

---

## 6. Design Principles

### 6.1 String-Typed CSV Reads

All `pd.read_csv()` calls use `dtype=str` to avoid pandas type inference. This prevents silent coercion of numeric IDs to integers (which would lose leading zeros) and mixed-type columns (which pandas would float). Numeric coercion is applied explicitly column-by-column where needed, with `errors="coerce"` so that unexpected values become NaN rather than raising exceptions.

### 6.2 Caching and Resumability

Every connector checks for its raw output file before downloading. The `force=False` default means re-running a connector that already has a cached file is a no-op (instant). To refresh a specific source, either delete its raw file or pass `force=True` through the script's `download_*` function. The TRI releases and NM OCD connectors additionally cache each sub-unit (state-year file; JSONL page) so network interruptions do not require a full restart.

### 6.3 Left-Join Discipline

The master index row count (527,983) is established at Step 3 and guaranteed to be unchanged by every subsequent step. Every join in Steps 4–14 is a left join with the master index on the left. This is enforced by an `assert len(master_out) == len(master)` statement in every join script; if violated, the script raises immediately rather than silently producing a wrong output.

### 6.4 County Name Normalisation

All county-level joins use a shared `normalize_county()` function that:
- Converts to uppercase
- Strips leading/trailing whitespace
- Removes common administrative suffixes (` COUNTY`, ` PARISH`, ` BOROUGH`, ` CENSUS AREA`, ` MUNICIPALITY`)
- Replaces hyphens with spaces

This function is defined independently in each connector that uses it (rather than a shared module) to keep each script self-contained and runnable without package installation.

### 6.5 Spatial Join Projection

The RRC R-3 spatial join uses **UTM Zone 14N (EPSG:32614)**, which provides metre-based Euclidean distance calculations accurate to within 1 m for the Texas study area. WGS84 (EPSG:4326) is used only for initial GeoDataFrame construction before reprojection. The 500 m match threshold was chosen based on typical gas processing plant footprint sizes and the coordinate precision of RRC's reporting data.

### 6.6 Source Volume Log

Every connector appends a timestamped row to `validation/source_volume_log.csv` recording the source name, row count, and a notes string containing key statistics. This log is the primary audit trail and the source for the Validation Report. Do not delete or modify it between runs; old runs are preserved for provenance.

---

## 7. Refreshing Individual Sources

To refresh a single source without rebuilding the entire pipeline from scratch, run its connector with `force=True` and then re-run all downstream steps. The dependency chain is:

| If you refresh... | Re-run these downstream steps |
|---|---|
| FRS (Step 1) or ECHO (Step 2) | Steps 3 → 14 |
| Master index (Step 3) | Steps 4 → 14 |
| TRI facility (Step 4) or releases (Step 5) | Steps 6, 7, 14 |
| TRI features (Step 6) | Steps 7, 14 |
| RRC R-3 (Step 8) | Steps 9, 14 |
| PHMSA (Step 10) | Step 14 |
| TCEQ (Step 11) | Step 14 |
| PA DEP (Step 12) | Step 14 |
| NM OCD (Step 13) | Step 14 |

To update the PA DEP connector for a newer PASDA release, change the `CSV_URL` and `RAW_FILE` constants in `fetch_padep_wells.py` to reflect the new release date (e.g., `2026_03` for the March 2026 release).

---

## 8. Known Limitations

| Limitation | Affected step | Notes |
|---|---|---|
| RRC main production data unavailable | Step 8 | Full TX production data (>25 GB) requires a manual email request to RRC Central Records. The R-3 connector is a self-service substitute covering gas processing plants only. |
| NM OCD plugged/abandoned wells not available | Step 13 | The public ArcGIS endpoint serves active wells only. A future connector could attempt the FTP server from a network without IP restrictions. |
| TCEQ Socrata portal returns 403 | Step 11 | Both `data.texas.gov` and `data.austintexas.gov` return 403 for programmatic bulk downloads. TCEQ's own direct file server works without restriction. |
| PHMSA GD/LNG incidents lack county | Step 10 | Gas Distribution and LNG forms do not include a county field. 87 incidents are in the interim file but excluded from the county join. |
| ME has no state-specific source | All | Maine is designated a complementary case study. USGS Water Quality Portal and Maine DEP data are identified as optional v1.0 additions; see Appendix A. |
| TRI 2025 data unavailable | Step 5 | TRI reporting cycle means year N data is not published until late year N+1. |

---

## 9. Testing

The repository includes a basic pytest suite. Run all tests with:

```bash
pytest tests/ -v
```

Unit tests cover the core normalisation functions (`normalize_county`, `log_minmax`, `yn_flag`, `bool_flag`), the LPST caret-delimiter parser, and the PHMSA system-type filename detection logic.

---

## 10. Output Files for Power BI

The primary Power BI input is:

```
data/processed/facility_risk_summary.csv
```

This 53-column file contains facility identity, all risk scores, risk tier, source coverage flags, and key indicators. It is designed for direct import into Power BI Desktop (Get Data → Text/CSV). The `latitude` and `longitude` columns support map visualisations. The `composite_percentile_rank` column (0–100 float) is suited for continuous colour scales on maps.

The full 111-column scored master index (`master_risk_scores.csv`) is available for advanced analysis but is large (~400 MB) and may require Power BI Premium for comfortable use.

See the Power BI Dashboard Guide (separate document) for step-by-step instructions on building the dashboard from `facility_risk_summary.csv`.

---

## Appendix A — Optional Sources (v1.0 Not Implemented)

The following sources are identified in the project scope as optional for v1.0 and are recommended for a future release.

**USGS Water Quality Portal**  
URL: https://www.waterqualitydata.us/  
Access: REST API with bulk download support.  
Relevance: Surface and groundwater monitoring stations near facilities; adds a water quality risk dimension currently absent from the dataset.  
States applicable: All four study states have USGS monitoring stations.

**Maine DEP**  
URL: https://www.maine.gov/dep/  
Access: Maine's environmental data portal has facility-level spill and remediation records.  
Relevance: Maine is currently the least-supported state in the dataset (no state-specific source); Maine DEP would provide the same level of state-specific context as TCEQ, PA DEP, and NM OCD.

---

*End of Technical Implementation Guide v1.0*