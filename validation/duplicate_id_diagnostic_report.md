# Duplicate ID Diagnostic Report

Triggered by an arithmetic gap in the ECHO-only diagnostic (1,368 rows
vs 928 unique IDs found+not_found). Checks whether duplicate keys exist
in FRS, ECHO, or the master index — and, if in FRS or ECHO, whether they
could also be inflating the 'both' and 'frs_only' match counts, not just
the ECHO-only bucket where the gap was first noticed.

## FRS interim table (key: registry_id)

- total_rows: 526992
- null_id_count: 0
- unique_non_null_ids: 526992
- duplicate_id_count: 0
- extra_rows_from_duplicates: 0
- sample_duplicated_ids: {}

## ECHO interim table (key: registry_id)

- total_rows: 311717
- null_id_count: 441
- unique_non_null_ids: 311276
- duplicate_id_count: 0
- extra_rows_from_duplicates: 0
- sample_duplicated_ids: {}
  **441 rows have a BLANK/missing ID — these have no usable identifier at all, which is different from and likely more important than duplication.**

## Master facility index (key: master_id)

- total_rows: 528360
- null_id_count: 441
- unique_non_null_ids: 527919
- duplicate_id_count: 0
- extra_rows_from_duplicates: 0
- sample_duplicated_ids: {}
  **441 rows have a BLANK/missing ID — these have no usable identifier at all, which is different from and likely more important than duplication.**
