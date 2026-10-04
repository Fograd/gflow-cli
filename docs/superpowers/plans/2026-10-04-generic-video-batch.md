# Generic native video batch delivery
## Contract and scope
Current Google t7a builds one request row per output for YhhmEf/eb1hJf/nprQif/MZZa6b. Each metadata field5 carries an invocation-owned UUID seed. Current _.gy.dg returns repeated _.Lx at response field4; _.Lx getters bind media/project/workflow at fields1/2/3. Use a new strict RPC-specific decoder rather than altering legacy first-record identity assumptions.
Count2..4 only; default count1 old API preserved. Explicit provider/supplied-token policy remains count1.
## Scenarios before implementation
- Source request count/project/rpc/UUID seeds positively match exact expectation, including canonical uniqueness; unrelated route passes, malformed known submit aborts before dispatch.
- Exact dispatched Request plus one matching RPC reply, field4 unique typed media/project/workflow rows, assigned seed media set and exact count; reordered replies return requested order.
- Partial/mixed/masked/duplicate/wrongproject replies retain every actual correct-project handle, settle unknown, never resubmit.
- Callback each source-proven handle before polling. All outputs poll strict owned GetMedia triples/type on same leased page and bounded deadline; download each privately. Failed sibling/timeout/cancellation preserves handles.
- CLI countN JSON/text alloutputs, indexed output relocation; SDK typed VideoBatchResult via additive generate_videos_batch.
- Durable MCP task completes checkpoint allN, records each clip, resolves all returned files. REST runtime creates public media allN from batch CLI DTO. No protected URLs in durable/public payload.
## Target files
New native UI video batch pure codec/observer/service modules and focused tests; video.py typed batch result, client.py additive method, migrated_composer.py shared setup only, cli_video.py shared report, json_output.py batch serializer, worker/daemon.py generic batch selection/checkpoint and mcp/tools.py generic result resolution. Root owns HTTP/server docs; runtime result integration coordinated.
## Proof limits
No live/paid/provider calls by implementer; primary cached source and root abort-only captures. Existing singular decoder identity drift remains documented pending separate source-specific correction/accepted proof. No guessed numeric seed/tier or synthetic accepted media IDs.
