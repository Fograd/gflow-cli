# Scenario: general video canonical controls
Active D7/D9/D11/D13: API validation/worker wire roundtrip/strict controls/source aliases. No new CLI/MCP fields: REST normalizes into existing canonical controls.
| Case | Severity | Expected |
|---|---|---|
| landscape/portrait general T2V/I2V/I2V-FL/R2V | High | Canonical16:9/9:16 before enqueue |
| Explicit Veo720 | High | Existing wire default via omission, no nonexistent resolution radio |
| Omni360/720 | High | Existing explicit resolution control retained |
| Other aspects/resolutions or malformed types | High |422 before enqueue |
| Numeric seed | High | Existing unsupported501 before enqueue |
| Worker CLI/privateDTO | High | Canonical aspect, resolutionNone/default; no new wire field |
Root owns no-generation native capture and representative generation acceptance; subagent no live calls.
