# TRACE-ER Explorer — Data Dictionary

**Version:** 1.0  
**Date:** September 20, 2026  
**Prepared by:** TRACE-ER Explorer Project Team  
**Scope document reference:** TRACE-ER Explorer Prototype Development Project Scope v1.2  

---

## 1. Overview

This document defines every field in the TRACE-ER Explorer master dataset and derived outputs. It covers the full 111-column scored master index (`master_risk_scores.csv`) and the 53-column Power BI summary table (`facility_risk_summary.csv`).

The dataset integrates eight public U.S. data sources covering four states: Texas (TX), Pennsylvania (PA), New Mexico (NM), and Maine (ME). Facility-level records from EPA and state agencies are joined into a single flat table. County-level contextual indicators from pipeline incident and contamination registries are attached via county name matching. Risk scores are computed from the combined feature set.

**Primary analysis period:** 2019 through 2024 (incident and release data).  
**Well and contamination registries:** All historical records retained; status and recency flags identify active sites.

---

## 2. File Inventory

| File | Rows | Columns | Description |
|---|---|---|---|
| `data/processed/master_risk_scores.csv` | 527,983 | 111 | Full master index with all source features and risk scores |
| `data/processed/facility_risk_summary.csv` | 527,983 | 53 | Lean Power BI table (identity + scores + key indicators) |
| `data/interim/phmsa_incidents.csv` | 1,230 | 18 | Cleaned PHMSA incident rows, all pipeline system types |
| `data/processed/phmsa_county_features.csv` | 223 | 17 | PHMSA risk aggregated to state+county |
| `data/interim/tceq_lpst_sites.csv` | 26,884 | 19 | TCEQ LPST site records (one row per case) |
| `data/processed/tceq_lpst_county_features.csv` | 257 | 8 | LPST contamination aggregated to TX county |
| `data/interim/padep_wells.csv` | 222,649 | 19 | PA DEP well locations (key columns only) |
| `data/processed/padep_county_features.csv` | 57 | 10 | PA well density aggregated to PA county |
| `data/interim/nmocd_wells.csv` | 55,572 | 16 | NM OCD well records |
| `data/processed/nmocd_county_features.csv` | 12 | 9 | NM well density aggregated to NM county |
| `data/processed/rrc_r3_plant_features.csv` | 1,451 | 14 | Texas RRC R-3 gas plant features (one row per plant) |
| `data/interim/tri_releases_enriched.csv` | 79,601 | — | TRI chemical release records with facility registry IDs |
| `data/processed/tri_release_features.csv` | 3,919 | 14 | TRI features aggregated to facility level |
| `validation/source_volume_log.csv` | — | 4 | Timestamped ingest log for every connector run |

---

## 3. Column Reference

Columns are grouped by the source that contributes them. Coverage figures are approximate and reflect the September 2026 production run.

---

### 3.1 Facility Identity

