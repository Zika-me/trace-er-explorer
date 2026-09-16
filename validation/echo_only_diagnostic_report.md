# ECHO-Only Entities Diagnostic Report

Checks whether 'ECHO only' registry_ids from the master index truly
have no FRS record anywhere, or exist in FRS under a different state
than ECHO reports — which would explain the exclusion as a filtering
artifact rather than a genuine data gap.

- Total ECHO-only entities: 1368
- Found in FRS's full national extract: 2
- NOT found in FRS's full national extract at all: 926
- Found under a TARGET state (TX/PA/NM/ME) — should be 0; nonzero means a bug in the state filter or join, not a data characteristic: 0
- Found under a different (non-target) state: 2

Sample of the non-target states found: {'LA': 2}

Sample of registry_ids not found in FRS at all: ['110072254082', '110072256439', '110072254496', '110072255757', '110072257157', '110072256414', '110072253394', '110072258286', '110072258106', '110072256095']