# Scenario: explicit account-load statistics
Relevant dimensions: data lifecycle/concurrency, errors, privacy, performance and API scope. Browser, CAPTCHA, generation, file/output and CLI/MCP paths are unchanged.
| Scenario | Expected behavior | Test |
|---|---|---|
| Two account projects/profiles | Separate public counters, combined weighted timing | Integration |
| More than100 recent jobs | No legacy list truncation | Integration |
| Old terminal vs currently running | Fifteen-minute terminal window; running regardless age | Integration |
| Terminal429 | rateLimited increments, failed excludes429, exact score | Integration |
| Disabled/unverified account | No account or job metadata exposed | Integration |
| History>10/type | Newest ten per type, safe IDs/status/timing only | Integration |
| Bad/repeated/mixed options | Refuse before reading, no job creation | Integration |
Timing is acceptance-to-observation/terminal; queued waiting is included, never claim true execution duration. Queued jobs are not executing. Admission failures have no durable jobs and are not counted. Native image upscaling and video promotion are included; auth maintenance/deletion/export/local composition are excluded. No browser E2E needed for this metadata-only surface; actual deployed authenticated read required.
