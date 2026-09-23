# TRACE-ER Explorer

**Multi-State Environmental Risk Screening and Remediation Prioritization Prototype**

Status: Pre-build (Week 1 — requirements and repository setup)
Version target: v1.0
Document owner: Ngozika Confidence Akosile, Product Owner and Environmental Domain Lead

## What this is

TRACE-ER Explorer is a proof-of-concept screening tool that pulls together public U.S. environmental and regulatory data — facility identity, compliance history, toxic releases, pipeline incidents, water-quality context, and oil-and-gas operational data — into a single, transparent risk-priority view. It is built and validated across three core states (Texas, Pennsylvania, New Mexico), with Maine as an optional complementary case study for petroleum spill and remediation screening.

The prototype produces priority tiers, reason codes, and confidence indicators for each facility or site. It does not make legal compliance determinations, does not diagnose health risk, and does not claim real-time monitoring unless a data feed is actually real time.

## What this is not

- Not a regulatory compliance or enforcement system.
- Not a machine-learning risk model (rule-based and transparent-weighted scoring only, for v1.0).
- Not proof of causation from spatial proximity alone.
- Not a finished production system — this is an MVP proof-of-concept.

## Repository layout

```
docs/         methodology, data dictionary, limitations, screenshots
config/       source URLs, parameters, thresholds, geography
data/raw/     local-only or lightweight samples (respect file-size limits)
data/interim/ intermediate cleaned data
data/processed/ analysis-ready tables
src/ingest/   source connectors and download scripts
src/clean/    standardization and QA logic
src/linkage/  entity resolution and geospatial linkage
src/features/ feature engineering
src/scoring/  risk-priority scoring engine
src/reporting/ report and export generation
src/app/      dashboard/app code (Power BI supporting assets, optional Streamlit)
tests/        unit and validation tests
notebooks/    exploration only, not production logic
outputs/maps/ exported map images
outputs/reports/ exported screening reports
validation/   validation reports, sensitivity analysis, review records
```

## Core data sources (v1.0)

| Source | Role |
|---|---|
| EPA ECHO / ECHO Exporter | Compliance, inspections, violations, enforcement |
| EPA FRS / FRS Geospatial | Facility master identity and coordinates |
| EPA TRI Basic Data | Chemical releases and waste management |
| PHMSA Pipeline Incident Data | Pipeline incidents and consequences |
| Texas RRC | Production and operational context (TX) |
| TCEQ | Spills and environmental records (TX) |
| Pennsylvania DEP Oil and Gas | Production, permits, inspections (PA) |
| New Mexico OCD | Production, incidents, spills (NM) |
| USGS Water Quality Portal | Water monitoring context (recommended) |
| Maine DEP | Optional petroleum spill/remediation case study |

Full source detail, URLs, and access-date logging rules live in `docs/Source_Register.md`.

## License and use

Public data sources retain their original licensing and usage terms; see `docs/Source_Register.md` for source-level notes. Add a repository license before public release.
