# R11 explicit account-load statistics
Goal: expose useapi-shaped read-only account-load statistics through explicit jobs options while preserving the existing default job list.
Predict: Architect/Security GO with scoped metadata and consistent snapshot; Performance GO8; UX CAUTION8 mitigated by explicit accepted-to-observation/terminal timing policy, recorded-terminal-only 429 counters, no scheduler/quarantine claims. Root Devil GO8: observational addition only.
- [x] Red tests for summary, executing/history, fifteen-minute window, >100 jobs, disabled accounts, rate-limit separation, weighted average and invalid query combinations.
- [x] Implement SQL snapshot aggregates and bounded history, with public handles only.
- [x] Document exact scope and timing; default list and scheduler remain compatibility gaps.
- [x] Full gates and council:6349pass/89%, corrected tree GO.
- [ ] Publish, idledeploy, free live statistics reads.