These columns are present for every row in the master index. They originate from EPA FRS, with ECHO coordinates substituted where FRS coordinates are absent or lower accuracy.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `master_id` | String | Unique row identifier in the master index. Equals the EPA FRS registry ID where available; a generated surrogate key for ECHO-only records. | 527,983 (100%) |
| `facility_name` | String | Primary facility name from FRS, or ECHO name where FRS is absent. | 527,983 (100%) |
| `address` | String | Street address from FRS. | ~520,000 |
| `city` | String | City from FRS. | ~524,000 |
| `postal_code` | String | ZIP code from FRS. | ~518,000 |
| `state` | String | Two-letter state abbreviation. Values: TX, PA, NM, ME. | 527,983 (100%) |
| `county` | String | County name from FRS, uppercase, no "County" suffix (e.g., HARRIS not HARRIS COUNTY). Used as the county join key for PHMSA, TCEQ, PA DEP, and NM OCD features. | ~524,000 |
| `latitude` | Float | Decimal degrees, WGS84. Sourced from FRS; ECHO used as fallback. | ~520,000 |
| `longitude` | Float | Decimal degrees, WGS84. | ~520,000 |
| `coord_accuracy_value` | Integer | FRS coordinate accuracy code. Lower values indicate higher precision (1 = address match, 5 = ZIP centroid, etc.). | ~490,000 |
| `coord_source` | String | Which source provided the accepted coordinates: `frs` or `echo`. | ~520,000 |
| `sources_present` | String | Comma-delimited list of source systems with a record for this facility (e.g., `FRS,ECHO,TRI`). | 527,983 (100%) |
| `source_count` | Integer | Count of distinct data sources with a record for this facility. Range 1–3. | 527,983 (100%) |
| `linkage_confidence` | String | How FRS and ECHO records were joined. Values: `EXACT_ID` (shared registry ID), `ECHO_ONLY`, `FRS_ONLY`. | 527,983 (100%) |
| `naics_codes_raw_frs` | String | NAICS code(s) from FRS, pipe-delimited where multiple. | ~340,000 |
| `sic_codes_raw_frs` | String | SIC code(s) from FRS, pipe-delimited where multiple. | ~290,000 |
| `programs_raw` | String | FRS regulatory program affiliations, semicolon-delimited (e.g., `AIR:TX0000123, RCRA:TXD000456`). | ~430,000 |
| `site_type` | String | FRS site type classification (e.g., STATIONARY, MOBILE). | ~480,000 |
| `huc_code` | String | USGS Hydrologic Unit Code (watershed) from FRS. | ~380,000 |

---

### 3.2 EPA ECHO Compliance

Source: EPA ECHO Exporter (bulk national download, filtered to TX/PA/NM/ME).  
URL: `https://echo.epa.gov/tools/data-downloads`  
Coverage: 311,316 facilities with ECHO records (59% of master index). The remaining 41% are FRS-only entities with no ECHO record; all ECHO fields are null for those rows.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `fac_inspection_count` | Integer | Total number of facility inspections on record in ECHO. | 311,316 |
| `fac_formal_action_count` | Integer | Count of formal enforcement actions (administrative orders, judicial referrals). A non-zero value indicates documented regulatory violations. | 311,316 |
| `fac_informal_count` | Integer | Count of informal enforcement actions (notices of violation, warning letters). | 311,316 |
| `fac_total_penalties` | Float | Cumulative monetary penalties assessed (USD). Note: reflects penalties as reported to EPA and may not include state-only penalties. | 311,316 |
| `fac_qtrs_with_nc` | Integer | Number of quarters (out of the most recent 12) in which the facility was in non-compliance with at least one regulatory requirement. Range 0–12. | 296,733 |
| `fac_compliance_status` | String | Most recent overall compliance status. Values: `No Violation Identified`, `Violation Identified`, `Unknown`. | 238,064 |
| `fac_snc_flag` | String | Significant Non-Compliance flag. `Y` = facility is currently designated SNC under one or more programs; `N` = not SNC. | 311,316 |
| `caa_hpv_flag` | String | Clean Air Act High Priority Violator flag. `Y` = currently designated HPV; `N` = not HPV. | 311,316 |
| `air_flag` | String | `Y` if facility has at least one active Clean Air Act permit in ECHO. | 311,316 |
| `npdes_flag` | String | `Y` if facility has at least one active NPDES (Clean Water Act) permit. | 311,316 |
| `sdwis_flag` | String | `Y` if facility is a registered public water system in SDWIS. | 311,316 |
| `rcra_flag` | String | `Y` if facility is registered as a hazardous waste handler under RCRA. | 311,316 |
| `tri_flag` | String | `Y` if facility is a TRI reporter in ECHO. Note: ECHO's TRI flag may lag the actual TRI release data joined from the TRI Basic Data connector. | 311,316 |
| `ghg_flag` | String | `Y` if facility reports under EPA's Greenhouse Gas Reporting Program. | 311,316 |
| `detail_report_url` | String | URL to the facility's detailed report page on ECHO. | ~308,000 |

