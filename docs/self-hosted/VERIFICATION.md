# Self-hosted fork verification

Measured on 2026-10-02 using one authenticated Google AI Pro profile served by `flow.google.com`.

| Surface | Evidence | Result |
|---|---|---|
| CLI native image2K | Existing1376×768 JPEG →2752×1536,3,334,707bytes | Passed |
| Shared-client/MCP native image2K | Three real-profile BDD cases, including Pro4K refusal |3passed |
| HTTP native image2K | Durable job completed, inline JPEG2752×1536,3,334,707bytes | Passed |
| Tee client text-to-image | Existing tee client used the local endpoint and received458,359bytes,1024×1024 | Passed |
| Raw upload and reference generation | Existing tee request format produced blue mug variation from red source,271,282bytes | Passed |
| HTTP complete image workflow | Real HTTP BDD: generate →upload →reference generation →native2K; asserts exactly doubled dimensions |1passed in133.91s |
| Actual Streamable HTTP MCP upscale | Live tool call through the running service returned native 2K bytes after direct detail navigation fixed gallery virtualisation | Passed |
| Authentication | HTTP401 without bearer on REST and MCP; authenticated MCP lists18tools including both upscale tools | Passed |
| Broad offline regression | 4,911 passed, 30 skipped; 91.26% coverage; one README sponsor-placement failure | Placement corrected and targeted test rerun |

The one real-profile native-upscale BDD run had a profile contention/setup failure while another test was using the account. It was repeated without concurrent browser work and all three cases passed. Profile leases rejected contention safely; no browser was killed.

## Explicit limits

Only one of the user's three Pro accounts is authenticated and configured for execution. Successful4K cannot be tested without an Ultra account; Pro4K refusal is verified. The three plans are independent allowances, not an Ultra entitlement.

No video generation credits were spent during this implementation. Native video1080p/original720p/GIF export adapters have offline coverage, but no existing Google-generated video was available for live validation. Other unsupported controls and endpoints are listed in [the compatibility inventory](PARITY.md). API presence is not proof of full useapi parity.

Tee's production provider was not switched. Its existing client was exercised against the new endpoint by overriding its base URL in an isolated verification process. The local service and fork can be used independently of that production configuration.
