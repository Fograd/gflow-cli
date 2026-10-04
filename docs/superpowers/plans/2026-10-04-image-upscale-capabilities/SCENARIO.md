# Scenario: image upscale capability discovery

## Coverage map
D1 auth: fresh selected-project image ownership required. D2 billing: no mint/target click/RPC. D3 selectors: unique visible menu and resolution tokens, absent/duplicate/hidden unknown. D5 page pool: bounded acquisition and exactly-once return on cancellation. D7 errors: invalid/foreign/non-image inputs refuse; selected-engine timeout normalized. D9 transport: REST worker envelope validated. D10 browser: headed authenticated reads remain required live, intercepted Patchright browser covers menu behavior. D11 IDs: strictUUID before navigation. D12 output: no URLs/user text/auth. D13 parity: SDK/CLI/directMCP/REST; no queued twin.
D4/D6/D8 have no new batches, database or paths.

|Scenario|Severity|Expected|Layer|
|---|---|---|---|
|Enabled2K, disabled4K|High|Independent available/disabled observations|Unit + real browser BDD|
|Missing/hidden/duplicate item|High|unknown, nullable availability|Unit + real browser BDD|
|Wrong detail/menu or ambiguous download|High|unknown; no target click|Unit + real browser BDD|
|Wrong kind/foreign UUID|Critical|error before detail navigation|Unit|
|Patchright timeout|High|unknown rather than false or raw error|Unit + real browser BDD|
|Lease/cancellation|High|page returned once|Unit|
|Invalid/secret/malformed worker result|High|REST refuses and strips no invented fields|Unit|
|Every surface|High|same observations, no generation job|Adapter tests|

No absent observation implies lack of entitlement or permission to delete. Known unusual-activity warnings remain applicable; no successful rendered upscale is claimed.
