# TRACE-ER Explorer — Release Manifest

**Release:** v1.0  
**Generated:** 2026-09-20 12:19 UTC  
**States:** TX, PA, NM, ME  
**Master index rows:** 527,983  
**Master index columns:** 111  

---

## Release Contents

SHA-256 checksums and file sizes are computed at manifest generation time.  
Verify a file with: `shasum -a 256 <filename>` (macOS/Linux) or `Get-FileHash <filename> -Algorithm SHA256` (PowerShell).

### Processed data outputs

| File | Size | SHA-256 |
|---|---|---|
| `data/processed/master_risk_scores.csv` | 229.0 MB | `38ba52cc12a00f71...` |
| `data/processed/facility_risk_summary.csv` | 128.6 MB | `2fa4f59659b34235...` |
| `data/processed/tri_release_features.csv` | 318.0 KB | `f4dfb4683904ffbd...` |
| `data/processed/rrc_r3_plant_features.csv` | 165.7 KB | `75d8b8dc86b1a1b1...` |
| `data/processed/phmsa_county_features.csv` | 15.8 KB | `5365be0053f67d5e...` |
| `data/processed/tceq_lpst_county_features.csv` | 8.3 KB | `64f873e242e8e4c9...` |
| `data/processed/padep_county_features.csv` | 2.8 KB | `1048c2644fb5f6f9...` |
| `data/processed/nmocd_county_features.csv` | 801.0 B | `26c37c7404875855...` |

### Cleaned interim tables

| File | Size | SHA-256 |
|---|---|---|
| `data/interim/phmsa_incidents.csv` | 138.6 KB | `37994be57b83081e...` |
| `data/interim/tceq_lpst_sites.csv` | 6.0 MB | `98ac080ea0c9caf3...` |
| `data/interim/rrc_r3_gas_plants.csv` | 817.9 KB | `bf42e1e324cf8cce...` |
| `data/interim/padep_wells.csv` | 37.8 MB | `9863ea30af0f102a...` |
| `data/interim/nmocd_wells.csv` | 8.7 MB | `c983913cfe3b30e6...` |

### Documentation

| File | Size | SHA-256 |
|---|---|---|
| `docs/TRACE_ER_Explorer_Data_Dictionary_v1_0.md` | 30.9 KB | `7c18f479296ab608...` |
| `docs/TRACE_ER_Explorer_Validation_Report_v1_0.md` | 18.5 KB | `6f69443b677e09e3...` |
| `docs/TRACE_ER_Explorer_Technical_Implementation_Guide_v1_0.md` | 24.6 KB | `a0159406e7f860b9...` |
| `docs/TRACE_ER_Explorer_White_Paper_v1_0.md` | 19.8 KB | `79e252803cc352bc...` |
| `docs/TRACE_ER_Explorer_Institutional_Brief_v1_0.md` | 6.9 KB | `f24f90d77f23b71a...` |
| `docs/TRACE_ER_Explorer_Power_BI_Dashboard_Guide_v1_0.md` | 0.0 B | `e3b0c44298fc1c14...` |

### Source code — ingest connectors

| File | Size | SHA-256 |
|---|---|---|
| `src/ingest/fetch_frs.py` | 6.2 KB | `0234ceb2874ec716...` |
| `src/ingest/fetch_echo.py` | 9.6 KB | `2b8d8e7daaa73cfb...` |
| `src/linkage/build_master_index.py` | 15.4 KB | `35145f6e873075db...` |
| `src/ingest/fetch_tri.py` | 7.1 KB | `02e1b59aabfaf58e...` |
| `src/ingest/fetch_tri_releases.py` | 12.4 KB | `ebe74ca8626cfda7...` |
| `src/features/aggregate_tri_release_features.py` | 7.0 KB | `354c80372e730f48...` |
| `src/features/join_tri_features_to_master_index.py` | 7.6 KB | `f31c411a6c80524e...` |
| `src/ingest/fetch_rrc_r3_gas_plants.py` | 10.5 KB | `8189d47ce89746ac...` |
| `src/ingest/join_rrc_r3_to_master.py` | 12.2 KB | `b81c0521be3e74bb...` |
| `src/ingest/fetch_phmsa_incidents.py` | 19.4 KB | `30d4957a3d1be6d5...` |
| `src/ingest/fetch_tceq_lpst.py` | 11.6 KB | `3c68104665c26101...` |
| `src/ingest/fetch_padep_wells.py` | 10.4 KB | `98f3f8d615a71082...` |
| `src/ingest/fetch_nmocd_wells.py` | 12.6 KB | `995865e8c1f4c51b...` |

### Source code — linkage scripts

| File | Size | SHA-256 |
|---|---|---|
| `src/linkage/build_master_index.py` | 15.4 KB | `35145f6e873075db...` |
| `src/linkage/join_tri_releases_to_facility.py` | 7.4 KB | `e985803c60a32c3b...` |

### Source code — features

| File | Size | SHA-256 |
|---|---|---|
| `src/features/build_risk_scores.py` | 16.0 KB | `15c523340a3232ce...` |

### Validation and audit

| File | Size | SHA-256 |
|---|---|---|
| `validation/source_volume_log.csv` | 15.4 KB | `18762568361285d6...` |
| `outreach/TRACE_ER_outreach_feedback_log.csv` | 1.1 KB | `95d6fc0b547c0c6a...` |

### Release metadata

| File | Size | SHA-256 |
|---|---|---|
| `scripts/generate_release_manifest.py` | 5.7 KB | `92602fba89e79515...` |
| `TRACE_ER_Explorer_v1_0_Release_Manifest.md` | 4.2 KB | `7e9eca581440ccea...` |

---

## Summary

| Item | Value |
|---|---|
| Total files | 39 |
| Total size | 412.0 MB |
| Missing files | 0 |
| Generated | 2026-09-20 12:19 UTC |

---

*TRACE-ER Explorer v1.0 | September 2026*  
*All source data is public and freely accessible.*