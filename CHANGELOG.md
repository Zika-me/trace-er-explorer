# Changelog

All notable changes to TRACE-ER Explorer will be documented in this file.

## [Unreleased] — 2026-09-17 — EPA TRI facility connector built

### A different problem than FRS/ECHO: no static download URL at all

TRI's "TRI Basic Data Files" web page has a JavaScript-driven "Download data file" button — it resolves to a `javascript:void(0)` placeholder, not a real URL. Unlike FRS and ECHO, there was no zip link to find and verify.

**Resolution:** EPA's Envirofacts efservice REST API (`data.epa.gov/efservice`) is a documented, working alternative, confirmed live via search results on 2026-09-17 — including one result that returned an actual labeled CSV header from a real fetch of `tri_facility/state_abbr/VA/CSV`, not just documentation describing the API. That real header is what this connector's column crosswalk is built from.

**A prior assumption corrected in the open:** earlier this session it was assumed TRI likely shares FRS/ECHO's REGISTRY_ID system. The real fetched sample initially looked like it might not — TRI's own primary key (`tri_facility_id`, e.g. `96701CLFRN99195`) is a TRI-internal scheme, not the numeric REGISTRY_ID format. Further verification found the real header does separately include `epa_registry_id` (format `110002097258`, matching FRS/ECHO exactly) as its own column — so the original assumption was right, just for the wrong initial reason. Corrected transparently rather than silently.

### Two real, documented API gotchas found before writing any connector code, and defended against directly

1. **A filter naming a column the table doesn't have is silently ignored**, and the full unfiltered/national table is returned instead of an error — confirmed via a third-party tool's own measurement (`tri_facility/bogus_column/CO/COUNT` returns the same count as unfiltered). Defended against with a new `common.verify_filtered_count()`, which raises immediately if a "filtered" count isn't both positive and strictly smaller than the unfiltered count. This check is mandatory in `fetch_tri.py`, run before any CSV body is trusted, not an optional nicety.
2. **Chained multi-table joins in one efservice URL can silently drop rows**, per the same third-party source. `fetch_tri.py` queries `tri_facility` alone, per state — it does not attempt a chained join to pull release data in the same request.

Also added `common.get_efservice_count()` to parse the API's COUNT/JSON response, written defensively (tries several plausible JSON shapes, raises a clear error if none match) since the exact response shape is based on third-party documentation, not a live-verified fetch from this environment.

### Connector built and tested

