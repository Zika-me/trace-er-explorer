# TRACE-ER Explorer — Public Data Source Register

This register is the provenance manifest required by Section 3.1 of the Development Project Scope. It must be updated at the moment each source is actually downloaded or queried — not filled in retroactively from memory. Fields left as "TBD" below are placeholders to be completed during Step 2 (source connectors and download scripts).

Rules for every source:
- Archive the exact download file, or record the exact API query, along with the access date.
- Preserve original filenames and source documentation.
- Never hand-edit raw files; all transformations belong in versioned code.
- If a source changes format, keep the prior snapshot and version the parser rather than overwriting it.

## Required national sources

| Source | Use in project | Official URL | Access date | File/version | Checksum | License/usage note |
|---|---|---|---|---|---|---|
| EPA ECHO Data Downloads (ECHO Exporter) | Facility compliance, inspections, violations, enforcement, penalties | Landing page: https://echo.epa.gov/tools/data-downloads — direct download: https://echo.epa.gov/files/echodownloads/echo_exporter.zip | 2026-09-16 (real download completed, not just link-verified) | ECHO_EXPORTER.CSV inside echo_exporter.zip; zip = 428,327,103 bytes; 3,180,415 national rows, 133 columns | sha256=fbaf4dd0de9531e837c44739894429198eec8f4ad43fe23a5fb430f36f3a3350 | Public domain, U.S. government data |
| EPA Facility Registry Service (FRS) Data | Facility identity, program linkages, NAICS/SIC, addresses, coordinates | Landing page: https://www.epa.gov/frs/epa-frs-facilities-state-single-file-csv-download — direct download: https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip | 2026-09-15 (real download completed, not just link-verified) | NATIONAL_SINGLE.CSV inside national_single.zip; zip = 351,697,980 bytes; 5,329,863 national rows, 39 columns | sha256=20296ac41aca625546d84c11c1d238686ce6d65860b36760c8f1871ad8cd1093 | Public domain, U.S. government data |
| EPA FRS Geospatial Data Download Service | National/state geospatial files for regulated facilities | https://www.epa.gov/frs/geospatial-data-download-service | TBD | TBD | TBD | Public domain, U.S. government data |
| EPA TRI (facility identity only) | Facility identity, address, coordinates, FRS/registry linkage — NOT release quantities yet, see note | Web download page's button is JavaScript-driven with no static URL; using EPA Envirofacts efservice REST API instead: https://data.epa.gov/efservice/tri_facility/state_abbr/{STATE}/CSV, verified live 2026-09-17 | 2026-09-17 (API endpoint verified live via search; connector written, dry-run tested; not yet run against the real API) | tri_facility table, per state (TX/PA/NM/ME) | TBD — set on first real run | Public domain, U.S. government data |
| PHMSA Pipeline Incident/Accident Data | Pipeline incidents, consequences, release details | https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data | TBD | TBD | TBD | Public domain, U.S. government data |
| USGS Water Data APIs | Water monitoring locations and quality observations | https://api.waterdata.usgs.gov/docs/ | TBD | TBD | TBD | Public domain, U.S. government data |

## Required state modules

| Source | Use in project | Official URL | Access date | File/version | Checksum | License/usage note |
|---|---|---|---|---|---|---|
| Texas RRC Oil & Gas Production Data | TX operational-intensity context | https://www.rrc.texas.gov/oil-and-gas/research-and-statistics/production-data/ | TBD | TBD | TBD | Public state data |
| Texas RRC Public GIS Viewer | TX oil, gas, well, pipeline locations | https://www.rrc.texas.gov/resource-center/research/gis-viewer/ | TBD | TBD | TBD | Public state data |
| TCEQ Raw Environmental Data Downloads | TX air, water, compliance, spill/release, waste, geospatial | https://www.tceq.texas.gov/agency/data/lookup-data/download-data.html | TBD | TBD | TBD | Public state data |
| Pennsylvania DEP Oil and Gas Reports | PA production, permits, inspections, violations, enforcement, waste | https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports | TBD | TBD | TBD | Public state data |
| New Mexico OCD Data / Statistics | NM production, produced water, flaring/venting, wells, inspections, incidents, spills | https://www.emnrd.nm.gov/ocd/ocd-data/ | TBD | TBD | TBD | Public state data |

## Optional local case study

| Source | Use in project | Official URL | Access date | File/version | Checksum | License/usage note |
|---|---|---|---|---|---|---|
| Maine DEP Maps and Data | Petroleum spill, tank, and remediation case study | https://www.maine.gov/dep/maps-data/index.html | TBD | TBD | TBD | Public state data |
| Maine DEP GIS Maps & Data Files | Geospatial layers for spill/tank/remediation sites | https://www3.maine.gov/dep/gis/datamaps/ | TBD | TBD | TBD | Public state data |

