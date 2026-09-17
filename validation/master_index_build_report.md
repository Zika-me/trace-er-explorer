# Master Facility Index Build Report (FRS + ECHO + TRI)

Generated automatically by `build_master_index.py`.

## FRS/ECHO match statistics (from the two-way join, before TRI is added)

- Total rows in FRS+ECHO outer join: 528360
- Matched in both FRS and ECHO (EXACT_ID, full data): 310349
- FRS only (no ECHO compliance data): 216643
- ECHO only (no FRS identity record — unusual, worth investigating if non-trivial): 1368

- Rows with NO registry_id at all, excluded from the final index (fixed 2026-09-16, see check_duplicate_ids.py): 441
  These rows have no usable identifier and cannot be indexed by one — excluded rather than mislabeled EXACT_ID or dropped without a count.

## Final three-way source breakdown (FRS + ECHO + TRI, after TRI is added)

- (none — should not happen): 791
- ECHO: 927
- FRS: 215839
- FRS,ECHO: 302065
- FRS,ECHO,TRI: 8322
- FRS,TRI: 15
- TRI: 24

**Scope note:** the state-agreement and coordinate-agreement checks below compare FRS against ECHO only — they were NOT extended to cross-check TRI in this build. TRI's identity and coordinate data are folded into the index (see coord_source, which can be 'tri'), but TRI has not been independently QA'd against the other two sources the way FRS and ECHO were QA'd against each other. This is a stated scope limitation, not an oversight to be assumed away.

## State agreement check (FRS vs ECHO, matched rows only)

- Checked: 310349
- Agree: 310349
- Disagree: 0

## Coordinate agreement check (FRS vs ECHO, matched rows with coordinates from both)

- checked: 252848
- min_km: 0.0
- median_km: 0.0
- max_km: 28.884
- under_1km: 252843
- under_5km: 252845
- under_10km: 252845
- under_50km: 252848
- over_50km: 0