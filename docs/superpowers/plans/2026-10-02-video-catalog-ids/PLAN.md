# PLAN — the video catalog's workflow id and re-recorded starts (#898)

**Assessment (2026-10-02).** Of the four items, 1 (`update_asset_status` dead) and 3
(`VideoRow` has no status) were already delivered by PR #912. Items 2 and 4 are open and
reproduced offline:

- Item 2: `record_started_video` / `record_completed_video` write `flow_workflow_id=None`.
  On ci-probe all three recent videos have `assets.flow_workflow_id = NULL`. The MCP task
  result (`mcp/tools.py`) returns `flow_workflow_id` from that column, so it is always
  `null` for a video, and `get_asset_by_any_id` cannot find a video by workflow id.
- Item 4: a second `record_started_video` for the same media id raises
  `DataIntegrityError: UNIQUE constraint failed: assets.profile_name, assets.flow_media_id`.

**Evidence that slot 0 is the workflow id.** The labs listing RPC is retired ("Flow RPCs
have been deprecated and disabled", `scripts/dev/spike_video_workflow_id.py`, 2026-10-02),
so it cannot be cross-checked live that way. The 2026-09-05 wire spike documents the record
as `[<workflow id>, <project id>, <media id>, "CAE", …]` — the same pairing as the labs
listing's `workflowId` + `workflowStepId: "CAE"` — and the driver polls the clip to a
terminal state by that id. Labs stores `operations[0].operation.name` as
`flow_operation_id`, which is not a workflow id; the labs reply's own workflow id is
`media[0].workflowId` (with a matching `workflows[0]` entry) in every committed capture
(`samples/captured/02`, `08`, `09`; 08 and 09 redact both as `<WORKFLOW_ID>`) — first read here as "unobserved", corrected by the
council on #942.

**Decisions.**
- Carry the id by name: `VideoStarted.workflow_id` / `VideoResult.workflow_id`, set by the
  migrated composer; the recorder persists it and never clobbers it with `None`.
- Item 4: a start for a media id the catalog already holds is a no-op (council on #942:
  reusing the row still rewrote it — status back to `pending`, metadata dropped — and left
  a second STARTED operation that is never resolved). **Not** a conflict-target change in
  `upsert_asset`: callers link operations by the id they pass, and the image paths rely on
  a repeated media id raising so `escalate_asset_collision` can name an attribution
  collision. Recorded at the SQL.
- The two #912-council follow-ups (`MediaDownloadError` retryable; HTTP-error signed URL
  7 → 6) each change a public contract and serve two callers with opposite needs (the
  generation download vs the `gflow_download_media` recovery). Filed as #941 for a
  deliberate decision, not folded in here.

## Tasks

- [x] 1. RED: recorder workflow id (start, completed keeps it, completed fills it), double start; migrated `VideoStarted.workflow_id`.
- [x] 2. GREEN.
- [x] 3. CHANGELOG.
- [x] 4a. `/gflow:check` green (4839 passed).
- [x] 4b. **Live (ci-probe, flow.google.com, 1 veo-lite clip, consented):** `gflow video t2v`
  exit 0, real MP4 (`ftypisom`). Submit reply `YhhmEf` named workflow `dbb0737e…`; all 10
  status replies matched that id (the driver drops any that do not); the catalog row now
  has `flow_workflow_id = dbb0737e…` (NULL on develop), and a lookup by that id finds the
  clip.
- [ ] 4c. PR, council, Sonar.
