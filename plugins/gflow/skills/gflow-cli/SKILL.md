---
name: gflow-cli
version: "1.2"
skillopt_epoch: 0
description: Use when the user wants to drive Google Flow (Veo image-to-video, Veo text-to-video, Imagen / Nano Banana image generation) from the terminal or a script — including text-to-video, image-to-video, image-to-image, batch image pipelines, or spending Flow credits programmatically. The CLI is `gflow` (or `flow`); install with `uv tool install gflow-cli` or run ad-hoc with `uvx --from gflow-cli gflow ...`. Drives the real Flow web UI through a headed Chrome session (Playwright) after a one-time browser sign-in — it does not bypass the UI, it automates it.
optimization_notes: |
  Known weak spots for the SkillOpt training loop (targets for epoch 1+):
  - Wrong subcommand: agents emit 'gflow video generate' / 'gflow video create' instead of 'gflow video t2v' or 'gflow video i2v'
  - Output flag confusion: '--output'/'-o' takes a FILE path (single asset, v0.48.0+); '--out' (image) / '--out-dir' (video) take a DIRECTORY
  - Prerequisite gap: Playwright Chromium install step skipped on fresh machines
  - Profile parallelism anti-pattern: two generations launched on the same profile in parallel (crashes Chromium)
  - reCAPTCHA direction inverted: agents suggest GFLOW_CLI_HEADLESS=true to fix detection; correct fix is =false
  - UUID reuse: agents call 'gflow image upload' again for an already-uploaded UUID instead of passing it directly to --ref
  - Model alias confusion: '--model imagen' / '--model quality' instead of '--model image4' / '--model nano2'
  - Auth recovery: agents suggest 'gflow auth refresh' / 'gflow auth renew' which do not exist; correct command is 'gflow auth login'
---

# gflow-cli skill

