# Recovering image outputs after a download failure

A download failure does not mean Google failed to generate the image. Inspect the
preserved handles and files before submitting another generation request.

The normal CLI, seeded/token REST worker, queued MCP worker and batch download paths
write a small private journal after Google returns image handles, then update it after
each completed local download. This does not issue another generation or automatically
retry a failed generation.

CLI JSON failures include `imageRecovery.images`: safe media/workflow handles, observed
seed/dimensions where available, and `local_path` only for a completed, contained file.
Signed URLs, prompts, CAPTCHA tokens and provider credentials are excluded. Image
download failures report `retryable: false` even when the underlying transfer error was
otherwise retryable.

REST jobs preserve `knownMediaGenerationIds`, `generatedCount`, `completedCount`, and
completed `media` entries. When recovered from the journal, an entry includes a protected
`downloadPath`; the caller must use its bearer token. Files larger than the 20 MiB inline
limit can still be preserved for download, up to the 250 MiB recovery bound. Inspect
failed/interrupted job results rather than assuming their media list is empty.

The REST daemon imports the expected job journal on command failure, timeout and startup
recovery. Running jobs interrupted by a crash become `interrupted` and are never replayed.
Queued MCP jobs retain native handles in their checkpoint before downloading and preserve
recovery data after each output; cancellation/restart remains `indeterminate` after a
submission. Recovery can read a newer fsynced journal if a crash happened just before its
next database checkpoint. It never resets the task to pending.

Batch rows preserve their generated images separately from downloaded paths. A later
transfer failure retains earlier local files and native handles for `batch:N` dependency
resolution. Manifest batch download failures honor `--continue-on-error`; fail-fast
errors expose the current row's safe recovery metadata. Earlier row journals remain on
disk. No batch download failure resubmits a row.

Journals live under `.gflow-image-recovery/<invocation UUID>.json` inside the output
directory. Normal invocations use random UUIDs; REST passes its exact job UUID through
an internal child environment variable. Journals are at most 64 KiB and four outputs.
Writes replace a same-directory private temporary file atomically, fsync the file and,
where supported, its directory. POSIX files use mode 600 inside mode 700 directories;
Windows uses the repository's private-directory ACL helper. Readers reject wrong
invocations, oversized/nonregular/symlink journals, and escaping/missing/empty output
files. Handle recovery works without reading an arbitrary URL.

If storage or checkpoint persistence fails, the immediate typed error still includes
safe in-memory handles and completed paths. REST imports only those allow-listed handles
and contained files from CLI JSON errors. A disk failure can prevent crash durability;
no retry or regeneration is attempted.

Keep journals with output backups while an operation is unresolved. Once the retained
handles/files have been inspected and no recovery is needed, the private journal can be
removed. A crash before Google returns any handles remains an unknown submission outcome;
there is no journal that can prove an image identity in that window.

Offline fault tests cover second-transfer failure, missing/malformed/oversized later
results, subprocess failure/timeout/cancellation, REST and queued-MCP restart, stale
invocation IDs, path escapes, symlinks, bounded metadata, and missing POSIX APIs. This
change has not consumed image or video credits for verification.


Callback delivery reads only acknowledgment headers/status and closes the response
stream without consuming its body. Exact-host HTTPS allowlisting, public-address DNS
pinning, Host/SNI, ten-second timeout, no redirects and five attempts remain enforced.
This bounds recipient-body memory usage; it does not change at-least-once callback
semantics or automatically retry generation.

Unrecognized CLI exit40 results retain conservative `outcomeUnknown: true` and
the trusted admitted project ID, without importing unverified handles or raw
diagnostics. This does not assert that image generation was submitted. An exact
typed upload uncertainty during image-reference preparation instead reports
`errorDetails.operation: upload`, `generationSubmitted: false`, and separate
`knownReferenceMediaGenerationIds` / `pendingReferenceMediaGenerationIds`. These
are reference inputs, not generated outputs. The same typed upload contract is
preserved for image and video asset uploads.

A synchronous asset upload failure returns HTTP502 with a structured `detail`
containing its durable `jobId`, redacted `errorDetails`, and any allow-listed
uncertainty/receipt handles. Poll that job before deciding whether to submit a
new upload. A reported pre-generation upload refusal remains distinct from an
unknown outcome; no failure causes automatic upload or generation replay.

Canonical media-upload failures (exit27) retain a bounded `errorDetails.uploadReason`
observation: `http_error`, `acknowledgement_unconfirmed`,
`response_timeout_after_dispatch`, `not_dispatched`, `dialog_blocked`, or
`unclassified`. Only an exact observed HTTP-error or unconfirmed-acknowledgement
branch exposes `nativeHttpStatus`; generic SDK problem statuses are excluded.
These fields identify the existing upload branch; raw exception detail, route,
remediation, credentials and incident paths never enter job receipts. Unknown
phrases remain `unclassified`. An unconfirmed HTTP200 acknowledgement does not
prove that an upload was rejected. Image generation was not submitted on this
upload failure path (`generationSubmitted: false`); no automatic replay occurs.

On the migrated host, Chromium can finish the page's streamed response while its
CDP body read fails with `No data found for resource with given identifier`.
The native upload, authoritative project timeline, and image-result readers use
one temporary page-owned fetch workaround, scoped to the exact HTTPS endpoint,
selected project, and one internal RPC (`maseQ`, `Zzl0ze`, or `ogiZ0b`). It calls
fetch once, returns the original promise and response, and drains/discards a
clone of an HTTP200 body. No clone bytes are retained or used as an
acknowledgement. The canonical `response.text()` and existing identity/ownership
parsers remain authoritative. There is no replay or additional request.

An observed clone must reach clean EOF within the existing operation budget:
upload 60 seconds / 1 MiB, project catalog 30 seconds / 2 MiB, and image result
180 seconds / 2 MiB. Oversized, aborted, ambiguous or incomplete observed streams
fail closed. The count is a drain budget, not a bound on Chromium's internal tee
buffers or the existing canonical body read. Unavailable hooks and requests
that bypass this fetch wrapper preserve the canonical path; they are not
reported as workaround coverage. Cleanup inactivates the wrapper and restores
fetch only while it still owns that slot. Project navigation installs an owned
main-world CDP init script before the new document starts, removes that exact
registration afterward, and carries an absolute expiry to prevent later rearm.
No Network interception or alternate response-body source is used.

Drain observations contain only completion flags and byte/match counts. A lost
image acknowledgement remains an unknown generation outcome and is never
replayed. Canonically acknowledged media/workflow IDs survive cleanup
cancellation. Opt-in native BDD checks require positive workaround use for both
the synthetic upload and a read-only project timeline; offline fault cases cover
incomplete/oversized streams and cancellation in each affected path.
