# ECHO-Only Entities Diagnostic Report

Checks whether 'ECHO only' registry_ids from the master index truly
have no FRS record anywhere, or exist in FRS under a different state
than ECHO reports — which would explain the exclusion as a filtering
artifact rather than a genuine data gap.

- Total ECHO-only rows in master index: 927
- Unique registry_ids among those rows: 927
- Duplicate-row gap (rows minus unique IDs): 0

- Found in FRS's full national extract (unique IDs): 2
- NOT found in FRS's full national extract at all: 925
- Found under a TARGET state (TX/PA/NM/ME) — should be 0; nonzero means a bug in the state filter or join, not a data characteristic: 0
- Found under a different (non-target) state: 2

Sample of the non-target states found: {'LA': 2}

Sample of registry_ids not found in FRS at all: ['110072255470', '110072256847', '110072256748', '110072254420', '110072255411', '110072255652', '110072256176', '110072257699', '110072253751', '110072257858']