# Native image character capacity scenarios

Source: cached Google project bundle Q6a3654330, $6a3655660, OZa3555579 and c_a3558449. Image mode has separate character and weighted image pools.

| Dimension | Scenario | Severity | Expected | Layer |
|---|---|---|---|---|
| D11 | Two characters fit image pool but exceed character pool | High | Refuse before mint/checkpoint/submit | SDK integration |
| D9 | Missing, bool, negative or malformed character capacity | High | ConfigurationError | Parser unit |
| D11 | Character capacity zero with plain owned images | High | Accept images; refuse characters | SDK integration |
| D11 | Two two-image characters plus two images exactly fill six slots | High | Preserve image/entity/prompt order and fresh weights | SDK integration |
| D13 | CLI/MCP/HTTP construct native request through SDK validator | High | Same capacity refusal before transport | Existing shared SDK call path |

D1/D2/D5: no auth, token or additional page calls; existing one lease and two metadata reads remain. D3/D10: no selectors or launch changes. D4/D6/D8/D12: no persistence, batch, paths or logs changed. D7: existing ConfigurationError retained.

Live source/model agreement remains root-owned; no rendered-retention claim. Existing native budget read-only BDD needs fresh character cap observations at root integration.


## Lite continuation

Fresh root-owned tier2 image model capture (2026-10-04) reports field22/index2=10 for Lite; source image decoder agrees. High scenarios: DTO/CLI/mentions preserve4/10 orderedrefs and reject11; lower fresh cap3 rejects4 before mint/checkpoint/upload/transport; eight localrefs+two-imagecharacter exactly10 accepts while nine+two refuses. These are offline acceptance/preflight tests, not retained/rendered proof. Root-owned no-submit retained-vector BDD remains separate.
