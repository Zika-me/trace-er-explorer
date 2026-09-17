# Master Facility Index Build Report (FRS + ECHO)

Generated automatically by `build_master_index.py`.

## Match statistics

- Total rows in outer join: 528360
- Matched in both FRS and ECHO (EXACT_ID, full data): 310349
- FRS only (no ECHO compliance data): 216643
- ECHO only (no FRS identity record — unusual, worth investigating if non-trivial): 1368

- Rows with NO registry_id at all, excluded from the final index (fixed 2026-09-16, see check_duplicate_ids.py): 441
  These rows have no usable identifier and cannot be indexed by one — excluded rather than mislabeled EXACT_ID or dropped without a count.

## State agreement check (matched rows only)

- Checked: 310349
- Agree: 310349
- Disagree: 0

## Coordinate agreement check (matched rows with coordinates from both sources)

- checked: 252848
- min_km: 0.0
- median_km: 0.0
- max_km: 28.884
- under_1km: 252843
- under_5km: 252845
- under_10km: 252845
- under_50km: 252848
- over_50km: 0