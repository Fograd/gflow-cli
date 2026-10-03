# Scenario: native confirmed deletion retry
Active dimensions D1 account replacement; D4 retry; D5 one-page lease; D6 receipt persistence; D7 exact errors; D8 paths; D9 no credits; D11 1..100 alias IDs; D12 no identity leakage; D13 CLI/MCP/REST parity. D2 no token mint, D3 no selector changes, D10 no browser install change.
| Case | Severity | Expected |
|---|---|---|
| Profile reauthenticated as another account | Critical | Receipt scope mismatch refuses before mutation |
| Foreign/unknown missing UUID mixed with owned present | Critical | Entire batch refuses before mutation |
| Exact as29s status5 plus scoped confirmed receipt | High | Already-deleted, zero second mutation for it |
| HTTP404/null/forbidden/malformed/duplicate frame | Critical | Never interpreted as deleted |
| One present + one confirmed gone | High | One mutation containing present ID only |
| Ack followed by receipt write failure | High | Preserve accepted result; receiptPersisted false |
| Read timeout before mutation | High | Refuse, no writes |
| Delete timeout after dispatch | Critical | Existing typed unknown handles, no receipt/retry |
Free browser BDD will upload only synthetic owned fixtures, delete them in batch and repeat, preserving originals.
