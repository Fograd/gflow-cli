# Cookie refresh scope scenarios
Critical: partial alias migration across databases; mitigate with a single committed lineage
rather than mutating alias stores. Critical: deletion then unrelated registration; tombstone
all historical scopes. High: last15minute jobs disappear after physical profile replacement;
resolve audit origins through verified account lineage. High: stale expected account row or
busy job; existing transaction rechecks refuse. High: chain refresh and profile reuse; collapse
accepted lineage and refuse retired physical names. Existing CookieTable/owned staging/identity
and project probes remain unchanged. CLI/MCP cookie-import contracts are unchanged; HTTP accepted
refresh is the affected surface. Root owns authenticated actual cookie acceptance.
