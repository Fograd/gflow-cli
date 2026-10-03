# Native Flow credit inspection

`gflow credits user` and the shared MCP credit tool now support the source-derived
native GetCredits RPC. For these shared service adapters set
`GFLOW_CLI_FLOW_HOST=flow.google.com` to bypass the old labs HTTP fast path.
An already-open SDK client also selects native inspection when its observed
bootstrap host is migrated. Explicit labs mode keeps its existing implementation.

The deployed `nzlxg` response supplies field1 total credits, field2 paygate enum
and field4 service-tier enum. These map to the existing `CreditsInfo.credits`,
`user_paygate_tier` and `service_tier` fields. Zero is a real balance; a missing,
negative or noninteger balance refuses. Unknown enums return null rather than an
invented plan name. Subscription-credit and SKU fields remain null because their
native semantics have not been established; components are not guessed from the
three Pro accounts. Service-tier labels are Google's enum labels, not an inferred
Pro/Ultra billing plan.

Native inspection uses the existing client page and profile lease, bounded fixed
same-origin RPC, without generation, token solving or an extra global browser pool.
Pure parser/SDK routing tests pass. Native live balance/CLI/MCP acceptance is
pending final read-only E2E; this code is not a new session-lifetime guarantee.