## Source-verification note

The URLs above were carried forward from the Development Project Scope v1.2, which records them as verified against official agency pages on September 4, 2026. Re-check availability and data dictionaries at the start of development and again immediately before publication — government data portals do restructure without much notice.

**Note on the FRS row above:** the direct download URL was fetched and confirmed live on 2026-09-11, then actually run for real on 2026-09-15, producing 5,329,863 national rows / 526,992 rows across TX, PA, NM, ME combined (see the source-volume log below). **Entity-scoping decision:** at 526,992 records, FRS alone vastly exceeds the ~5,000–13,000 unique-analytical-entity target in the Requirements Spec, because FRS registers every facility under any EPA program, not just the oil/gas and industrial facilities this project is actually about. The project owner decided on 2026-09-15 to defer narrowing this down (via NAICS/SIC filtering or requiring a cross-source match) until Step 3 (master facility index) — all FRS records are being kept for now. This means Step 3 needs to either implement that scoping rule before finalizing the index, or explicitly re-confirm that all ~527K records should carry forward as candidate entities.

**Note on the ECHO row above:** run for real on 2026-09-16, producing 3,180,415 national rows / 311,717 rows across TX, PA, NM, ME combined (TX 170,580 / PA 100,255 / NM 27,805 / ME 13,077). All 6 core identity fields matched on the first guess — no naming surprises like FRS's NAICS/SIC miss. The connector was then expanded to also capture 24 confirmed compliance-summary and coordinate-quality fields, read directly off the real 133-column header (see `docs/Data_Dictionary.md` and `docs/Analytical_Data_Model.md`'s `echo_compliance_summary` table).

**Critical data-quality finding, 2026-09-16:** the real run reported 0 of 311,717 rows missing latitude/longitude. This does NOT mean 0 imprecise coordinates. ECHO's `FAC_COLLECTION_METHOD` and `FAC_ACCURACY_METERS` fields (now captured by the connector) show that many facilities have no GPS-precision location at all — ECHO backfills a state, county, or zip-code centroid instead of leaving the coordinate null, with accuracy values observed as coarse as 100,000 meters. Any tight-radius spatial join using ECHO coordinates (the "within 1 mile" style rules in Section 9 of the scope document) must check `coord_accuracy_value` first — a present coordinate is not the same as a precise one. This is now documented at the field level, not just here.

**Note on the TRI row above:** TRI's web download page has a JavaScript-driven "Download data file" button with no static URL to verify — unlike FRS and ECHO, there was no direct zip link to confirm. Instead, `fetch_tri.py` uses EPA's documented Envirofacts efservice REST API, verified live via search results on 2026-09-17 (including one that returned an actual labeled CSV header, not just documentation). **This connector covers facility identity only** (name, address, coordinates, FRS/registry linkage) — it does NOT pull chemical release quantities, which is TRI's core analytical value. The tables for that (`tri_release_qty`, `tri_reporting_form`) are confirmed to exist by name but their columns are not confirmed; building that connector requires a real header sample first, the same verification standard applied to everything else in this project. Two API-specific gotchas are defended against in code (see `docs/Data_Dictionary.md`): an unrecognized filter column is silently ignored and returns the full national table instead of erroring, and chained multi-table joins have been reported to silently drop rows.

## Source-volume log (to be populated during Step 2)

| Source | Downloaded rows | Accepted rows | Rejected/quarantined | Duplicate rows | Linked rows | Final unique entities |
|---|---|---|---|---|---|---|
| EPA ECHO | 3,180,415 (national) | 311,717 (TX 170,580 / PA 100,255 / NM 27,805 / ME 13,077) | 2,868,698 (other states, out of scope by state filter) | Not yet computed (dedup/join happens at Step 3) | Not yet computed (FRS join happens at Step 3) | TBD — pending Step 3 |
| EPA FRS | 5,329,863 (national) | 526,992 (TX 338,529 / PA 124,889 / NM 44,068 / ME 19,506) | 4,802,871 (other states, not rejected for quality reasons — out of scope by state filter) | Not yet computed (dedup happens at Step 3) | Not yet computed | TBD — pending Step 3 entity-scoping decision (currently: keep all 526,992) |
| EPA TRI | | | | | | |
| PHMSA | | | | | | |
| USGS Water Quality | | | | | | |
| Texas RRC | | | | | | |
| TCEQ | | | | | | |
| Pennsylvania DEP | | | | | | |
| New Mexico OCD | | | | | | |
| Maine DEP (optional) | | | | | | |