---

### 3.3 EPA TRI Release Data

Source: EPA Envirofacts efservice API (MV_TRI_BASIC_DOWNLOAD), queried per state per year, 2019–2024.  
URL: `https://data.epa.gov/efservice/`  
Coverage: 3,919 facilities with TRI release records (0.74% of master index). The TRI program covers only facilities meeting size, industry, and chemical-use thresholds; most EPA-registered facilities do not file TRI reports. All TRI numeric columns are null for non-TRI facilities; `has_tri_release_data` is `False` for those rows.

Note: 2025 TRI data was confirmed unavailable system-wide at the time of ingestion (TRI reporting cycle means the prior year's data is not published until after the calendar year closes).

| Column | Type | Description | Coverage |
|---|---|---|---|
| `tri_facility_id_tri` | String | TRI facility identifier (alphanumeric, distinct from EPA registry ID). | 3,919 |
| `region_tri` | String | EPA region number from the TRI facility record. | 3,919 |
| `parent_co_name_tri` | String | Parent company name as reported in TRI. | ~3,800 |
| `fac_closed_ind_tri` | String | TRI closed-facility indicator. `1` = facility reported as closed in TRI; `0` = active. | 3,919 |
| `distinct_chemical_count` | Integer | Number of distinct chemicals for which this facility reported releases across 2019–2024. | 3,919 |
| `distinct_reporting_years` | Integer | Number of years (within 2019–2024) in which this facility filed at least one TRI report. | 3,919 |
| `most_recent_reporting_year` | Integer | Most recent year in which this facility filed a TRI report. | 3,919 |
| `total_on_site_release` | Float | Sum of all on-site releases reported (pounds), aggregated across all chemicals and years 2019–2024. | 3,919 |
| `total_off_site_release` | Float | Sum of all off-site transfers reported as releases (pounds). | 3,919 |
| `total_releases_sum` | Float | `total_on_site_release + total_off_site_release`. Primary TRI release magnitude indicator used in risk scoring. | 3,919 |
| `total_production_waste` | Float | Total production-related waste generated (pounds), including releases, recycling, energy recovery, and treatment. | 3,919 |
| `any_carcinogen` | Boolean | `True` if any reported chemical is classified as a known or probable human carcinogen (IARC Group 1/2A or EPA carcinogen list). | 3,919 |
| `any_pbt` | Boolean | `True` if any reported chemical is designated a Persistent Bioaccumulative Toxic (PBT) under TRI. | 3,919 |
| `any_pfas` | Boolean | `True` if any reported chemical is a per- and polyfluoroalkyl substance (PFAS). Reporting of PFAS under TRI began with reporting year 2020. | 3,919 |
| `any_metal` | Boolean | `True` if any reported chemical is a metal or metal compound. | 3,919 |
| `form_a_row_count` | Integer | Number of Form A (certification of threshold exemption) records filed by this facility across 2019–2024. | 3,919 |
| `total_release_records` | Integer | Total number of individual chemical-year release records summed to produce this row. | 3,919 |
| `form_r_row_count` | Integer | Number of Form R (full quantitative report) records filed. | 3,919 |
| `has_tri_release_data` | Boolean | `True` if this facility has TRI release data in the master index. Used as a mask in risk scoring. | 527,983 (100%) |

---

### 3.4 Texas RRC R-3 Gas Processing Plants

Source: Texas Railroad Commission R-3 Gas Processing Plants Report (monthly JSON downloads).  
URL: `https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report`  
Coverage: 411 facilities spatially matched within 500 m of an RRC gas plant (0.08% of master index). Join method: UTM Zone 14N nearest-neighbour spatial join. RRC coordinates were 41% placeholder values (30.0, −100.0); only the 890 plants with valid coordinates participated in the join. Coverage is limited to Texas.

Note: RRC's main Production Data Query Dump (comprehensive well and production data) requires a manual email request to RRC Central Records (>25 GB). The R-3 connector is a self-service substitute covering gas processing plants specifically.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `r3_match_distance_m` | Float | Distance in metres between the master-index facility point and the matched RRC gas plant centroid (UTM 14N). Lower values indicate higher confidence. | 411 |
| `r3_facility_name` | String | Gas plant name from RRC R-3 reports. | 411 |
| `r3_plant_type` | String | RRC plant classification (e.g., Gas Processing, Compressor Station, Treating). | 411 |
| `r3_district` | String | RRC district where the plant is located (e.g., `06 - Kilgore`). | 411 |
| `r3_county` | String | County name from RRC R-3, uppercase. | 411 |
| `r3_is_cid_critical` | String | Critical Infrastructure Designation flag from RRC. `YES` = designated critical infrastructure. | 411 |
| `r3_months_reported` | Integer | Number of monthly R-3 reports filed by this plant across the 13-month coverage window (Aug 2025–Aug 2026). | 411 |
| `r3_years_covered` | String | Comma-delimited list of calendar years represented in the monthly reports (e.g., `2025,2026`). | 411 |
| `r3_net_gas_total_mcf` | Float | Total net gas to plant for processing across all reported months (Mcf). Primary throughput indicator. | 411 |
| `r3_vented_gas_total_mcf` | Float | Total vented gas across all reported months (Mcf). Null for most plants (94% of monthly rows have null vented values). | 37 |
| `r3_avg_capacity_mean` | Float | Mean of the reported average plant capacity values across all months. | 411 |
| `has_rrc_r3_data` | Boolean | `True` if this facility was spatially matched to an RRC R-3 gas plant. | 527,983 (100%) |

---

### 3.5 PHMSA Pipeline Incidents

Source: PHMSA Pipeline Safety Flagged Incidents ZIP (all five pipeline system types).  
URL: `https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data`  
Coverage: 391,069 facilities (74% of master index) are in counties with at least one pipeline incident on record. Join method: county-level left join on (state, normalized county name). Pipeline incidents are events on linear infrastructure — not fixed-facility events — so county-level attribution is the appropriate and defensible join strategy. All four study states are represented (TX 1,080 / PA 83 / NM 65 / ME 2 incidents).  
Analysis period: 2019–2024.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `phmsa_incident_count` | Float | Total number of pipeline incidents in this facility's county, 2019–2024, across all pipeline system types. | 391,069 |
| `phmsa_significant_count` | Float | Incidents flagged as "Significant" by PHMSA (met one or more significance criteria: fatality, injury, fire, explosion, or release above threshold). | 391,069 |
| `phmsa_serious_count` | Float | Incidents flagged as "Serious" by PHMSA (a subset of significant with more severe consequences). | 391,069 |
| `phmsa_fatalities_total` | Float | Total fatalities across all incidents in the county, 2019–2024. | 391,069 |
| `phmsa_injuries_total` | Float | Total injuries across all incidents in the county. | 391,069 |
| `phmsa_total_cost_current` | Float | Total estimated property damage (current-year USD) across all incidents. | 391,069 |
| `phmsa_gas_released_mcf` | Float | Total gas released in Mcf across gas-system incidents in the county. | 391,069 |
| `phmsa_liquid_released_bbl` | Float | Total liquid released in barrels across hazardous-liquid incidents. | 391,069 |
| `phmsa_most_recent_year` | Float | Year of the most recent pipeline incident in this county within the analysis period. | 391,069 |
| `phmsa_gd_incidents` | Integer | Count of Gas Distribution incidents in the county. | 391,069 |
| `phmsa_gt_incidents` | Integer | Count of Gas Transmission and Gathering incidents. | 391,069 |
| `phmsa_hl_incidents` | Integer | Count of Hazardous Liquid incidents. Dominant system type in Texas (894 of 1,080 TX incidents). | 391,069 |
| `phmsa_lng_incidents` | Integer | Count of LNG Facility incidents. | 391,069 |
| `phmsa_gg_incidents` | Integer | Count of Gas Gathering (Type R) incidents. | 391,069 |
| `has_phmsa_incidents` | Boolean | `True` if this facility is in a county with at least one PHMSA pipeline incident (2019–2024). | 527,983 (100%) |

---

### 3.6 TCEQ Leaking Petroleum Storage Tanks (Texas only)

Source: TCEQ Office of Waste, Remediation Division — LPST database flat file.  
URL: `https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt`  
Entry page: `https://www.tceq.texas.gov/agency/data/lookup-data/download-data.html`  
Coverage: 338,683 Texas facilities (all TX rows in the master index that can be matched by county). Join method: county-level left join on normalized county name. LPST records carry no coordinates; county name is the only geographic linkage available. Coverage limited to Texas.  
Date range: All historical LPST records (1983 to present) — LPST is a contamination site registry, not a time-series incident log; older active sites remain material risk indicators.

Data quality note: The TCEQ source database contains a data-entry error where some "REPORTED" dates are recorded as year 2103 (likely intended as 2023). As a result, `tceq_lpst_recent_sites_2019_2025` reads zero for all counties — this is a confirmed source-data anomaly, not a processing error. The total and active site counts are unaffected.

Status code note: Status code `6A` (and variants 6B–6H) denotes a closed case. All other codes (1–5) indicate active or in-progress corrective action.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `tceq_lpst_total_sites` | Float | Total number of LPST cases ever reported in this county, all dates and statuses. | 338,683 |
| `tceq_lpst_most_recent_reported_year` | Float | Year of the most recent LPST report in the county (subject to the 2103 data-entry issue noted above). | 338,683 |
| `tceq_lpst_active_sites` | Float | LPST cases with a current status code indicating active or in-progress corrective action (status not in {6A, 6B, 6C, 6D, 6E, 6F, 6G, 6H, NFA}). Primary contamination burden indicator used in state resource score. | 338,683 |
| `tceq_lpst_recent_sites_2019_2025` | Float | LPST cases first reported in 2019–2025. Currently zero for all counties due to the year-2103 data-entry error in TCEQ's source database. Retained for transparency; correct values pending a TCEQ source correction. | 338,683 |
| `tceq_lpst_high_priority_sites` | Float | LPST cases with priority codes starting with 1 or 2 (high and medium-high risk per TCEQ's own classification). | 338,683 |
| `has_tceq_lpst_data` | Boolean | `True` if this facility is in a Texas county with at least one LPST case on record. | 527,983 (100%) |

---

### 3.7 Pennsylvania DEP Oil and Gas Wells (Pennsylvania only)

Source: PA DEP Oil & Gas Well Locations (Conventional + Unconventional) via PASDA.  
URL: `https://www.pasda.psu.edu/spreadsheet/OilGasLocations_ConventionalUnconventional2025_09.csv`  
Release date: September 2025.  
Coverage: 75,785 Pennsylvania facilities in counties with PA DEP well data (57 of 67 PA counties have wells). Join method: county-level left join. Limited to Pennsylvania.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `padep_total_wells` | Float | Total number of PA DEP-registered oil and gas wells in this county (all types and statuses). | 75,785 |
| `padep_most_recent_permit_year` | Float | Most recent permit year for any well in the county. | 75,785 |
| `padep_active_wells` | Float | Wells with a status not containing "Plug", "Abandon", or "Inactive". PA has 149,080 active wells statewide. | 75,785 |
| `padep_plugged_abandoned_wells` | Float | Wells with a status containing "Plug" or "Abandon". | 75,785 |
| `padep_unconventional_wells` | Float | Wells flagged as unconventional (primarily Marcellus and Utica Shale). Used in state resource score because unconventional development correlates with higher methane emissions and water-quality risk. PA has 24,750 unconventional wells statewide. | 75,785 |
| `padep_oil_wells` | Float | Wells with WELL_TYPE containing "Oil". | 75,785 |
| `padep_gas_wells` | Float | Wells with WELL_TYPE containing "Gas", "Coalbed", or "Methane". | 75,785 |
| `padep_recent_permit_count` | Float | Wells with a permit date in 2019–2025. Indicates active drilling activity. PA has 5,763 recent-permit wells statewide. | 75,785 |
| `has_padep_well_data` | Boolean | `True` if this facility is in a PA county with at least one registered PA DEP well. | 527,983 (100%) |

---

### 3.8 New Mexico OCD Oil and Gas Wells (New Mexico only)

Source: NM Oil Conservation Division via UNM New Mexico Heritage Network / NMEDB ArcGIS REST API.  
API: `https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/ActiveOilandGasWells/MapServer/3`  
Note: The NM OCD FTP server and REST API (`api.emnrd.nm.gov`) were inaccessible at ingestion time. The UNM NHNM endpoint is the documented public-access substitute and mirrors OCD's permitting database.  
Coverage: 17,516 New Mexico facilities in 12 counties with OCD well data (12 of 33 NM counties have wells — oil and gas activity is concentrated in the Permian Basin counties of Eddy and Lea, and the San Juan Basin). Limited to New Mexico. The API endpoint name ("Active Oil and Gas Wells") means all 55,572 retrieved records carry active status; plugged and abandoned wells are not available through this endpoint.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `nmocd_total_wells` | Float | Total number of NM OCD-registered active wells in this county. | 17,516 |
| `nmocd_most_recent_spud_year` | Float | Most recent year in which a well was spudded (drilling commenced) in this county. | 17,516 |
| `nmocd_most_recent_prod_year` | Float | Most recent year of recorded production for any well in this county. Derived from the PHMSA epoch-millisecond `last_production_date` field; values above year 2096 treated as sentinel nulls and excluded. | 17,516 |
| `nmocd_active_wells` | Float | Count of wells with "Active" status. Equal to `nmocd_total_wells` because the API endpoint serves active wells only. | 17,516 |
| `nmocd_plugged_abandoned_wells` | Float | Count of plugged/abandoned wells. Zero throughout because the API does not serve inactive records. Retained for schema consistency with PA DEP columns. | 17,516 |
| `nmocd_gas_wells` | Float | Wells with type containing "Gas", "Coal Bed Methane", "Methane", or "CO2". | 17,516 |
| `nmocd_oil_wells` | Float | Wells with type containing "Oil". | 17,516 |
| `nmocd_recent_spud_count` | Float | Wells spudded in 2019–2025. Indicates active drilling pressure. NM has 3,256 recently-spudded wells across 12 counties. | 17,516 |
| `has_nmocd_well_data` | Boolean | `True` if this facility is in an NM county with at least one registered OCD well. | 527,983 (100%) |

---

### 3.9 Risk Scores

Computed by `src/features/build_risk_scores.py` from the integrated feature set. All numeric scores are on a 0–100 scale. See Section 4 for full scoring methodology.

| Column | Type | Description | Coverage |
|---|---|---|---|
| `compliance_risk_score` | Float | Facility-level compliance risk (0–100). Derived from ECHO enforcement history. Zero for facilities with no ECHO record. | 527,983 (100%) |
| `tri_release_score` | Float | Facility-level toxic release risk (0–100). Non-zero only for the 3,919 facilities with TRI release data. Zero does not imply no risk — it indicates no TRI reporting obligation or no releases above TRI reporting thresholds. | 527,983 (100%) |
| `pipeline_context_score` | Float | County-level pipeline incident burden (0–100). Derived from PHMSA data. Zero for facilities in counties with no recorded pipeline incidents 2019–2024. | 527,983 (100%) |
| `state_resource_score` | Float | State-specific resource extraction and contamination burden (0–100). Normalised within each state independently (TX, PA, NM each span 0–100). ME receives 0 (no state-specific source ingested). Not included in the composite score to preserve cross-state comparability. | 527,983 (100%) |
| `composite_risk_score` | Float | Weighted composite of compliance, TRI, and pipeline components (0–100). See Section 4 for weights and the TRI-absent renormalisation rule. | 527,983 (100%) |
| `composite_percentile_rank` | Float | Percentile rank (0.0–100.0) of each facility's composite score within the full 527,983-row dataset. Suitable for continuous colour-scaling in Power BI maps. | 527,983 (100%) |
| `risk_tier` | String | Categorical screening label derived from the composite percentile rank. Values: `HIGH` (≥ P90), `MEDIUM` (P50–P90), `LOW` (< P50). September 2026 thresholds: HIGH ≥ 20.49, LOW < 5.19. | 527,983 (100%) |

---

## 4. Risk Score Methodology

### 4.1 Normalisation

Numeric features are transformed before weighting:

- **log1p + min-max:** `score = (log(1 + x) - min) / (max - min)`, scaled to the weight. Used for skewed continuous variables (release totals, incident counts, penalties). The log transform reduces the influence of extreme outliers while preserving rank order. Min and max are computed across the entire 527,983-row dataset for cross-facility comparability, except for state resource features (see 4.4).
- **Binary (Y/N or True/False):** Converted to 1.0 or 0.0 before applying the weight. No normalisation needed.

### 4.2 Compliance Risk Score (0–100)

Applies to facilities with at least one ECHO field populated. Zero for FRS-only facilities.

| Feature | Transform | Weight |
|---|---|---|
| `fac_qtrs_with_nc` | log1p + min-max | 30 |
| `fac_formal_action_count` | log1p + min-max | 25 |
| `fac_total_penalties` | log1p + min-max | 20 |
| `fac_snc_flag == 'Y'` | binary | 15 |
| `caa_hpv_flag == 'Y'` | binary | 10 |

### 4.3 TRI Release Score (0–100)

Non-zero only for the 3,919 facilities with TRI release records. Facilities without TRI data score 0 on this component.

| Feature | Transform | Weight |
|---|---|---|
| `total_releases_sum` | log1p + min-max | 35 |
| `any_carcinogen == True` | binary | 25 |
| `any_pbt == True` | binary | 20 |
| `any_pfas == True` | binary | 15 |
| `distinct_chemical_count` | log1p + min-max | 5 |

### 4.4 Pipeline Context Score (0–100)

County-level. Zero for facilities in counties with no PHMSA incidents 2019–2024.

| Feature | Transform | Weight |
|---|---|---|
| `phmsa_incident_count` | log1p + min-max | 40 |
| `phmsa_significant_count` | log1p + min-max | 35 |
| `phmsa_fatalities_total` | log1p + min-max | 15 |
| `phmsa_injuries_total` | log1p + min-max | 10 |

### 4.5 State Resource Context Score (0–100)

Normalised within each state so each state independently spans 0–100. Excluded from the composite to preserve cross-state comparability of the composite score.

**Texas:** `tceq_lpst_active_sites` (50) + `tceq_lpst_high_priority_sites` (30) + `r3_net_gas_total_mcf` (20), all log1p + min-max within TX.

**Pennsylvania:** `padep_unconventional_wells` (55) + `padep_recent_permit_count` (45), both log1p + min-max within PA.

**New Mexico:** `nmocd_total_wells` (55) + `nmocd_recent_spud_count` (45), both log1p + min-max within NM.

**Maine:** 0 (no state-specific source ingested in v1.0).

### 4.6 Composite Risk Score (0–100) and TRI Renormalisation

For facilities **with** TRI release data (3,919 rows):

```
composite = 0.35 × compliance + 0.40 × tri_release + 0.25 × pipeline
```

For facilities **without** TRI release data (524,064 rows), weights are renormalised so the composite still spans 0–100:

```
composite = (0.35/0.60) × compliance + (0.25/0.60) × pipeline
         = 0.583 × compliance + 0.417 × pipeline
```

This prevents TRI-absent facilities from being artificially capped at 60% of the maximum score purely because they lack TRI reporting obligations.

### 4.7 Risk Tier Assignment

Tiers are derived from the percentile distribution of `composite_risk_score` across all 527,983 facilities. Percentile thresholds are recalculated on each run; the September 2026 values are shown below.

| Tier | Criterion | Sep 2026 threshold | Count | Share |
|---|---|---|---|---|
| HIGH | ≥ 90th percentile | ≥ 20.49 | 52,896 | 10.0% |
| MEDIUM | 50th–90th percentile | 5.19–20.49 | 217,256 | 41.1% |
| LOW | < 50th percentile | < 5.19 | 257,831 | 48.8% |

**Interpretation note:** The pipeline context score is the dominant contributor to the composite for most facilities, because PHMSA county-level incident data covers 74% of the index and provides the most uniformly populated continuous signal. Compliance and TRI components are non-zero only for facilities with documented enforcement history or TRI reporting obligations, respectively, making the score distribution right-skewed. HIGH-tier facilities typically combine elevated pipeline incident county context with at least one facility-level indicator (enforcement action or toxic release).

---

## 5. Data Quality Notes

| Source | Issue | Impact | Status |
|---|---|---|---|
| TCEQ LPST | Year 2103 in REPORTED field (data-entry error; likely 2023) | `tceq_lpst_recent_sites_2019_2025` = 0 for all counties | Source anomaly; awaiting TCEQ correction. Active/total counts unaffected. |
| TCEQ LPST | One record with REPORTED year 1971 (predates TCEQ's founding) | Negligible; excluded from recent-year calculations | Source anomaly |
| Texas RRC R-3 | 41% of plant coordinates are placeholder (30.0°N, −100.0°W) | 561 of 1,451 plants could not be spatially matched | Documented; 890 valid-coord plants participated in the 500 m spatial join |
| NM OCD | FTP server and REST API inaccessible; UNM NHNM mirror used | Coverage limited to active wells only (no plugged/abandoned records) | Documented; no impact on active-well counts |
| PHMSA GD/LNG | Gas Distribution and LNG forms have no county field in their PHMSA schema | 87 GD+LNG incidents excluded from county-level join | Documented; GT (181) and HL (962) incidents — the dominant types — are fully included |
| EPA TRI 2025 | TRI reporting cycle means 2025 data not yet published | Analysis period effectively 2019–2024 | Confirmed system-wide; not a data-quality defect |
| PA DEP | PASDA release is Sept 2025; well permits after that date not captured | Minimal impact for 2019–2025 analysis | Acknowledged; update script with new release URL when available |

---

## 6. Source Provenance

| Source | Agency | Public URL | Data vintage | Connector script |
|---|---|---|---|---|
| EPA FRS | US EPA | https://www.epa.gov/frs | Downloaded Sept 2026 | `fetch_frs.py` |
| EPA ECHO Exporter | US EPA | https://echo.epa.gov/tools/data-downloads | Downloaded Sept 2026 | `fetch_echo.py` |
| EPA TRI Basic Data | US EPA | https://data.epa.gov/efservice/ | 2019–2024 (queried Sept 2026) | `fetch_tri_facility.py`, `fetch_tri_releases.py` |
| PHMSA Flagged Incidents | US DOT PHMSA | https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data | 2019–2024 (downloaded Sept 2026) | `fetch_phmsa_incidents.py` |
| Texas RRC R-3 | Texas RRC | https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report | Aug 2025–Aug 2026 | `fetch_rrc_r3_gas_plants.py`, `join_rrc_r3_to_master.py` |
| TCEQ LPST | Texas TCEQ | https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt | Downloaded Sept 2026 (all historical) | `fetch_tceq_lpst.py` |
| PA DEP Well Locations | PA DEP via PASDA | https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=1088 | Sept 2025 release | `fetch_padep_wells.py` |
| NM OCD Wells | NM EMNRD OCD via UNM NHNM | https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/ActiveOilandGasWells/MapServer/3 | Queried Sept 2026 | `fetch_nmocd_wells.py` |

---

*End of Data Dictionary v1.0*