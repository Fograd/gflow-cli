# Generic video batches

Generic text-to-video, start/end images and image ingredients support count2–4
through one current Flow UI submission. Count1 preserves the existing interface.
This replaces the older HTTP sequence of separate count-one submissions.

## SDK and outputs

`await client.generate_videos_batch(req=request, project_id=project)` accepts
`GenerateVideoRequest(count=2..4)` and returns `VideoBatchResult` with a
`videos` tuple and `project_id`. Each video retains its own verified media,
workflow, status and optional downloaded path. Singular `generate_video`
refuses count above1 before transport; use the batch interface.

CLI `video t2v/i2v/r2v --count 2..4` retains all files. JSON returns
`videos`, `returned_count` and `project_id`. Registered
`gflow_generate_video` retains all `flow_media_ids`,
`flow_workflow_ids` and files in its completed result; asynchronous mode returns
the durable task ID. REST `POST /v1/google-flow/videos` produces one job with
all validated outputs, `requestedCount` and `completedCount`.

## Correlation and recovery

Every canonical requested media UUID must be unique and bound to the selected
project and exact native RPC. The reply must contain exactly the requested
identities with media/workflow roles from the current field4 codec. Actual
positively acknowledged pairs checkpoint before a later malformed/partial reply
can fail validation. Only those actual identities survive recovery.

Each output is polled and downloaded independently. A partial, mixed, malformed,
cancelled or unknown batch retains known handles and completed artifacts without
automatic submission replay. The private worker output and durable job recovery
validate the whole exact project/output scope and never synthesize missing IDs.

## CAPTCHA

Count1–4 share the current single-request CAPTCHA context. Every assigned UUID
is freshly checked before one provider token is minted for that RPC; there are
no invented per-output tokens. Supplied tokens remain single-use and confidential.
Explicit provider retry uses a new full identity vector/context and is permitted
only after an exact singleton WAF refusal with zero acknowledged handles.
See [generic CAPTCHA controls](GENERIC_VIDEO_CAPTCHA.md).

## Evidence and limits

The real pro1 count-four preflight selected Veo3.1Lite, captured one YhhmEf
request with four distinct assigned identities and aborted it before Google
forwarding. This used zero generation requests/video credits. Focused codec,
SDK/CLI/MCP/worker/HTTP and partial recovery tests cover result handling.
Accepted plural rendering remains [final E2E](FINAL_E2E.md); countN requires
N authorized video outputs. Numeric native seeds remain unsupported.
