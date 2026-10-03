# Unsafe-caption picker implementation plan
Goal: finish R01 caption-format coverage with bounded safe queries and exact owned token selection.
Predict: Architect GO8, Security GO8, Performance CAUTION8, UX GO8; root Devil CAUTION8: bare picker may omit target, refuse rather than substitute.
User standing authorization covers implementation/publication/deployment.
Architecture: shared migrated composer only; original captions/UUIDs/slots/ownership and submit checks unchanged. All SDK/CLI/direct+queued MCP/REST share it.
Scenarios D1 auth existinglease; D2 generation guarded; D3 unique exacttoken; D4 no writes/replay; D5 one page; D6 no Store/history synthesis; D7 Unicode controls/formats/surrogates excluded; D8 empty/long/newline/@; D9 locale unchanged; D10 clear probe draft; D11 IDs preserved; D12 red tests+tagged BDD; D13 shared mirrors/docs.
- [x] Prediction and scenario coverage.
- [x] Red safe-query/duplicate-token tests.
- [x] Deterministic contiguous excerpt<=120 or bare picker; unique token required.
- [x] Fresh-owned zero-generation attachment BDD.
- [ ] Docs and evidence, required gate/council/publication/deployment.
Only one authorized image-generation slot remains; this attachment batch does not satisfy all generation acceptance or shrink R01/R02/full roadmap.

Live canonical unsafe-caption attachment passed 37.41s after caller-path correction; two synthetic fixtures archived, no generation. Missing/nontext captions are distinct: None becomes bare query, nontext refuses. Safe captions preserve the previous local name path; unsafe uploaded references discover a fresh exact owned grid token.
