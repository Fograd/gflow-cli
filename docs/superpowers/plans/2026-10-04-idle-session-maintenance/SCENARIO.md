# Scenario: optional idle session maintenance

Active dimensions: D1 identity/session scope; D2 quiet backoff; D4 restart dedup; D5 serial queue and global bound; D6 durable atomic metadata; D7 cancellation; D10 existing bounded headed client; D11 finite interval validation; D12 safe observed metadata. D3/D9 introduce no selector/wire changes. D8 uses existing paths. D13 adds daemon configuration only, no CLI/MCP command or payload keys; MCP profile contention keeps the existing ProfileLease UNKNOWN/backoff behavior.

| Scenario | Severity | Expected result | Test |
|---|---|---|---|
| Disabled interval or account, including reserved pro1 | Critical | No native read | Offline |
| Due idle profile, concurrent ticks or restart | Critical | One existing health job, daemon-wide maximum one | Offline BDD/SQLite |
| Accepted generation/manual health | Critical | No maintenance admission or cancellation of that work | Offline |
| Registration/project changes or stale queued read | Critical | New timing scope, old read canceled before subprocess | Offline |
| Interval disabled before startup | Critical | Only created maintenance canceled; manual/active jobs preserved | Offline lifespan |
| UNKNOWN/login required | High | 2x/4x backoff, no login/replay | Offline |
| Daemon cancellation | High | Scheduler exits, running health recovered UNKNOWN by existing recovery | Offline |
| Safe status projection | High | No principal/token/cookies or expiry/renewal claims | Offline HTTP |

Known issue: ../../../../KNOWN_ISSUES.md documents /about requiring human verification despite stored cookies. This feature does not fix that issue. The existing live health acceptance covers the unchanged native read; an actual scheduled pro3 smoke is blocked until parent coordination, and idle/renewal-boundary survival stays unverified.
