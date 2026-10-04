# Scenario: Resumable native inventory synchronization

Active dimensions: D1 account/profile identity; D4 interruption; D5 concurrent resumes;
D6 atomic durable storage; D7 typed errors; D8 private paths; D9 repeated cursors;
D11 bounds; D13 CLI/direct MCP parity. D2/D3/D10 introduce no new browser behavior;
existing proven SDK methods retain responsibility. D12 adds no log event.

| Scenario | Severity | Expected |
|---|---|---|
| Process fails after page discovery | High | Pending catalogs survive; discovery page is not skipped |
| Catalog read fails | High | Last committed checkpoint resumes the same project |
| History reveals an undiscovered project | High | Its catalog is scheduled before history continues |
| Empty catalogs/history or later omissions | Critical | Retain previous rows; complete remains null |
| Two writers resume one scope | High | Atomic compare-and-swap rejects stale checkpoint |
| Project cursor repeats after restart of process | High | Refuse cycle without advancing checkpoint |
| Other profile/account | Critical | Separate checkpoint and observations |
| Secret or URL fields in SDK result | Critical | Store only explicit metadata fields |
| Step/time cap | High | Return resumable progress after the last atomic step |
| CLI and MCP controls | High | Same bounds/restart, private configured home and account selection |

Root owns authenticated read-only BDD. Offline tests prove orchestration, not live transport acceptance.
