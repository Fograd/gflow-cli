# R07 scenarios

Relevant dimensions: D1 exact account/project binding; D2 no mint before refusal and no replay; D6 private checkpoints; D7 typed uncertainty; D9 exact output/request correlation; D11 source dimensions and targets; D12 no secret URLs; D13 interface forwarding. D3 selectors, D4 batch, D5 concurrency, D8 paths and D10 engine behavior reuse existing boundaries without redesign.

| Scenario | Severity | Expected | Test |
|---|---|---|---|
| Owned video with explicit absent dimensions | High | Strict URL/ownership parser, bounded measurement, cleanup; no guessing | Unit and real source preflight |
| Foreign, ambiguous, malformed or partial dimensions | Critical | Refuse before measurement/mint | Unit |
| 640x360 to720p source preparation | High | Exact16:9, enum1/task21 selected before mint | Unit and synthetic opt-in BDD if originals lack source |
| Unavailable target/model/aspect | High | Fresh capability refusal before token | Unit and live catalogs |
| Accepted output wrong identity/aspect/resolution | Critical | Preserve exact handles, typed unknown, zero replay | Unit |
| Image4K enum2 and incorrect project context | Critical | Forward enum2; exact context slot5; wrong binding refuses | Unit |
| Image bytes valid wide2K vs corrupt header/truncated file | High | Decode actual dimensions; preserve2752x1536; no guessed4K geometry | Unit |
| CLI/MCP/REST worker controls | High | Shared targets/default1080p; supplied tokens remain exclusive/single use | Existing plus focused forwarding tests |

Paid rendered acceptance has a named external blocker: exhausted video allowances and absent authorization/entitled4K evidence. It remains R12.