`src/ingest/fetch_tri.py` pulls `tri_facility` per target state (TX/PA/NM/ME — TRI's downloads are naturally per-state, so no post-hoc filtering of a national file is needed the way FRS/ECHO required). Confirmed real columns captured: `epa_registry_id` (join key), `frs_id`, facility identity/address fields, and TRI's own coordinate-quality metadata (`pref_accuracy`, `pref_collect_meth`, `pref_horizontal_datum`) plus both the as-reported (`fac_latitude`/`fac_longitude`) and EPA's "preferred/cleaned" (`pref_latitude`/`pref_longitude`) coordinate pairs.

**Scope, stated plainly: this is facility identity only.** It does not pull chemical release quantities — TRI's actual core analytical value. The tables for that (`tri_release_qty`, `tri_reporting_form`) are confirmed to exist by name (found via the same search process) but their column headers are NOT confirmed. Building that connector from memory of just the table names would repeat exactly the mistake this project has been careful to avoid — it needs a real header sample first, the same standard applied to every other source.

7 new tests, all passing (73 total), including a test that reproduces the documented "filtered count equals unfiltered count" bug signature and confirms it raises rather than silently proceeding. Full dry run performed across all four target states with mocked network responses, confirming per-state fetch, combination, coordinate-completeness detection, and logging all work correctly end to end. Dry-run artifacts were written to the actual repo paths this time (not `/tmp`) and cleaned up before packaging — caught and fixed as part of the standard pre-ship check.

### Pending
- **Not yet run against the real API** — network access to data.epa.gov isn't available from this build environment. Run `fetch_tri.py` for real, confirm the "Resolved columns" log line and the per-state row counts, and check for the "Row count mismatch" warning (COUNT endpoint vs. CSV body length) — expected to be silent, but worth confirming on first live run.
- Fetch a real header sample for `tri_release_qty` and/or `tri_reporting_form` before building a release-quantity connector — this is the actual next step for TRI to deliver its core value.
- Join TRI facility data into the master index once run for real (shares `epa_registry_id` with FRS/ECHO, so this should be a straightforward three-way outer join extension of `build_master_index.py`, not a new matching problem).
- Real match-rate finding to revisit for the entity-scoping question: FRS ~527K rows, ECHO ~312K, so even a full match would leave far more entities than the ~5,000–13,000 target.
- The EXACT_ID-only scope of the master index build is a real limitation — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's and FRS's multi-value fields (`FAC_NAICS_CODES`/`FAC_SIC_CODES`, `NAICS_CODES`/`SIC_CODES`/`PGM_SYS_ACRNMS`).
- Decide whether/when to extract the ~90 remaining per-program ECHO fields.
- Remaining source connectors: TRI release quantities, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16 (continued, part 5) — investigation closed, fix confirmed

Both fixed scripts were run for real. Results confirm the diagnosis exactly, not just directionally:

- `check_duplicate_ids.py`: FRS clean (0 nulls, 0 duplicates). ECHO: `null_id_count=441`, `duplicate_id_count=0` — the gap was 100% blank registry_ids, zero actual duplicate rows. Master index: `null_id_count=441` (matches ECHO's, as expected since these rows only ever existed in ECHO), `unique_non_null_ids=527919`.
- `build_master_index.py` (with the fix applied): raw outer join still 528,360 rows; 441 correctly excluded for having no registry_id; final index 527,919 rows. `528,360 − 441 = 527,919` — matches the duplicate-checker's independent count exactly, cross-validating both fixes against each other.
- State agreement (310,349 checked, 0 disagree) and coordinate agreement (252,848 checked, median 0.0 km, max 28.9 km, all under 50 km) are unchanged from the pre-fix run, as expected — the null-ID rows only ever existed in the ECHO-only bucket and never touched the matched-in-both entities.
- Net effect on the ECHO-only bucket: of the original 1,368, 441 were null-ID rows now correctly excluded from the index entirely; 927 are genuine entities with a real registry_id that ECHO has compliance data for for but FRS's target-state subset does not. Re-running `diagnose_echo_only.py` against the now-clean master index will investigate that reduced, more accurate number automatically, without needing further changes to that script.

This closes out the investigation that started as an apparent duplicate-row bug and turned out to be a null-handling bug in the diagnostic itself, plus a real (now-fixed) data-quality gap in ECHO's registry_id coverage.

### Final confirmation — diagnose_echo_only.py re-run against the clean master index

Result: 927 total ECHO-only rows, 927 unique IDs, 0 duplicate-row gap. `found_under_target_state` still 0 (no bug). 2 found under LA (benign filtering artifact, already explained). 925 genuinely absent from FRS's national extract entirely (~0.3% of ECHO's 311,717 target-state rows) — small enough not to be alarming, but real and worth remembering as a known, quantified gap in FRS/ECHO cross-referencing rather than an assumed 100% overlap.

**Investigation fully closed.** What started as an apparent duplicate-row bug in the master index build turned out to be: (1) a null-handling bug in the diagnostic script itself, now fixed and regression-tested, and (2) a real, now-quantified and correctly-excluded set of 441 ECHO rows with no registry_id. The master index (527,919 rows) and its supporting diagnostics are internally consistent and cross-validated against each other.

### Pending
- Real match-rate finding to revisit for the entity-scoping question: FRS has ~527K rows, ECHO ~312K, so even a full FRS∩ECHO match would still leave far more entities than the ~5,000–13,000 target.
- The EXACT_ID-only scope of the master index build is a real limitation — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's and FRS's multi-value fields (`FAC_NAICS_CODES`/`FAC_SIC_CODES`, `NAICS_CODES`/`SIC_CODES`/`PGM_SYS_ACRNMS`).
- Decide whether/when to extract the ~90 remaining per-program ECHO fields.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16 (continued, part 4)

### The 440-row gap was a bug in my own diagnostic, not duplicate data

Ran `check_duplicate_ids.py` for real. Result looked internally impossible: ECHO showed `total_rows=311717`, `unique_ids=311276` (a 441 gap), but `duplicate_id_count=0` and `extra_rows_from_duplicates=0`. Given how the script computed those numbers, that combination should have been mathematically impossible — treated as a bug to trace immediately, not accepted at face value.

**Root cause found:** pandas' `value_counts()` and `nunique()` both silently drop null/NaN values by default. The original `check_duplicate_ids` called `.astype(str)` before computing anything, but a column's null values had already round-tripped through a CSV write/read cycle and were still real NaN at that point — `value_counts()`'s default `dropna=True` excluded them entirely from BOTH the unique count and the duplicate check. They were invisible to the diagnostic while still counted in `total_rows`, producing exactly this kind of gap. Verified by reproducing the exact bug with a small `None`-containing series, then confirming a simulated 311,276-unique-IDs-plus-441-nulls dataset reproduces the real numbers exactly.

**This means the real finding is different from what was suspected, and arguably more important:** approximately 441 rows in ECHO's interim data (and, since the master index carries `registry_id` through as `master_id`, correspondingly in the master index) most likely have a BLANK `registry_id` — not a duplicate one. A row with no ID at all has no usable identifier in the final table, which is a data-quality issue distinct from and more serious than duplication.

**Fixed:** `check_duplicate_ids` now counts null IDs explicitly, before any `value_counts()` call, and returns `null_id_count` separately from `duplicate_id_count`. Added an internal assertion (`null_id_count + unique_non_null_ids + extra_rows_from_duplicates == total_rows`) so this class of accounting bug cannot recur silently — a future violation raises immediately with the exact numbers, rather than producing a quietly-wrong report. `write_report` now flags a nonzero null count separately from a nonzero duplicate count, since they call for different fixes. Added a regression test locking in the exact real numbers (311,717 / 441 / 311,276) as a permanent check. 57 tests total, all passing. Dry run repeated with both null IDs and a true duplicate present together, confirming both get correctly separated rather than conflated.

**Also fixed while this was fresh:** `build_master_index.py` was labeling every row `linkage_confidence = EXACT_ID` uniformly, including any row with no registry_id at all — which is factually wrong, since there's no ID to be exact about. `build_master_index()` now excludes rows with a null registry_id before assigning confidence labels, returns the dropped count alongside the index, and the build report surfaces that count explicitly. Added a regression test constructing exactly this scenario (a null-registry_id ECHO row) and confirming it's excluded. 58 tests total, all passing. Dry run confirmed the exclusion and reporting work correctly end to end, with no leakage into the repo's real data/validation folders.

**Not yet confirmed against your real file** whether these 441 rows are truly blank in ECHO's own raw export, or became blank somewhere in `fetch_echo.py`'s processing — that determines whether the fix belongs in the connector (filter or flag rows with no registry_id) or is just a property of the source data to document and live with.

### Pending
- **Priority:** re-run `check_duplicate_ids.py` with the fix and confirm `null_id_count` is close to 441 for ECHO (not `duplicate_id_count`). If confirmed, inspect a sample of ECHO's raw rows with blank REGISTRY_ID (a quick `df[df['REGISTRY_ID'].isna()]` on the raw extracted CSV) to understand why they lack an ID — likely a facility pending FRS cross-reference, but worth checking rather than assuming.
- Decide how `fetch_echo.py` (and `build_master_index.py`) should handle rows with a blank registry_id going forward — options include excluding them from the master index (since a blank master_id is not a usable key), or keeping them with an explicit `UNRESOLVED` linkage_confidence tag rather than `EXACT_ID`, which is currently applied uniformly and would be wrong for these rows.
- The original duplicate-row concern (whether ECHO has genuine repeated registry_ids beyond null handling) is still worth re-checking now that the diagnostic is fixed — the corrected report should be trusted this time, but hasn't been re-run against real data yet.
- Real match-rate finding to revisit for the entity-scoping question: FRS has ~527K rows, ECHO ~312K, so even a full FRS∩ECHO match would still leave far more entities than the ~5,000–13,000 target.
- The EXACT_ID-only scope of the master index build is a real limitation — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's and FRS's multi-value fields (`FAC_NAICS_CODES`/`FAC_SIC_CODES`, `NAICS_CODES`/`SIC_CODES`/`PGM_SYS_ACRNMS`).
- Decide whether/when to extract the ~90 remaining per-program ECHO fields.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16 (continued, part 3)

### Real bug found: duplicate registry_id rows, caught by an arithmetic check

Running `diagnose_echo_only.py` for real against the actual 1,368 "ECHO only" entities produced a genuine inconsistency: `found_in_national_frs` (2) + `not_found_in_national_frs` (926) = 928, not 1,368. A 440-row gap.

**This was caught by habit, not luck:** every real run this session has had its totals cross-checked against arithmetic identities (e.g. both + frs_only = FRS's total). This is the first time the check actually failed, and it was treated as a bug to chase, not a rounding quirk to wave off.

**Root cause, most likely:** duplicate `registry_id` rows within one or both source interim files. `pd.merge` does not deduplicate — a key appearing twice on one side of an outer join produces two output rows, not one. This matters beyond the ECHO-only bucket: if duplicate keys exist for entities that match BOTH sources, the "both" (310,349) and "frs_only" (216,643) counts from the master index build could also be inflated, not just the bucket where this was first noticed.

**Fixed the diagnostic itself, not just the immediate finding:** `check_against_national_frs` now reports `total_echo_only_rows`, `total_echo_only_unique_ids`, and `duplicate_row_gap` explicitly, so a future run surfaces this kind of gap automatically instead of requiring an external arithmetic check every time. Added `test_check_against_national_frs_matches_confirmed_real_gap`, which locks in the exact real numbers found today (1,368 / 928 / 440) as a permanent regression test.

**Built `src/linkage/check_duplicate_ids.py`** to find the actual root cause: checks FRS's interim table, ECHO's interim table, and the master index itself for duplicate keys, reports counts using a mathematical identity (`total_rows - unique_ids == extra_rows_from_duplicates`, tested directly) so the numbers are self-consistent by construction, and prints the actual duplicate rows for the first offending ID so it's clear whether the duplicate rows are identical or genuinely different records sharing an ID. 5 new tests, all passing (54 total). Full file-based dry run with a simulated duplicate-in-ECHO scenario confirmed the tool correctly isolates which source has the problem and shows it propagating unchanged into the master index. No leakage into the repo's real data/validation folders — checked before packaging.

**Not yet run against the real data.** This needs to happen before the master index's "both" and "frs_only" counts (310,349 / 216,643) can be fully trusted — right now there's direct evidence of duplication in the ECHO-only bucket and no evidence yet about whether it also affects the matched bucket.

### Pending
- **Priority:** run `check_duplicate_ids.py` for real and review `validation/duplicate_id_diagnostic_report.md`. If ECHO's interim file has duplicate registry_ids beyond the ECHO-only bucket, the master index needs to be rebuilt after deduplicating (or after understanding why the duplicates exist — e.g. genuinely different records that happen to share an ID, versus an artifact of how `fetch_echo.py` filtered/wrote the interim file).
- Re-run `diagnose_echo_only.py` after the duplicate question is resolved, since its "found under target state" bug-check (0, confirmed) is still valid, but the total counts feeding into it may need correcting.
- The larger "FRS only" group (216,643) has not been checked for the same duplicate-row issue — do so as part of the priority item above, not separately.
- Real match-rate finding to revisit for the entity-scoping question: FRS has ~527K rows, ECHO ~312K, so even a full FRS∩ECHO match would still leave far more entities than the ~5,000–13,000 target.
- The EXACT_ID-only scope of the master index build is a real limitation — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's and FRS's multi-value fields (`FAC_NAICS_CODES`/`FAC_SIC_CODES`, `NAICS_CODES`/`SIC_CODES`/`PGM_SYS_ACRNMS`).
- Decide whether/when to extract the ~90 remaining per-program ECHO fields.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16 (continued, part 2)

### Master facility index run for real — results consistent with prior sessions

`build_master_index.py` was run for real against the actual FRS (526,992 rows) and ECHO (311,717 rows) interim files. Results:

- Total: 528,360. Matched in both: 310,349. FRS only: 216,643. ECHO only: 1,368.
- Arithmetic verified: both + frs_only (310,349 + 216,643 = 526,992) exactly matches FRS's prior total; both + echo_only (310,349 + 1,368 = 311,717) exactly matches ECHO's prior total. This internal consistency is strong evidence the join executed correctly.
- State agreement: 310,349 checked, 0 disagreements — FRS and ECHO agree on state for every matched entity.
- Coordinate agreement: 252,848 matched rows had coordinates from both sources (the remaining ~57,500 matched rows are missing a coordinate on at least one side, consistent with FRS's known ~23% missing-coordinate rate). Median distance 0.0 km, max 28.884 km, all under 50 km. This is a strong positive signal — if the join were matching unrelated records, coordinates would not agree this closely.

### Investigated the 1,368 "ECHO only" entities rather than accepting the count at face value

Both sources were filtered to the four target states INDEPENDENTLY before joining. That ordering has a real subtlety: if a registry_id's state field disagrees between FRS and ECHO, it could be excluded from FRS's filtered subset while still passing ECHO's — showing up as "ECHO only" even though FRS actually has a record for it, just filed under a different state. This is a different, more benign situation than FRS genuinely having no record at all for an ID, which would be unusual since FRS is meant to be the comprehensive national identity registry.

Built `src/linkage/diagnose_echo_only.py` to tell these apart: checks the "ECHO only" registry_ids against FRS's FULL, UNFILTERED national extract (not just the state-filtered interim table). It explicitly checks for and flags the bug-signal case (an ID found under a TARGET state in the full extract, which should be impossible if the filter and join both worked correctly) as distinct from the benign case (found under a different state) and the genuine-gap case (not found at all). 6 new tests, including one that deliberately constructs the bug-signal scenario and confirms it gets flagged, not silently absorbed into "benign." Full file-based dry run performed with all three scenarios represented; confirmed no leakage into the repo's actual data/validation folders. 47 tests total, all passing.

**Not yet run against the real 1,368 ECHO-only IDs and the real FRS national extract** — that requires `data/raw/frs/extracted/NATIONAL_SINGLE.CSV`, which exists only on the project owner's machine.

### Pending
- Run `diagnose_echo_only.py` for real and review `validation/echo_only_diagnostic_report.md` — particularly whether `found_under_target_state` is 0 (expected) or nonzero (would mean a real bug to fix, not a data characteristic to document).
- The larger "FRS only" group (216,643) was not diagnosed the same way — it's much more plausibly explained by FRS covering many EPA programs ECHO doesn't track at all (drinking water systems, brownfields, etc.), a real and expected pattern, not primarily a filtering artifact. Revisit if evidence suggests otherwise.
- Real match-rate finding to revisit for the entity-scoping question: FRS has ~527K rows, ECHO ~312K, so even a full FRS∩ECHO match would still leave far more entities than the ~5,000–13,000 target. Cross-source matching alone (with just these two sources) will not fully resolve the scoping decision deferred on 2026-09-15.
- The EXACT_ID-only scope of the master index build is a real limitation — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's and FRS's multi-value fields (`FAC_NAICS_CODES`/`FAC_SIC_CODES`, `NAICS_CODES`/`SIC_CODES`/`PGM_SYS_ACRNMS`).
- Decide whether/when to extract the ~90 remaining per-program ECHO fields.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16 (continued)

### Step 3 started — master facility index (FRS + ECHO)

Built `src/linkage/build_master_index.py`, joining FRS and ECHO on `registry_id` via an outer join (`pd.merge(..., how="outer", indicator=True)`). This is the first entity-linkage step in the project and the first script under `src/linkage/`.

**Scope, stated plainly:** both FRS and ECHO share EPA's national REGISTRY_ID system, so every match here is EXACT_ID — no fuzzy, deterministic-name, or geo-assisted matching was needed or built. That matching hierarchy remains genuinely unimplemented and will be needed once the state modules (which almost certainly use their own state IDs, not REGISTRY_ID) get added. This build proves out the schema, provenance tracking, and QA framework using the two sources where linkage is easy — it does not solve the harder matching problem yet.

**Built with real QA checks, not just a join:**
- Match statistics (both/frs_only/echo_only counts).
- State-agreement cross-check between FRS's and ECHO's reported state for matched rows — a mismatch on a shared national ID would be a serious finding, so this is checked and reported rather than assumed.
- Coordinate-agreement check: computes the great-circle distance (haversine) between FRS's and ECHO's coordinates for matched rows with both present, banded into distance buckets. Added `common.haversine_distance_km`, tested against a known NYC-to-LA reference distance and a known 1-degree-latitude separation before trusting it for anything.
- `choose_best_coordinate`: when both sources have a coordinate for the same entity, prefers whichever has the lower (better) `coord_accuracy_value` — directly using the coordinate-quality metadata captured from the ECHO/FRS coordinate-accuracy finding earlier this session, rather than letting that finding go unused.
- The entity-scoping decision from 2026-09-15 ("keep everything for now") is honored here: this is an outer join, not an inner join — FRS-only and ECHO-only entities are both kept and explicitly tagged via `sources_present` / `source_count`, not silently dropped.

**Tested before trusting:** 12 new unit tests on synthetic data covering the join, both QA checks, coordinate-preference logic (including the "neither side has an accuracy value" and "neither side has a coordinate" edge cases), and the full build pipeline's source-tracking output. Then a full file-based dry run with realistic synthetic FRS/ECHO CSVs on disk (not just in-memory DataFrames), which caught and confirmed a real edge case the in-memory tests didn't cover: empty CSV cells correctly parse to NaN rather than literal empty strings, so a row with no coordinates correctly reports no coordinate source instead of falsely claiming FRS data. Dry-run artifacts were written to `/tmp`, not the repo's actual `data/`/`validation/` folders, and confirmed not to have leaked in before packaging. 41 tests total, all passing.

**Not yet run against the real 526,992 / 311,717 row files** — those exist only on the project owner's machine, not in this build environment. Next action: run it for real and review `validation/master_index_build_report.md`.

### Pending
- Run `build_master_index.py` for real against the actual FRS/ECHO interim files and review the build report — particularly the state-agreement and coordinate-agreement checks, which have not been exercised against real data yet.
- Real match-rate finding to revisit for the entity-scoping question: FRS has ~527K rows, ECHO ~312K, so even a full FRS∩ECHO match would still leave far more entities than the ~5,000–13,000 target. Cross-source matching alone (with just these two sources) will not fully resolve the scoping decision that was deferred on 2026-09-15 — worth surfacing when that decision gets revisited, not deciding unilaterally now.
- The actual EXACT_ID-only scope of this build is a real limitation, not a finished linkage system — deterministic/geo-assisted matching for state sources is still fully unbuilt.
- Confirm the delimiter used in ECHO's `FAC_NAICS_CODES` / `FAC_SIC_CODES` when a facility has more than one value.
- Decide whether/when to extract the ~90 remaining per-program (CAA/CWA/RCRA/SDWA) ECHO fields.
- Confirm the delimiter used in FRS's `NAICS_CODES`, `SIC_CODES`, and `PGM_SYS_ACRNMS`.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Cleaning, linkage, feature engineering (Steps 4–6) — deterministic/geo-assisted matching in particular.
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-16

### First real live data pull — EPA ECHO Exporter

`fetch_echo.py` was run for real against the live ECHO Exporter, not a dry run. Results:

- National file: 3,180,415 rows, 133 columns, extracted from a 428,327,103-byte zip (`sha256=fbaf4dd0de9531e837c44739894429198eec8f4ad43fe23a5fb430f36f3a3350`).
- Filtered to target states: 311,717 rows — TX 170,580 / PA 100,255 / NM 27,805 / ME 13,077.
- All 6 core identity/join fields matched on the first guess — no naming surprises like FRS's NAICS/SIC miss.
- Reported 0 of 311,717 rows missing coordinates.

### Critical finding: "0 missing coordinates" does not mean "0 imprecise coordinates"

A raw CSV sample showed `FAC_COLLECTION_METHOD` values of "State Centroid" (100,000m accuracy), "County Centroid" (30,000m), and "Zip Code Centroid" (10,000m) — none of the three sample rows had GPS-precision locations. ECHO backfills a centroid approximation rather than leaving a coordinate null when a precise location isn't known. Without capturing this, downstream spatial analysis could silently treat a 100km-radius approximation as an exact point.

**Action taken:** `fetch_echo.py` now also resolves `coord_collect_method`, `coord_reference_point`, and `coord_accuracy_value` (confirmed real fields: `FAC_COLLECTION_METHOD`, `FAC_REFERENCE_POINT`, `FAC_ACCURACY_METERS`), and these flow through into the standardized interim table. Documented at the field level in `docs/Analytical_Data_Model.md` and `docs/Data_Dictionary.md`, not just here, so it can't be missed by someone jumping straight to a data model doc.

### Compliance-summary fields confirmed and captured

With the real 133-column header in hand, expanded the connector from 6 core fields to 24 confirmed fields, covering the overall FAC_-level compliance rollups (inspection count, formal/informal action counts, total penalties, quarters with noncompliance, compliance status, SNC flag), the six program-applicability flags (AIR/NPDES/SDWIS/RCRA/TRI/GHG), NAICS/SIC codes, and the facility detail-report URL. All added as a separate `CONFIRMED_COMPLIANCE_SUMMARY_CANDIDATES` dict, clearly distinguished from the keyword-discovery pass used for the ~90 remaining per-program fields not yet individually extracted.

**Resolved the open architectural question from the previous session:** ECHO Exporter is confirmed to be a facility-level summary (one row per facility), not event-level data. Decision: use these aggregates directly as the MVP's compliance history component rather than pursuing ECHO's separate event-level Pipeline datasets. `docs/Analytical_Data_Model.md` now has a confirmed `echo_compliance_summary` table; the original `compliance_event` table is kept as a documented future upgrade path, not the MVP's actual source.

**A genuine blind spot found, not hidden:** the keyword-discovery pass's "violations" bucket does not catch `CAA_HPV_FLAG` — EPA named CAA's severe-violation indicator "HPV" (High Priority Violation) instead of following the `*_SNC_FLAG` pattern used by CWA/RCRA/SDWA. Only caught by manually reading the real header. Handled by adding `caa_hpv_flag` as an explicit confirmed field rather than relying on the discovery pass to find it, and documented as a known limitation of the keyword approach in code comments, the Data Dictionary, and a dedicated regression test (`test_keyword_discovery_misses_caa_hpv_flag_documenting_a_known_limitation`).

Added `test_resolve_echo_columns_matches_confirmed_real_schema` using the exact real header, locking in all 30 resolved fields (6 core + 3 coordinate-quality + ~21 compliance-summary) so a future edit can't silently break a confirmed mapping. 26 tests total, all passing. Full dry run performed with programmatically-built fake data (continuing the practice adopted after the earlier FRS test-fixture bug) confirming the coordinate-accuracy metadata and compliance fields flow through end to end. A duplicate/stale ECHO placeholder row was found and removed from `docs/Source_Register.md`'s source-volume log during this update — caught before shipping, not after.

### Pending
- Confirm the delimiter used in ECHO's `FAC_NAICS_CODES` / `FAC_SIC_CODES` when a facility has more than one value (same open question as FRS's equivalent fields).
- Decide whether/when to extract the ~90 remaining per-program (CAA/CWA/RCRA/SDWA) fields — deferred to Step 6 if program-specific granularity turns out to matter.
- FRS join and entity resolution (Step 3) — now genuinely possible for the first time, since two real sources share REGISTRY_ID.
- Entity-scoping rule for the master facility index (Step 3) — deferred from the FRS run, still not resolved.
- Confirm the delimiter used in FRS's `NAICS_CODES`, `SIC_CODES`, and `PGM_SYS_ACRNMS`.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Master facility/site index (Step 3).
- Cleaning, linkage, feature engineering (Steps 4–6).
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-15 (continued)

### Shared ingestion logic refactored
`resolve_frs_columns` and `filter_and_standardize` (originally written only for FRS) were generalized into `common.resolve_columns` and `common.filter_and_standardize_by_state`, so every connector after this one shares one tested implementation instead of copy-pasting the column-matching and state-filtering logic. `fetch_frs.py` now calls the shared functions through thin wrapper functions of the same name, so its existing tests kept working unchanged. All 18 tests (6 new, covering the generic functions directly) pass after the refactor — verified before moving on, not assumed.

### EPA ECHO Exporter connector built
- Verified the real direct download URL by fetching the live EPA page on 2026-09-15: `https://echo.epa.gov/files/echodownloads/echo_exporter.zip` (392 MB).
- Found the official column-definition spreadsheet (`echo_exporter_columns_7-16-2025_0.xlsx`) linked from the same page, but it's binary and this build environment can't reach echo.epa.gov to download and parse it — so, unlike FRS, the 130+ ECHO Exporter fields are NOT individually confirmed.
- Rather than guess at all 130+ fields the way FRS's 8 were guessed (and get 2 wrong), `fetch_echo.py` only guesses at 6 CORE fields needed for the FRS join and state filtering (registry_id, facility_name, state, latitude, longitude, county). For everything else, it runs a keyword-discovery pass (`common.discover_columns_by_keyword`) that finds real columns containing likely substrings (PENALT, VIOLATION, INSPECTION, FORMAL/INFORMAL, FLAG, COMPL/QTR) and writes them to `validation/echo_column_discovery.md` for human review — no exact-name guess is asserted as fact for those fields.
- 6 new tests added (`test_fetch_echo.py`), all passing, including a test that the discovery function correctly buckets a synthetic column list and correctly returns an empty bucket when nothing matches.
- Full dry run performed with a fake zip built programmatically (via `csv.writer`, not hand-typed strings — see the FRS test-fixture bug from earlier this session) to avoid repeating that mistake. Confirmed correct: CA excluded, TX/PA/NM/ME retained, missing-coordinate detection correct, discovery report readable and accurate. Dry-run artifacts removed before commit.
- **Not yet done:** actually running this against the real 392 MB file. That's the next action, same pattern as FRS — run it, send back the "Resolved core columns" line and the discovery report, and the exact compliance-field crosswalk gets confirmed from there rather than assumed.
- Open architectural question flagged in `docs/Analytical_Data_Model.md`: the ECHO Exporter is a facility-level summary (one row per facility), not event-level data. Whether the MVP's `compliance_event` table gets built from the Exporter's aggregates or from a separate event-level Pipeline dataset is not yet decided.

### Pending
- ~~Run `fetch_echo.py` for real, confirm core columns~~ — done 2026-09-16, see the entry above.
- ~~Decide whether compliance_event is built from ECHO Exporter aggregates or a Pipeline dataset~~ — resolved 2026-09-16: using Exporter aggregates for MVP, see the entry above.
- Entity-scoping rule for the master facility index (Step 3) — deferred from the FRS run, still not resolved.
- Confirm the delimiter used in FRS's `NAICS_CODES`, `SIC_CODES`, and `PGM_SYS_ACRNMS` when a facility has more than one value.
- Remaining source connectors: EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Master facility/site index (Step 3).
- Cleaning, linkage, feature engineering (Steps 4–6).
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased]

### Added
- Repository scaffold created per Development Project Scope v1.2, Section 4.
- MVP Requirements Specification v1.0 drafted (Step 1 output).
- Source Register drafted from Appendix A (pending access-date and checksum fill-in during ingestion).
- White Paper Draft v0.1 written (problem, method, data, and planned validation sections; findings pending).
- Analytical Data Model drafted (target standardized schema, Section 6 formalized).
- Data Dictionary drafted as a source-to-standard field crosswalk hypothesis, explicitly flagged for verification against live source schemas during Step 2.
- Feature and Indicator Register drafted (candidate features, reason codes, and cautions per component; weights and thresholds deferred to Steps 7–8 by design).

All six pre-ingestion planning artifacts (Requirements Spec, Source Register, Data Dictionary, Analytical Data Model, Feature/Indicator Register, repository structure) are now in place.

- Step 2 started: `src/ingest/common.py` (shared download/checksum/validation utilities) and `src/ingest/fetch_frs.py` (EPA FRS connector) written.
- Verified the EPA FRS direct download URL by fetching the live EPA pages on 2026-09-11 (see `docs/Source_Register.md` and `config/sources.yaml`): the "state single file" product at `https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip`.
- 14 unit tests written and passing (`tests/test_common.py`, `tests/test_fetch_frs.py`), covering checksum determinism, zip-slip protection, column detection/fallback, the required-column failure path, and state-filtering/coordinate-completeness logic.
- Full pipeline dry-run performed with a fake local zip standing in for the real download, to exercise `main()`'s orchestration end to end before handoff. Output confirmed correct: state filter, coordinate-completeness count, and source-volume log all behaved as designed. Dry-run artifacts were removed before commit — this repo does not contain real or fake FRS data.
- `requirements.txt` added.

**Known limitation, stated plainly:** the FRS column-name candidates in `fetch_frs.py` (`REGISTRY_ID`, `PRIMARY_NAME`, `LATITUDE83`, etc.) are best-current-knowledge guesses, not confirmed against an actual downloaded file — this build environment cannot reach epa.gov. The script is written to fail loudly with the real column list if none of the candidates match, rather than silently produce wrong output. Confirm `resolved_columns` in the log output against the real header row on first live run.

## [Unreleased] — 2026-09-14

### FRS schema confirmed against real data
The project owner provided a real sample row from the actual FRS national_single.csv file. Result: 6 of 8 original column guesses were exactly right (`REGISTRY_ID`, `PRIMARY_NAME`, `LATITUDE83`, `LONGITUDE83`, `STATE_CODE`, `COUNTY_NAME`). Two were wrong — the real file uses `NAICS_CODES` and `SIC_CODES` (plural), not the singular forms guessed. Both have been fixed in `fetch_frs.py`, `docs/Data_Dictionary.md`, and `docs/Analytical_Data_Model.md`.

The real file also has richer fields than originally planned for, now added to the connector and data model: `LOCATION_ADDRESS`, `CITY_NAME`, `POSTAL_CODE`, `HUC_CODE` (enables watershed-based spatial linkage), `PGM_SYS_ACRNMS` (program flags, kept raw pending delimiter confirmation), `SITE_TYPE_NAME`, and — most valuable — four coordinate-quality fields (`ACCURACY_VALUE`, `COLLECT_DESC`, `REF_POINT_DESC`, `HDATUM_DESC`) that feed directly into the geolocation-quality data-confidence feature.

Added a regression test, `test_resolve_frs_columns_matches_confirmed_real_schema`, using the exact real header row, so a future edit cannot silently break a mapping that's already confirmed against ground truth. 15 tests passing.

**Bug caught and corrected during this update, documented here rather than quietly fixed:** while dry-running the pipeline against the newly confirmed schema, a hand-typed synthetic test CSV produced a "2 of 4 rows missing coordinates" result. That number was wrong — it came from a manual comma-counting error in the test fixture (one row was short a field, shifting every subsequent column left by one position), not from a bug in the connector itself. Rebuilding the fixture programmatically with `csv.writer` instead of hand-typed strings gave the correct result: 1 of 4 (New Mexico's row is genuinely missing latitude in the test data; nothing else is). This is a reminder to construct test fixtures programmatically rather than by hand-counting delimiters, and it's recorded here instead of silently corrected so the fix is auditable.

### Pending
- Confirm the delimiter used in `NAICS_CODES`, `SIC_CODES`, and `PGM_SYS_ACRNMS` when a facility has more than one value, then implement array parsing for `naics_codes_raw` → structured NAICS list (same for SIC and programs).
- Remaining source connectors: EPA ECHO, EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Master facility/site index (Step 3).
- Cleaning, linkage, feature engineering (Steps 4–6).
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).

## [Unreleased] — 2026-09-15

### First real live data pull — EPA FRS

`fetch_frs.py` was run for real against the live EPA FRS single-file product, not a dry run or a sample. Results:

- National file: 5,329,863 rows, 39 columns, extracted from a 351,697,980-byte zip (`sha256=20296ac41aca625546d84c11c1d238686ce6d65860b36760c8f1871ad8cd1093`).
- Filtered to target states: 526,992 rows — TX 338,529 / PA 124,889 / NM 44,068 / ME 19,506. Arithmetic checked and confirmed to match the "wrote N rows" log line.
- Missing or unusable coordinates: 121,561 of 526,992 (about 23%). Plausible for a registry this broad; not evidence of a bug, but a real coverage gap to remember once spatial linkage (Step 5) starts.
- Column resolution matched the schema confirmed on 2026-09-14 exactly — no surprises there.
- `docs/Source_Register.md` updated with the real access date, file details, checksum, and source-volume counts, replacing the earlier placeholders.

### Entity-scoping decision required and made

At 526,992 records, FRS alone is far above the Requirements Spec's ~5,000–13,000 unique-analytical-entity target, because FRS registers every EPA-program facility nationally (drinking water systems, minor waste generators, administrative entries), most of which are unrelated to this project's oil/gas and industrial risk focus. This was surfaced to the project owner as a decision point rather than resolved silently. **Decision (2026-09-15): keep all 526,992 records for now; defer NAICS/SIC filtering or cross-source-match filtering until later.** This means Step 3 (master facility index) will need to either implement a scoping rule before finalizing the index, or explicitly reconfirm that the full ~527K set should carry forward as candidate entities — this has not been decided yet and should not be assumed.

### Pending
- Entity-scoping rule for the master facility index (Step 3) — deferred, not resolved. Revisit before Step 3 is considered complete.
- Confirm the delimiter used in `NAICS_CODES`, `SIC_CODES`, and `PGM_SYS_ACRNMS` when a facility has more than one value.
- Remaining source connectors: EPA ECHO, EPA TRI, PHMSA, USGS WQP, Texas RRC, TCEQ, PA DEP, NM OCD, Maine DEP (Step 2).
- Master facility/site index (Step 3).
- Cleaning, linkage, feature engineering (Steps 4–6).
- Scoring engine and validation (Steps 7–8).
- Power BI dashboard (Step 9).
- Reproducibility QA, external review, public release (Steps 11–13).