`gflow-cli` is a Python CLI that drives [Google Flow](https://labs.google/fx/tools/flow) — Veo (T2V/I2V) and Imagen / Nano Banana — from the terminal by automating the real Flow web UI in a headed Chrome session (Playwright), not by bypassing it. Source: <https://github.com/ffroliva/gflow-cli>. Canonical command reference: [`docs/USAGE.md`](https://github.com/ffroliva/gflow-cli/blob/main/docs/USAGE.md).

## When to invoke this skill

The user wants to:

- Generate one or many Veo videos from text prompts (T2V) or from initial frame + motion prompt (I2V)
- Generate one or many Imagen / Nano Banana images from text (T2I) or from prompt + reference images (I2I)
- Build a batch pipeline for video generations
- Create a reusable, project-scoped Flow **Character** (a named subject with reference images, optional voice + personality) for consistent subjects across generations (`gflow character`)
- Compose ordered clips into a **scene** and optionally render a credit-free server-side extended video (`gflow scene`)
- Stitch a multi-clip story where each clip is seeded by the previous clip's last frame (`gflow video chain`)
- Use their Flow credits via script instead of clicking through the UI
- Automate Flow inside a content pipeline, AI video production stack, or research project

**Do NOT use this skill** when:

- The user wants production-grade reliability with SLAs — recommend the [official Gen AI SDK](https://github.com/googleapis/python-genai) instead.
- The user asks about audio, music, or anything outside Flow's video/image surface — wrong tool.

## Prerequisites

Before any gflow-cli invocation, verify:

1. **Python 3.11+** is available (`python --version`).
2. **uv** is installed (`uv --version`). If not, install: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or Windows equivalent from <https://docs.astral.sh/uv/>).
3. **gflow-cli** is installed OR available via uvx:
   - Quick: `uvx --from gflow-cli gflow --help` (no install)
   - Persistent: `uv tool install gflow-cli && gflow --help`
4. **Playwright Chromium** has been downloaded once: `uvx --from gflow-cli playwright install chromium` (~150 MB).
5. **A signed-in profile** exists: `gflow auth status` should print `Flow session verified` and exit 0 (it probes the live Flow session endpoint — no browser, no credits; exit 1 means dead or missing session). If not, run `gflow auth login` and walk the user through the one-time browser sign-in.
6. **The user has Flow access** — any Google account with Flow rolled out works. If `gflow image upload` returns 403, missing Flow access is the cause.

## Core commands

```bash
# Auth (one-time)
gflow auth login                                          # opens Chromium, user signs in
gflow auth status                                         # confirms session
gflow auth                                                # bare: list profiles or trigger first login
gflow auth logout                                         # delete a saved session

# Veo video-credit balance (read-only; image models use separate daily quotas)
gflow credits user [--profile NAME] [--json]
gflow credits list [--json]                               # all saved profiles

# Image generation (Imagen / Nano Banana)
gflow image upload <path>                                 # → asset UUID + dimensions
gflow image t2i "<prompt>" [--model {nano2|nano2-lite|nano-pro|image4}] \
                            [--aspect {9:16|16:9|1:1|4:3|3:4}] \
                            [-n 1..4] [--out DIR]
gflow image i2i "<prompt>" --ref PATH_OR_UUID [--ref ...] [...same as t2i]
gflow image upscale <mediaId> --scale {2k|4k} [--project ID] [--out DIR]  # 4K is Ultra-only
gflow image batch <manifest.tsv|manifest.json> [-n 1..4] [--aspect ...] [--out DIR]  # shared project, up to 5 prompts; refuses any row ref (exit 2)
gflow run --config <batch.json>                           # JSON image batch; a row's "ref" may be "batch:N" (an earlier
                                                          # row's image, in place, no upload) or a local file (uploaded once)
# On migrated flow.google.com accounts (#639), t2i, i2i, and upscale are ported (a project is
# created when --project is omitted, #864): i2i accepts local --ref files only, all
# five aspects. UUIDs, @Name/entity references, Imagen 4 (image4), and image batch
# are refused there with exit 36.

# Video generation (Veo 3.1)
gflow video t2v "<prompt>" [--project ID] [--model ...] [--duration 4|6|8|10] [--resolution 360p|720p] [--out-dir DIR] [--aspect ...]  # --resolution: omni-flash only; without --project a project is created first, on either host (#864); 10s is omni-flash-only
gflow video i2v --initial-frame <image|media-UUID> "<prompt>" [--out-dir DIR] [...same as t2v]  # UUID = in-project asset, no re-upload (#287; pair with --project)
gflow video upscale <mediaId> --scale {1080p|720p|270p} [--project ID] [--out DIR]  # 1080p = Full HD, 720p = original, 270p = GIF
# `gflow video` has no `batch` subcommand — that stub never worked and was
# removed. For multi-clip runs, loop `gflow video t2v`/`i2v` from the shell.
gflow video chain <manifest.jsonl> [--out-dir DIR] [--dry-run] \
                  [--max-links N] [--resume-from N]   # last-frame I2V chaining; veo models only

# Characters (reusable, project-scoped subjects)
gflow character create --project <id> --name "<name>" --face-prompt "<prompt>" \
                       [--body-prompt "<prompt>"] [--voice <id>] [--personality "<text>"] \
                       [--model {nano2|nanopro}]
gflow character list --project <id>
gflow character show <character-id> --project <id>
gflow character rm --project <id> (--id <character-id> | --name "<name>") [--yes]   # delete (FREE)
gflow character voices                                    # list the Gemini voice catalog

# Scenes (Add Clip / compose ordered clips)
gflow scene create --project <id> <clip-id> [<clip-id> ...] \
                   [-o extended.mp4]                       # --output = credit-free server-side concat
gflow scene show <scene-id> --project <id>

# Agent instructions (project brief cards, credits-free setup) — --project is REQUIRED
gflow instructions add TITLE --text TEXT [--ref REF]... --project ID [--disabled]
gflow instructions list --project ID [--json]
gflow instructions enable (TITLE | --id ID) --project ID
gflow instructions disable (TITLE | --id ID) --project ID
gflow instructions rm (TITLE | --id ID) --project ID
gflow instructions apply FILE --project ID                # declarative full-sync (TOML/JSON)
gflow instructions toggle-mode (--on | --off) --project ID # toggle master agent switch

# Keeping gflow-cli current (every command shows a banner when a newer release exists)
gflow update [--check] [--json]
gflow docs [TOPIC] [--search TERM] [--json]                            # upgrades via uv tool / pipx / pip; source installs refused (exit 11)
```

Every subcommand accepts `--profile <name>` (per-subcommand, not global) to drive multiple Google accounts side-by-side.

## Recipes

### Single image (most common)

```bash
gflow image t2i "a hot air balloon over Tokyo at sunrise" --aspect 16:9
```

### Native image seed

For a single prompt on `flow.google.com`, image `t2i` and `i2i` accept `--seed 42`. The CLI, SDK and MCP direct/queued paths retain the seed. Valid range is `0..2147483647-count+1`; outputs use seed+index and returned Google seeds are checked. Other hosts/transports and multi-prompt mode reject seeds before submission. Matching seeds do not promise identical pixels. Corrected CLI seed handling was live-verified with one native image returning seed42 and a valid1024×1024 downloaded JPEG.

### Image fan-out (4 variants in parallel)

```bash
gflow image t2i "variations of a minimalist fox logo" -n 4 --aspect 1:1 --out ./logos/
```

### Image-to-image with a local reference

```bash
gflow image i2i "make it cinematic, golden hour" --ref hero.png
```

### Image-to-image with an already-uploaded asset UUID (no re-upload)

```bash
UUID=$(gflow image upload hero.png | awk '/Asset UUID:/ {print $3}')
gflow image i2i "stylize this asset" --ref "$UUID"
```

### Single clip from initial frame

```bash
gflow video i2v --initial-frame ./input.png "Slow cinematic push-in, soft golden light at sunset" --out-dir outputs
```

### Batch from a directory of inputs (bash)

There is no manifest-driven video batch command — that stub never worked and
was removed. Loop `gflow video t2v`/`i2v` from the shell instead:

```bash
mkdir -p out
for img in ./inputs/*.png; do
  name=$(basename "$img" .png)
  gflow video i2v --initial-frame "$img" "Cinematic push-in" --out-dir out
done
```

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
Get-ChildItem ./inputs/*.png | ForEach-Object {
    gflow video i2v --initial-frame $_.FullName "Cinematic push-in" --out-dir out
}
```

### Create a reusable Character for consistent subjects

```bash
# A Character is a named, project-scoped subject reused across generations.
gflow character create --project "$PROJECT_ID" --name "Joaquim" \
  --face-prompt "weathered fisherman, grey beard, kind eyes" \
  --body-prompt "tall, broad-shouldered, wearing a navy wool sweater" \
  --voice <voice-id> --model nano2
gflow character voices            # discover valid --voice ids first
gflow character list --project "$PROJECT_ID"
```

See [`docs/CHARACTER.md`](https://github.com/ffroliva/gflow-cli/blob/main/docs/CHARACTER.md) for the full domain model, wire protocol, and the crash-recoverable persist-before-spend saga.

### Compose clips into an extended video (credit-free)

```bash
# Concatenate ordered clips server-side via runVideoFxConcatenation — no local ffmpeg, no credits.
gflow scene create --project "$PROJECT_ID" "$CLIP_A" "$CLIP_B" -o extended.mp4
```

### Chain clips by last frame (story stitching)

```bash
# manifest.jsonl: one JSON object per line. Link 0 = t2v; later links = i2v seeded by the
# previous clip's last frame. Each link is a pending video operation; credit
# use varies by model/duration/tier — check Flow. veo models only.
gflow video chain ./story.jsonl --out-dir ./out/ --dry-run   # preview the plan first
gflow video chain ./story.jsonl --out-dir ./out/             # then run for real
```

### Sync instructions and generate (3-layer pipeline)

```bash
# 1. Discover project ID from Flow editor URL (.../project/<id>/...) or create one.
# 2. Set up the brief cards (credits-free setup).
gflow instructions apply brief.toml --project 6b714c4e-...
# 3. Generate using that project context (steers via reasoning path).
gflow image t2i "a bicycle" --project 6b714c4e-...
```

### Use as a Python library

```python
import asyncio
from pathlib import Path
from gflow_cli.api.client import FlowApiClient
from gflow_cli.paths import profile_dir

async def make_clip(image: Path, prompt: str, out: Path) -> None:
    async with FlowApiClient(profile_dir=profile_dir("default")) as client:
        project = await client.create_project(title="gflow-cli demo")
        asset = await client.upload_image(image, project.project_id)
        op = await client.generate_video(
            project_id=project.project_id,
            prompt=prompt,
            start_asset=asset,
            aspect="9:16",
        )
        # Poll op.workflow_id with client.poll_video_status(...) and
        # client.download_video(...) when status reaches succeeded.

asyncio.run(make_clip(Path("in.png"), "Push-in", Path("out.mp4")))
```

## Layered Instructions Pipeline

The `gflow-cli` supports a 3-layer pipeline for persistent generation context (Agent Mode brief cards):

1. **Layer 1 (Setup - credits-free):** Set up the project brief cards using `gflow instructions add` or `gflow instructions apply`.
2. **Layer 2 (Generate):** Run generations targeting that project with `--project <id>`. Enabled brief cards are automatically resolved and folded into the prompt via the agent's reasoning path.
3. **Layer 3 (Compose):** Scene-level composition overrides via `movie.toml` `[[scene.instructions.card]]` or `[scene.instructions] disable` blocks.

### Constraints & Rules:
- **Discover Project ID First:** Persistent cards require a real project. Discover the project ID from the Flow browser editor URL (`.../project/<id>/...`) or create one.
- **DO NOT** use the ephemeral `-i / --instruction` option for anything you want to reuse; it creates a new card every call. Prefer persistent `gflow instructions` cards.
- **Master Switch:** Ensure agent mode is toggled on (`gflow instructions toggle-mode --on`) for cards to steer output.

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `No session for profile 'default'` | First run, no auth | `gflow auth login` |
| `403 Forbidden` from upload / generate | Account doesn't have Flow access | Verify in [labs.google/fx/tools/flow](https://labs.google/fx/tools/flow) |
| reCAPTCHA refuses to mint a token (headless detected) | Google bot-detection | Set `GFLOW_CLI_HEADLESS=false` and re-run; a headed window passes detection. With `--json`, a mint failure has `type` `…/errors/recaptcha-mint` and exits 1; re-run only when `retryable` is true |
| `Playwright Executable doesn't exist` | Chromium not downloaded | `uvx --from gflow-cli playwright install chromium` |
| Generations all fail with the same UUID | Stale Flow session | `gflow auth login` again to refresh cookies |
| Quota exceeded | Burned through monthly credits | Wait for reset, or upgrade subscription |

## Important constraints

- **Video costs Flow credits.** Video generation draws down the balance shown by `gflow credits`; image generation uses separate per-model daily quotas. Confirm before running batches.
- **Not for production-grade SLAs.** gflow-cli reverse-engineers a private Google API. It can break without notice. For production, use the [official Gen AI SDK](https://github.com/googleapis/python-genai).
- **Don't share auth profiles.** The Playwright profile dir lives at the per-OS user-data location (Windows: `%LOCALAPPDATA%\gflow-cli\profile_*`; macOS: `~/Library/Application Support/gflow-cli/profile_*`; Linux: `~/.local/share/gflow-cli/profile_*`) and contains Google session cookies — treat as secrets.
- **Same profile can't run in parallel.** Chromium refuses two persistent contexts on the same profile dir; use different `--profile` names for parallel work.
- **Respect Google's [Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy).** Don't generate content that would get the user's Google account banned.

## Known agent failure modes

Documented errors agents commonly make — negative examples for the SkillOpt training loop:

| Mistake | Correct behaviour |
|---|---|
| `gflow video generate` or `gflow video create` | `gflow video t2v` (text→video) or `gflow video i2v` (image→video) |
| `--output DIR` (a directory) as the output location | `-o`/`--output PATH` is an explicit FILE path on `image t2i`/`i2i` and `video t2v`/`i2v` (v0.48.0+, single-prompt only); use `--out DIR` (image) / `--out-dir DIR` (video) for directory output. `r2v`/`chain` have no `-o` |
| `gflow auth` bare or `gflow login` to sign in | `gflow auth login` — bare `gflow auth` only lists profiles |
| `gflow auth refresh` / `gflow auth renew` (don't exist) | `gflow auth login` to refresh a stale or expired session |
| `playwright install` or `playwright install --all` | `uvx --from gflow-cli playwright install chromium` (Chromium only, ~150 MB) |
| Running two generations on the same `--profile` in parallel | Use different `--profile` names — Chromium refuses two persistent contexts on the same dir |
| `GFLOW_CLI_HEADLESS=true` to fix reCAPTCHA failures | `GFLOW_CLI_HEADLESS=false` — headless mode *causes* bot-detection, not prevents it |
| Calling `gflow image upload` again for an already-uploaded UUID | Pass the UUID directly to `--ref UUID` (i2i) or `--initial-frame/--end-frame UUID` (i2v, with `--project`) — no re-upload needed |
| `--model imagen` / `--model quality` / `--model high` | `--model image4` (Imagen 3.5), `--model nano-pro` (Gem Pix 2), `--model nano2` (Narwhal) |
| Python: `client = FlowApiClient(...)` then method calls | Must use `async with FlowApiClient(...) as client:` — it's an async context manager |
| Python: `from gflow_cli import FlowApiClient` | `from gflow_cli.api.client import FlowApiClient` |
| `gflow video t2v`/`i2v`/`r2v` with an unported UUID/entity reference or model on an account served `flow.google.com` (exit 36) | Pass local files instead — migrated hosts support video t2v, local-file i2v/r2v, and image t2i/i2i (local refs) only; exit 36 is non-retryable, `GFLOW_CLI_FLOW_HOST=labs.google` is the kill switch (see USAGE § gflow video t2v / i2v / r2v and image sections) |
| Telling a user on `flow.google.com` whose run exits **25** to retry, switch profile or pass `--ui-mode classic` | Their account's composer is **agent-only** — no classic arm exists, so aspect/model/count are Agent-settings defaults and gflow has no driver for it (`retryable: false`, $0, pre-submit). Nothing in gflow reaches it; the Flow web UI still works ([#799](https://github.com/ffroliva/gflow-cli/issues/799)). Exit 25 on `labs.google` IS the retryable A/B cohort — check the host before advising |
| Suggesting a native `batch` subcommand under `gflow video` | It doesn't exist — that stub never worked and was removed. Loop `gflow video t2v`/`i2v` from the shell for multi-clip runs (`gflow image batch manifest.tsv\|json` is the real, working batch command, but it's image-only) |

## Disclaimer

gflow-cli is **not affiliated with Google**. Reverse-engineered; may break when Google changes Flow's private API. Read the [DISCLAIMER](https://github.com/ffroliva/gflow-cli/blob/main/DISCLAIMER.md) before deploying in any sensitive setting.

### Native existing-image character metadata

Use `gflow character create-from-images --project <UUID> --name <name>
--image-reference-1 <media-UUID> [--image-reference-2 <media-UUID>]
[--personality <notes>] [--voice <system-preset>] --profile <profile> --json`
when images already exist. Both images must be owned native images in that
project with integrity-verified local PNG/JPEG catalog copies. This copies into
portrait/body slots and spends no generation credits. Keep generated-portrait
`character create --face-prompt ...` separate.

Use `character update --project <UUID> --id <UUID> [--name <name>]
[--personality <notes>] [--voice <preset>] --json` for free metadata changes.
Empty notes clear personality. MCP twins are `gflow_character_create_from_images`
and `gflow_character_update`; native list/show use their existing twins. MCP
removal is `gflow_character_rm` and requires explicit `confirm_delete: true`;
CLI removal requires `--yes` for unattended use. Deletion affects the character,
not original source images. System preset assignment is metadata, not a rendered
speech proof or custom voice feature. Mutations run directly, never as a queued
replay. CLI exit 40 / MCP nonretryable typed problems preserve known partial
identities; inspect before creating again.

### Native read-only inventory

`gflow project list` defaults to the local catalog. Explicit `--source google`
reads one native account page by default (fixed 21 rows; omit --limit), with `--cursor`
forwarding the returned opaque cursor. `gflow project media --project <UUID>
--source google --json` reads mixed native media identifiers/kinds/dimensions.
Both return unknown completeness and perform no local sync or absence deletion.
MCP twins are `gflow_list_projects(source="google", cursor=...)` (omit limit,
use offset 0) and `gflow_project_media(project=<UUID>)`. No generation/solver calls.

### Native preset voice discovery

The default character voices command reads the bundled catalog offline.
Explicit --catalog google --project PROJECT_UUID --profile NAME --json reads
native system presets without generation. SDK list_native_voices(project_id)
and MCP gflow_character_voices(catalog="google", project=..., profile=...)
use the same snapshot semantics: complete is null, returned_count describes
this scoped system preset snapshot. Custom voice CRUD and rendered TTS are
not implied. Offline adapter tests pass; new live CLI/MCP proof is pending.

### Private session import

The CLI-only auth import-cookies command accepts --cookies-file /private/cookies.tsv,
--profile NEW_NAME, optional --expected-email EXPECTED_ACCOUNT and --project UUID,
and --json safe metadata. It stages a new automation profile and requires actual
Google identity and Flow access before activation; parsing a cookie table is not
proof of authentication. Existing profiles are preserved. Keep the file private
and never paste cookie values into command arguments or logs. See the
[self-hosted cookie import guide](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/COOKIE_IMPORT.md).
Use Vivaldi for personal browser setup; the current remote automation profile
continues to use its configured headed Chrome engine.


### Explicit image reference slot syntax

Image CLI leaf commands accept `--reference-syntax slots`; MCP image generation accepts `reference_syntax="slots"`. The default `names` retains saved asset-name expansion. Slot mode uses ordered image and character inputs as `@reference_1..10` and `@character_1..7`, matches tokens case-insensitively, preserves repeated positions and requires matching inputs. Unknown token families and email text stay literal. Queue codecs retain and validate the immutable plan; they do not strip markers into text that appears grounded.

Character references require one fresh native project snapshot proving the active owned image workflows. Each actual character image consumes the shared image budget; the native Lite cap remains 3. Local upload identities are mapped to acknowledged Google identities before native wire validation. Image positional transport is implemented in the isolated expansion; the accepted one-image native SDK proof passed in 104.75s and is recorded separately in the verification ledger. Canonical video positional syntax is not yet implemented.


### Native MP4 upload and reversible archive

CLI project upload-video FILE --project UUID --rights-confirmed --profile PROFILE --json and project archive --project UUID --media-id UUID --confirm-archive --profile PROFILE --json perform direct native operations without generation or replay. MCP mirrors are gflow_upload_video(path, project, rights_confirmed=True, profile) and gflow_archive_media(media_ids, project, confirm_archive=True, profile). Upload snapshots a stable regular MP4 before browser creation; archive verifies every active owned batch sibling before the first write. Both require explicit per-request confirmation. Typed exit40 preserves safe known/pending media identities when a write or its cleanup is uncertain. Complete native membership is not inferred from a partial timeline.

Image Auto: `image i2i --aspect auto` requires the first reference to be a local PNG/JPEG or an owned native image UUID with measured dimensions and an explicit project. Text/character-only requests refuse. `gflow run --config` supports per-row Auto with local files or successfully downloaded `batch:N` images. This is a local nearest-supported-ratio approximation; preserve requested/resolved/policy metadata. See `docs/AUTO_ASPECT.md`.

## Saved speech and permanent media deletion

Use voice list/show/create/rm for saved preset-based TTS. Creation can consume credits and performs one preview plus two metadata saves without retry. voice rm requires --confirm-delete; system presets are not saved deletable voices. Read docs/self-hosted/VOICES.md.

project delete-media --project UUID --media-id UUID --confirm-delete permanently targets only requested owned IDs after fresh reads. project archive remains reversible whole-batch trash. Preserve exit40 known/pending handles and inspect uncertain results before another mutation. Source-derived additions await final E2E acceptance.

Native video edit: `video edit-models --project UUID` discovers account-native keys; `video edit-native SOURCE --project UUID --prompt TEXT --model-key KEY [--end-frame N]` submits one source-derived edit. Omitted end uses measured source duration at virtual24fps, rounded down and capped240; unavailable duration refuses before generation. Optional5image/3nativeaudio media UUID refs require active sameproject ownership; audio need not be saved-TTS visible. Optional7character entity UUID refs and canonical positional image/audio/entity markers share fresh native combined capacities. Available presets require fresh native catalog proof and consume native audio capacity. Paid acceptance remains pending; see docs/VIDEO_EDIT.md.

Native standalone extension: `video extension-models --project UUID` discovers
native keys; `video extend-native SOURCE --project UUID --prompt TEXT` supports
optional model key, count 1–4 and frame trims. MCP twins are
`gflow_list_extension_models` and `gflow_extend_native_video`.

Native image/audio ingredients: `video reference-models --project UUID
--with-audio` discovers current account keys and budgets; `video reference-native
--project UUID --prompt TEXT --image-ref UUID --audio-ref UUID` uses existing
owned IDs. At least one ingredient is required. Count 1–4; optional model key,
aspect, duration and resolution are checked against the current catalog. MCP
mirrors are `gflow_list_reference_video_models` and
`gflow_generate_native_reference_video`. Paid acceptance awaits final E2E. Read
`docs/self-hosted/NATIVE_REFERENCE_VIDEO.md`.

Native reads: project get-media --project UUID --media-id UUID returns confidential fresh image/video/audio URL metadata (audio metadata only). project download-media additionally requires --output-dir DIR and validates downloaded content (ffprobe for video), never overwrites files or generates/upscales. MCP mirrors gflow_get_native_asset and gflow_download_native_asset execute directly; these GET reads do not persist signed URLs in generation queues.

Character show supports --include-urls --json for fresh confidential native
reference-image/thumbnail detail, mirrored by MCP include_urls. Metadata-only
defaults remain unchanged; unresolved ownership refuses rather than guessing.

Native project traversal: `gflow project list --source google --all-pages
--max-pages 2 --json`; MCP `gflow_list_projects(source="google",
all_pages=True, max_pages=2)`. Page cap1–100 defaults100. Local source and a
cap without traversal refuse. Results preserve next cursor, pages read and
pagination exhaustion; complete remains unknown and absence never means deleted.

Observed account project catalogs: append `--include-catalogs --max-projects 1`
to native `project list`; MCP mirrors `include_catalogs/max_projects`.
Cap1–20 defaults20. Returns four typed URL-free per-project catalogs and known
counts, unread listed IDs and later-page cursor separately. Completeness remains
unknown. One leased page/180seconds; no cache or missing-object deletion.

Native R2V characters: video reference-native --character-ref, SDK reference_character_ids,
MCP character_ref, REST character_N or mixed referenceImage_N UUID slots.
Fresh active entity-owned image/audio weights and native capacity pools apply;
slot positions survive classification. V2V character transport now uses the same
fresh ownership and native budgets. Available preset inputs require fresh native
catalog proof. Rendered acceptance remains R12. See docs/self-hosted/NATIVE_REFERENCE_VIDEO.md.


Native R2V/V2V audio refs also accept available system preset names or exact
voices/lowercase resources through existing CLI/MCP/SDK/REST fields. Aliases
normalize before duplicate checks; fresh unique native preset availability and
actual audio capacities apply before mint. Arbitrary paths/URLs refuse. UUID
ownership stays strict. Reference preflight does not prove rendered speech.


Native supplied CAPTCHA: scoped SDK native_captcha_token, private-file CLI
--captcha-token-file on reference-native/edit-native/extend-native/voice create,
direct MCP captcha_token and REST captchaToken share single-use project/action
binding. Token files/values are private; no fallback or uncertain retry.
Provider acceptance remains unverified. See docs/self-hosted/NATIVE_CAPTCHA.md.

Native video promotion: SDK/CLI video upscale-native/upscale-models, direct MCP twins, HTTP explicit operation=promotion. Targets720p/1080p/4k require fresh tier/model/source proof. Paid acceptance remains R12. See [native promotion](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/NATIVE_VIDEO_PROMOTION.md).

Fresh native image reference budgets: SDK/CLI image reference-models, direct MCP twin, HTTP images/reference/models. Effective=min(advertised,transport), fresh before upload/mint; Lite3 conservative. See [budgets](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/IMAGE_REFERENCE_BUDGETS.md).

Confirmed permanent-delete retries preserve requested deleted IDs, separate newly/already deleted IDs and make zero mutation calls for receipt-backed already-gone batches. Fresh account/project and exact GetMedia NOT_FOUND proof required; arbitrary absent UUIDs refuse. See [native media](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/NATIVE_MEDIA.md#confirmed-deletion-retries-r09).

HTTP native image/video aliases require explicit fresh-owned registration; reads revalidate and removal deletes only the local mapping. Opaque URL-safe prefixes never establish vendor/account ownership; supported HTTP input fields resolve exact registered mappings with fresh proof. SDK/CLI/MCP retain UUID inputs. See [alias API](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-native-imagevideo-aliases).

Bounded native history: SDK list_native_history defaults to one page; existing project-list CLI --include-history/--history-cursor/--history-max-pages/--history-max-media, MCP snake_case and HTTP includeHistory/historyCursor/historyMaxPages/historyMaxMedia enrich Google project discovery. Up to50 pages/1000 media/45seconds; URL-free observations, complete unknown and no absence-based deletion. See [history API](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#bounded-native-account-history).

HTTP includeHistory returns inventoryObservations from private exact account/profile-scoped metadata upserts. No URLs/prompts/captions/cursors, no absence-based deletion and no fresh ownership authority; SDK/CLI/MCP reads do not persist this REST-only cache.

HTTP character/saved-voice aliases also support explicit scoped registration and fresh detail reads; only local mappings are removed. Supported HTTP generation/operation inputs now resolve exact mappings before queueing; Google resource deletion and character CRUD mutation inputs remain raw. SDK/CLI/MCP UUID inputs remain unchanged. See [resource aliases](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-character-and-saved-voice-aliases).

Native catalog resume accepts SDK/MCP catalog_project_ids, repeat CLI --catalog-project-id and HTTP catalogProjectIds with native catalog inclusion;1–20unique ordered IDs, incompatible account pagination, bounded remaining IDs. REST-only observations also retain empty projects/characters/saved-user voices without URL persistence or ownership/deletion authority. See [catalog resume](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-native-catalog-resume).

HTTP alias inputs resolve registered image/video/character/saved-voice mappings before account selection and queueing, with fresh same-account/project/type proof and preserved slots. Queued jobs carry canonical UUIDs, not protected URLs. SDK/CLI/MCP raw contracts and presets are unchanged. See [HTTP alias inputs](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#registered-aliases-as-http-inputs).

General HTTP /videos frames/ingredients can cache a freshly verified registered
image alias privately before admission: validated PNG/JPEG up to20MiB, exact
profile/project scope and atomic store insertion. Cache failure502 queues no
generation; existing foreign cache422. Unregistered raw UUID/public image GET
behavior stays unchanged. Actual workers-disabled cache/forwarding BDD passed
64.71seconds with zero generation; rendered acceptance remains pending.

HTTP project-list defaults now return generated-history summaries (source=history); media-list defaults now read native Google inventory. Explicit source=local retains managed cache and project source=google retains catalog discovery. SDK/CLI/MCP history adds summary fields without new flags/tools. See [default changes](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#generated-history-summaries-and-http-defaults). Actual default-summary/media BDD passed65.84seconds with zero generation; final gates passed6746tests; sourceea9cc2c5 is published/deployed with all3 production HTTP200 reads, zero generation; complete history is not claimed.


Observed account characters/saved voices: SDK list_account_resources, CLI project account-resources, direct MCP gflow_list_account_resources and REST GET assets/resources/{email} share bounded opaque continuation. Completeness is unknown; no absence deletion. See [resources](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/ACCOUNT_RESOURCES.md).
Generic video count1 provider controls: SDK services.video_captcha wrapper, CLI t2v/i2v/r2v provider-order/retry/private-token-file and queued MCP gflow_generate_video provider controls; HTTP videos accepts mutually exclusive token/order/retry. Queued confidential tokens refuse. See [generic CAPTCHA](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/GENERIC_VIDEO_CAPTCHA.md).
Image upscale2K/4K explicit REST provider controls support1–10 positively confirmed WAF-only attempts. Fresh4K availability is checked before paid mint and dispatch; unavailable Pro options refuse. Existing SDK scopes/CLI token-file/direct MCP token remain single sequence. See [CAPTCHA](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/CAPTCHA.md).
