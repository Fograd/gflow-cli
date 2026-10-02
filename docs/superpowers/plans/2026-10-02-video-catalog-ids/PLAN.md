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
terminal state by that id. Labs stores `operations[0].operation.name` (equal to the media
name in every capture) as `flow_operation_id`: not a workflow id, so labs records none.

**Decisions.**
- Carry the id by name: `VideoStarted.workflow_id` / `VideoResult.workflow_id`, set by the
  migrated composer; the recorder persists it and never clobbers it with `None`.
- Item 4: reuse a known media id's row in `record_started_video`, the pattern
  `record_completed_video` already uses. **Not** a conflict-target change in
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
