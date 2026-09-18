# Master Index + TRI Release Features Join Report

Generated automatically by `join_tri_features_to_master_index.py`.

- tri_release_features.csv key (epa_registry_id) duplicate check: 0 (should always be 0 — this table is built by groupby(), which cannot produce duplicate keys; a nonzero value here means something upstream is broken)

- Total master index rows: 527983
- Rows with real TRI release data attached: 3919
- Rows with NO TRI release data (left null, never zero-filled): 524064

A row with no TRI release data means this entity has never reported to TRI in the 2019-2024 window covered so far. Most entities in the master index are not TRI-reporting facilities at all (TRI only covers specific industrial chemical users/handlers), so a low match rate here is expected, not an error.

Note: 34 known registry_ids have multiple rows each in the master index (the confirmed multi-tenant-site pattern). Every tenant row at a shared site will show the SAME site-level release total after this join, since TRI reports releases per site, not per tenant company — a correct reflection of the source data, not a bug.