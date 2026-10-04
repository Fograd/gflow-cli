# Native image character pool plan

Goal: enforce the independently observed character count limit alongside actual flattened image weights.
Architecture: extend native_image_models metadata and native_image_references preflight; reuse existing reads/page lease. No new public input fields. Root approved these files and dedicated tests. Lite hard3 change remains gated separately.
Predict: confined source-backed preflight correction GO; live retention CAUTION. Full integration review belongs to root.

- [x] Read source and current metadata/parser evidence; inspect existing video sibling.
- [x] Write red parser and SDK boundary/order tests.
- [x] Verify red failures (12 expected failures, two existing boundary successes).
- [x] Parse field22/index1 character capacity as integer0..100 and bound effective count to documented seven character slots.
- [x] Validate requested model character cap before any billed side effect; preserve weights/order.
- [x] Run focused tests (67 passed), affected regression (138 passed), lint, format and type check.
- [ ] Root: fresh read-only metadata proof, live BDD acceptance, shared docs/mirror changes and full gates.


## Authorized Lite continuation

- [x] Root fresh safe HTrJv/nzlxg evidence: three available image usages advertise image10/character10 at tier2; cached source explicit image decoder matches.
- [x] Add red DTO/CLI/mentions/native current-capacity tests (16 intended failures across two runs).
- [x] Raise shared admissible Lite ceiling to10; current native metadata may lower it. Keep Imagen4 ceiling3 and metadata proof flags false.
- [x] Verify306 affected tests using isolated temporary directory; ruff/format/pyright clean.
- [ ] Root shared docs, updated live budget BDD, no-submit retained-vector proof and full gates.
