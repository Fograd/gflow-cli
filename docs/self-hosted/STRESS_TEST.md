# Bounded Flow reliability test — 2026-10-02

One authenticated Google AI Pro profile, native logged-in browser tokens, no
external CAPTCHA provider, Nano Banana 2, square images. The budget was ten
requested images. Each operation used the normal profile lease; no simultaneous
Google submissions were forced through one profile.

| Stage | Requested | Returned | Time | Evidence |
|---|---:|---:|---:|---|
| Spaced request 1 | 1 | 1 | 26.09 s | JPEG decoded and verified, 1024×1024 |
| Spaced request 2 | 1 | 1 | 28.09 s | JPEG decoded and verified, 1024×1024 |
| First batch | 4 | 3 | 30.09 s | Three decoded JPEGs, 1024×1024; all three IDs present in Google timeline |
| Diagnostic repeat batch | 4 | 4 | 25.72 s | Captured native request had four output entries; HTTP200 reply returned four image records, each 1024×1024 |

**Ten requested; nine returned. No explicit CAPTCHA, unusual-activity, quota or
rate-limit error was observed.** The repeat's captured reply contained no
recognised Google refusal codes. The first batch's raw wire reply was not captured,
so its missing output's cause remains unknown. Returned-image count alone cannot
diagnose CAPTCHA. This is four generation submissions, not ten independent token
trials, and is too small to establish an overall reliability percentage.

The first batch caused the test to stop before the planned queued-request stage.
The remaining four-image allowance was used for a second native batch on the same implementation/model/count with
request/response diagnostics and a fresh simple prompt. It was not an exact
same-prompt reproduction. The repeat succeeded; no automatic replay of
the original job occurred. This test therefore did not establish a maximum request
rate, concurrent account capacity, or sustained daily reliability.

## API correction found by the test

The API previously marked a non-empty image response complete even if it contained
fewer images than requested. It now preserves and registers every returned image,
then reports a failed job with `image_output_count_mismatch`, `expectedCount`,
`receivedCount`, and `retryable:false` when the counts differ. It does not submit
additional generations to fill the gap. The original historical job remains as
recorded; its incorrect completion label is part of this test evidence.

Regression tests first reproduced missing/excess count errors, then passed after
the fix. Exact counts still complete normally; mismatched outputs remain available
through their owned asset records. This correction is in the REST result handling,
not a change to Google's browser transport or CAPTCHA generation.

## What this says about solvers

The tested browser could generate images without an external solver. We have not
found a point at which a solver is required, and cannot infer one from ten images.
The unexplained partial batch is a reliability issue to monitor, not proof that
buying CAPTCHA solves would fix it.

Treat a measured token rejection or unusual-activity refusal as a CAPTCHA/WAF
investigation trigger. Quota, entitlement, content-policy, timeout and partial-count
failures need their own diagnosis. A solver improves a failure only if a controlled
comparison shows Google accepts its replacement token; that integration remains
guarded off while the native action is unmeasured. Do not retry a partially accepted
job automatically, because its existing outputs may already have consumed allowance.

For a larger test, retain a fixed image budget, gradually change one variable
(pace, batch size or account), measure returned output counts and job/error
latencies, and stop on explicit account restrictions. Repeat on each authenticated
account separately. Long-term observations from normal workloads are more useful
than deliberately pushing one account until it is flagged.

Private wire captures remain outside the repository. No credentials, signed media
URLs, account email addresses or project identifiers are included in this report.
