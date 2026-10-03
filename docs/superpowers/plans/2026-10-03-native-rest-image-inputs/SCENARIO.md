# Scenario: Ordered mixed image reference inputs

Active dimensions: D1/D3/D5/D6/D7/D9/D11/D12/D13 ownership, lease, codec and mirror
boundaries. D2/D4 retain existing no replay/unknown outcome behavior.
D8 preserves contained private paths. D10 live headed proof remains explicit.

| Scenario | Severity | Expected behavior | Test surface |
|---|---|---|---|
| Native/local/native numeric slots with repeated marker | High | One ordered immutable plan; deduplicated bindings | DTO/codec/composer |
| Uploaded ID differs from public local alias | Critical | Only acknowledged ID emitted | Guarded wire |
| Missing/extra/reordered/overlapping alias vector | Critical | Refuse before browser or upload | DTO/codec |
| Native refs without configured email | High | Explicit request error; no account scan | REST |
| Managed/native selected account mismatch | Critical | Refuse before enqueue | REST |
| Foreign/archived/unsearchable native ref | Critical | Refuse before any local upload | SDK/composer |
| First native Auto missing dimensions | High | Refuse; never use later local | Worker |
| First managed Auto then native | High | Decode first contained PNG/JPEG | REST/worker |
| Queued aliases/path record tampering | Critical | Validate registry and plan again | Runtime |
| Partial upload/attachment cancellation | Critical | Preserve handles; no replay | Worker/composer |
| Direct/queued MCP and CLI canonical mixed inputs | High | Same ordered mapping and errors | Mirrors |
| Actual owned native adapter discovery/attachment | High | Tagged no-submit probe only | Live BDD |

Must cover all Critical/High cases before enabling the mixed generation path.
Reference URL/download work is independent and not discharged by these tests.
