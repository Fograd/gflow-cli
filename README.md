<!-- mcp-name: io.github.ffroliva/gflow-cli -->

# gflow-cli

> Python CLI and MCP server for Google Flow. Drive [Veo](https://labs.google/fx/tools/flow) (image-to-video, text-to-video) and Imagen (text-to-image) from your terminal: scripted, batched, pipeline-ready.

[![PyPI version](https://img.shields.io/pypi/v/gflow-cli.svg)](https://pypi.org/project/gflow-cli/)
[![CI](https://github.com/ffroliva/gflow-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/ffroliva/gflow-cli/actions/workflows/ci.yml)
[![Release](https://github.com/ffroliva/gflow-cli/actions/workflows/release.yml/badge.svg)](https://github.com/ffroliva/gflow-cli/actions/workflows/release.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/gflow-cli.svg)](https://pypi.org/project/gflow-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](docs/PROJECT_STATUS.md)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)
[![Tests: TDD](https://img.shields.io/badge/tests-TDD-brightgreen.svg)](CONTRIBUTING.md)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_gflow-cli&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ffroliva_gflow-cli)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_gflow-cli&metric=coverage)](https://sonarcloud.io/component_measures?id=ffroliva_gflow-cli&metric=coverage)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ffroliva/gflow-cli/badge)](https://scorecard.dev/viewer/?uri=github.com/ffroliva/gflow-cli)
[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/ffroliva/gflow-cli)

<!-- Gold sponsors appear here: filled by scripts/ci/update_sponsors.py, empty until there is one. -->
<!-- sponsors-gold:start -->

<!-- sponsors-gold:end -->

> ⚠️ **Read this before you install.** gflow-cli is **alpha and reverse-engineered — not affiliated with Google**. It drives a headed browser on *your own* Google Flow session, so treat it as your own account risk: automation is subject to Google's ToS, and endpoints or UI can change without notice. It works with **any Google account** that has Flow access, and every generation bills against your account's Flow credit allowance. Read the full [DISCLAIMER](DISCLAIMER.md).
>
> 🛡️ **"Will this get my account flagged?"** The honest, specific answer — what the tool does to stay unremarkable (headed real Chrome, randomised interaction timing, paced submissions), what it deliberately does **not** do (no proxies, no fingerprint spoofing, no pretending it isn't automation), what you can tune, and what we cannot promise — is in [docs/ACCOUNT_SAFETY.md](docs/ACCOUNT_SAFETY.md).
>
> 💳 **What failure costs you.** Generations use your Google account's model-specific allowances; saved speech has a separate native generation path, while local composition does not submit a Google generation. When Flow's UI drifts mid-run, the CLI fails fast and loudly with distinct exit codes (e.g. selector drift = exit 23) instead of resubmitting, and batch items are recorded locally *before* submission so a broken run never silently burns credits on a stale state. See [KNOWN_ISSUES](KNOWN_ISSUES.md) for the current risk list.
>
> 🌐 **Headed browser today.** gflow drives Flow through a persistent Playwright Chromium profile, because Google's auth and reCAPTCHA gates require it. The [Architecture](#architecture--current-limitations) section shows where you can help.

## Self-hosted fork

This fork adds a single-user authenticated HTTP API and integrates the migrated image/video export work from [upstream PR 922](https://github.com/ffroliva/gflow-cli/pull/922), with additional validation and regression tests. Native 2K image upscaling has been verified on a Pro account through the CLI, MCP and HTTP adapter.

Start with the [self-hosted documentation index](docs/self-hosted/INDEX.md), then read the [API guide](docs/self-hosted/API.md), [deployment example](deploy/selfhost/README.md) and [Google Flow compatibility inventory](docs/self-hosted/PARITY.md). The compatibility inventory distinguishes working routes, unverified adapters and unsupported controls. This fork does not yet implement every useapi feature. Private CLI session import uses a staged new profile and verifies actual Flow access; see the [cookie import guide](docs/self-hosted/COOKIE_IMPORT.md).

## Why gflow-cli?

You have a Google account with Flow access, you have Veo credits, and you run real batch work. gflow-cli gives you:

- **Batch generation.** Loop prompts straight from the shell: `for p in $(cat prompts.txt); do gflow image t2i "$p"; done`. Image batching plus `gflow video t2v` / `i2v` / `r2v` all ship today, and `gflow video extend` continues an existing clip past Flow's 8s ceiling.
- **Consistent subjects.** `gflow character create` mints a Flow Character (face and body reference) so the same person appears from one generation to the next.
- **Prompt tools.** `--tool creative-director` rewrites a terse prompt into a vivid one (Google's 5-component formula) before generating — on any command. Bring your own with [My Tools](docs/TOOLS.md).
- **Pipelines.** Wire Veo into your content automation, AI-video stack, or batch experiments.
- **Terminal-native.** After one `gflow auth login`, you stay in the shell. No clicking through dialogs.

Same Veo and Imagen models, same quality, same billing against your own Google account, now programmatic.

## 60-second quick start

```bash
# 1 · Install (uv recommended; also: pip install gflow-cli)
uv tool install gflow-cli
uv tool run --from gflow-cli playwright install chromium     # one-time, ~150 MB
# later: `gflow update` upgrades in place (every command shows a banner when a newer release is out)

# 2 · Authenticate (one-time, opens a real Chrome window)
gflow auth login --browser chrome

# Check the current balance (or use `credits list` for every saved profile)
gflow credits user

# 3 · Generate
gflow image t2i "a hot air balloon over Tokyo at sunrise"
# or:
gflow video t2v "Slow cinematic push-in on a sunlit forest clearing" --aspect 16:9
# or mint a reusable Character (face + body reference):
gflow character create --project <id> --name "Aria" --face-prompt "..." --body-prompt "..."
```

Outputs land under `$GFLOW_CLI_OUTPUT_DIR`, or you can route them to S3, MinIO, or Google Cloud Storage with [`GFLOW_CLI_STORAGE_URI`](docs/EXTERNAL_STORAGE.md). The first call takes 30 to 90 seconds while Chromium warms up; later calls reuse the warm session.

> **Why `--browser chrome`?** It is the only strategy that marks the profile as a real-Chrome profile, which is what later generation runs open it with. The default `auto` picks it whenever Chrome is installed — see [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

> **Installing from a local checkout?** `uv tool install <path>` **ignores `uv.lock`** and resolves dependencies from the `pyproject.toml` ranges, so it can hand you a Playwright build this project has never tested. Playwright ships the browser driver, and an untested minor can wedge a generation silently. Carry the locked version explicitly:
>
> ```bash
> uv tool install --force --with playwright==1.59.0 .
> ```
>
> Installing from PyPI (`uv tool install gflow-cli`) is unaffected — the published range is upper-bounded. Check what you actually have with `uv tool run --from gflow-cli python -c "import importlib.metadata as m; print(m.version('playwright'))"`.

For the full 10-minute walkthrough with troubleshooting and multi-account setup, see **[USER_GUIDE: Journey 1](docs/USER_GUIDE.md#journey-1--first-time-setup-10-minutes)**.

## Examples

One command in, real Flow output back. Left: `gflow image t2i` generating a photorealistic scene in your library. Right: a frame-to-frame transform.

![gflow-cli examples: text-to-image generation, and a before/after frame transform](https://raw.githubusercontent.com/ffroliva/gflow-cli/main/docs/assets/examples.webp)

## Demo

![gflow image t2i runs a single 9:16 prompt, streams structlog output, and writes a PNG to disk](https://raw.githubusercontent.com/ffroliva/gflow-cli/main/docs/assets/example-run.gif)

A single `gflow image t2i "..." --aspect 9:16 --model nano2` call against a logged-in Flow profile. The terminal streams the run's `structlog` JSON, then lists the written PNG. Chromium drives the Flow editor silently in the background.

Reproduce the recording with [`scripts/record_demo.ps1`](scripts/record_demo.ps1) (Windows, OBS, ffmpeg, gifski). More formats, including the side-by-side split-screen: **[docs/DEMOS.md](docs/DEMOS.md)**.

## Documentation

[**docs/INDEX.md**](docs/INDEX.md) is the master routing layer. Quick links:

| Topic | Read |
|---|---|
| 🎯 **Getting started** | [User Guide](docs/USER_GUIDE.md) · [Usage](docs/USAGE.md) · [Configuration](docs/CONFIGURATION.md) |
| **Storage & catalog** | [External Storage](docs/EXTERNAL_STORAGE.md) · [Data Layer](docs/DATA_LAYER.md) |
| 🎭 **Characters** | [Characters](docs/CHARACTER.md), reusable subjects (`gflow character`) |
| 🤖 **Agentic & automation** | [Instructions](docs/INSTRUCTIONS.md) (`gflow instructions`, persistent brief cards) · [Movie](docs/MOVIE.md) (`gflow movie`, multi-scene manifests) · [Tools](docs/TOOLS.md) (`--tool`, prompt rewriting) · [MCP server](docs/MCP.md) (`gflow mcp run` / `gflow serve`) |
| 🔐 **Auth & sessions** | [Authentication](docs/AUTHENTICATION.md) · [Known issues](KNOWN_ISSUES.md) |
| 📣 **Where to install from** | [Marketplaces](docs/MARKETPLACES.md) (every channel and what each actually delivers) · [Container](docs/CONTAINER.md) (why the image introspects but cannot generate) |
| 🏗️ **Internals** | [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Debugging](docs/DEBUGGING.md) |
| 📦 **Releases** | [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Release protocol](RELEASE.md) · [Project status](docs/PROJECT_STATUS.md) |
| 🤝 **Contributing** | [Contributing](CONTRIBUTING.md) · [Development](docs/DEVELOPMENT.md) · [GitHub workflow](docs/GITHUB.md) |

## For AI agents & LLMs

gflow-cli ships four agent entry points. Pick the one your tool reads first.

| File | Audience | Tools |
|---|---|---|
| [**AGENTS.md**](AGENTS.md) | Universal coding-agent spec | Cursor · Codex · Aider · Antigravity · Jules · Devin · Windsurf · Zed · Warp · opencode · Copilot |
| [**CLAUDE.md**](CLAUDE.md) | Claude Code's auto-loaded memory | Claude Code |
| [**llms.txt**](llms.txt) | LLM-readable summary (llmstxt.org format) | Paste into ChatGPT, Claude, or Gemini to onboard the model |
| [`skills/gflow-cli/SKILL.md`](skills/gflow-cli/SKILL.md) | Claude Code Skill | Symlink into `~/.claude/skills/` |

### Install the plugin (Claude Code)

One step, and you get the `gflow-cli` and `video-production` skills plus the MCP server:

```
/plugin marketplace add ffroliva/gflow-cli
/plugin install gflow@gflow-cli
```

The plugin ships **disabled**. Claude Code starts a plugin's MCP servers automatically once a
plugin is enabled, with no prompt of its own — and this server drives your own Google account,
where Veo video generation bills your credits. So installing it starts nothing, and enabling it
is a deliberate act. Generation, saved TTS voice creation and native video extension/editing can spend credits. For a hard guarantee,
register the server yourself with `gflow mcp run --no-spend`, which never registers the
credit-spending tools at all. See [docs/MCP.md](docs/MCP.md) for the details, including which
revision `/plugin marketplace add` gives you.

Codex users: `codex plugin marketplace add .` then `codex plugin add gflow@gflow-cli`.

Onboard any agent in one line. Paste this into your agent of choice:

> *"Read [AGENTS.md](https://github.com/ffroliva/gflow-cli/blob/main/AGENTS.md) and [docs/INDEX.md](https://github.com/ffroliva/gflow-cli/blob/main/docs/INDEX.md), then help me with my Flow batch."*

## Architecture & current limitations

```text
gflow CLI  →  Provider (interchangeable)  →  Flow (ui_automation) / Mock (tests) / [planned: Official Veo]
                                              ↓
                                      Playwright Chromium (headed — login AND generation, by default)
                                              ↓
                              aisandbox-pa.googleapis.com  (Google's private Flow API)
```

**Current transport:** `ui_automation` drives Flow through a persistent Playwright Chromium profile. It is production-stable and verified end-to-end every release (see the per-release `LIVE_VERIFICATION_*` evidence files).

**Two Flow frontends:** Google is moving accounts from `labs.google` onto `flow.google.com` ([#639](https://github.com/ffroliva/gflow-cli/issues/639)) — same product, different widget toolkit and wire protocol (`batchexecute` instead of `aisandbox-pa`). The migrated driver covers text-to-video, image-to-video from a local start frame, reference-to-video from local files, text-to-image, and image-to-image from local files. Image generation supports Nano Banana 2 / Pro, the four aspect ratios measured on that host (16:9, 4:3, 1:1, 9:16), and counts 1–4; an existing project is required at the transport boundary. UUID/entity references, instructions, Imagen 4, and the rest of the matrix keep the labs driver until ported (`GFLOW_CLI_FLOW_HOST`, see [CONFIGURATION](docs/CONFIGURATION.md#gflow_cli_flow_host)).

**What's blocked:** a pure HTTP transport for video generation. The video upload endpoint returns HTTP 401 under non-Chrome browsers plus a reCAPTCHA mint we cannot reproduce headlessly. Three earlier HTTP strategies (`evaluate_fetch`, `bearer`, `sapisidhash`) live under `src/gflow_cli/api/transports/experimental/` for research, off the production path.

**How you can help:** if you have driven `aisandbox-pa.googleapis.com` from outside a real Chrome session, or you understand Google's anti-bot stack here, please open an issue. A working REST transport would unlock serverless deployments, true horizontal concurrency, and roughly 10x the project's reach. Details: [docs/ARCHITECTURE.md § Headed-browser dependency](docs/ARCHITECTURE.md#headed-browser-dependency--current-limitation).

## Project status

**Alpha.** Image (t2i, i2i, upload, upscale, batch) and video (t2v, i2v, r2v, chain, extend) run end-to-end on `ui_automation`, with a 5-model Veo picker plus `--duration` and `--count`. Beyond single generations: `gflow movie` renders multi-scene manifests, `gflow instructions` manages persistent Agent-Mode brief cards (credits-free), `gflow character` handles reusable subjects, `gflow scene` does credit-free server-side stitching, `--tool` applies prompt-rewriting tools, and an MCP server (`gflow mcp run` stdio / `gflow serve` Streamable HTTP) exposes the core surface to AI agents with a CI-enforced CLI↔MCP parity contract.

Full milestone history lives in [CHANGELOG.md](CHANGELOG.md). Where the project is heading: [ROADMAP.md](ROADMAP.md).

## Support gflow-cli

gflow-cli is built and maintained by one person. Every release is verified against real Google Flow, which spends real AI credits, and breakages get fixed fast because people run it in their pipelines. Sponsorship pays for both.

[![Sponsor $5 one-time](https://img.shields.io/badge/☕_sponsor-$5_one--time-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/ffroliva/sponsorships?frequency=one-time&amount=5)
[![Sponsor $5 a month](https://img.shields.io/badge/💖_sponsor-$5_a_month-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/ffroliva/sponsorships?frequency=monthly&amount=5)

Relying on gflow-cli at work? The monthly company tiers put your logo here, and Silver and above also get priority issues. All tiers and what each one gets: [docs/SPONSORS.md](docs/SPONSORS.md).

Patched gflow-cli in your fork? Please [open an issue](https://github.com/ffroliva/gflow-cli/issues) or a pull request — a fix that lands upstream helps everyone.

### Hall of fame

<!-- sponsors:start -->
No sponsors yet. <a href="https://github.com/sponsors/ffroliva/sponsorships?frequency=one-time&amp;amount=5">Be the first</a> — every public sponsor is listed here.
<!-- sponsors:end -->

## License & legal

[MIT License](LICENSE) © 2026 Flavio Oliva (`ffroliva`). The MIT license covers `gflow-cli`'s code only. It grants no rights to Flow, Veo model output, or any Google service. Google's own terms (Labs Additional Terms and any plan-specific subscription terms) govern your generations. See the [DISCLAIMER](DISCLAIMER.md).

## Acknowledgements

- [`edge-tts`](https://github.com/rany2/edge-tts), design inspiration for community SDKs over private cloud APIs.
- [`googleapis/python-genai`](https://github.com/googleapis/python-genai), the official Veo SDK that a future provider release may alias.
- [Keysight, *Google Labs – Flow AI with Veo3: A Network Traffic Analysis*](https://www.keysight.com/blogs/en/tech/nwvs/2025/08/04/google-flow-ai-har-analysis), an independent capture that helped validate the route patterns.

---

## Stats

[![GitHub stars](https://img.shields.io/github/stars/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/network/members)
[![GitHub watchers](https://img.shields.io/github/watchers/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/watchers)
[![GitHub issues](https://img.shields.io/github/issues/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/pulls)
[![GitHub last commit](https://img.shields.io/github/last-commit/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/commits/main)
[![GitHub repo size](https://img.shields.io/github/repo-size/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli)
[![PyPI downloads](https://static.pepy.tech/badge/gflow-cli/month)](https://pepy.tech/project/gflow-cli)

### Star history

<!-- DO NOT strip `sealed_token` from the URLs below. GitHub restricted the public
     /stargazers endpoint (2026-06-30), so star-history can only build this chart from a
     token-authenticated request. Its per-repo cache expires in <3 days, so a tokenless
     URL renders a "GitHub restricted access to star data" placard — served as HTTP 200,
     which is why nothing catches it. `.github/workflows/star-history-watch.yml` probes
     for exactly that. The token is sealed with star-history's key and grants metadata
     read on a public repo; it is safe in a public README, and they recommend it. -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ffroliva/gflow-cli&type=date&theme=dark&legend=top-left&sealed_token=7kTiE_HExjjY2aT7O-_hMxY_Mf6n-ET17mi_RXcRjCSS5rHSBDMd7xFYCzT_yaXhAXrgF8AGTQc6mny_qfuJc7473KGqb-5U41Dpu-tpZIS1IYl-xVQR9ziGJtL0KWQVyWZU1IoUmLWwo43PhgVTo4MJfmWOvluFJq2zlGxE_iLl9wMRgpwQaiC4ufOK" />
  <img alt="Star history chart for ffroliva/gflow-cli" src="https://api.star-history.com/chart?repos=ffroliva/gflow-cli&type=date&legend=top-left&sealed_token=7kTiE_HExjjY2aT7O-_hMxY_Mf6n-ET17mi_RXcRjCSS5rHSBDMd7xFYCzT_yaXhAXrgF8AGTQc6mny_qfuJc7473KGqb-5U41Dpu-tpZIS1IYl-xVQR9ziGJtL0KWQVyWZU1IoUmLWwo43PhgVTo4MJfmWOvluFJq2zlGxE_iLl9wMRgpwQaiC4ufOK" />
</picture>

If `gflow-cli` saves you time, please ⭐ the repo. It is the cheapest way to support the project.

### Reuse existing images as a Flow character

For free native image-copy creation and name/notes/system preset assignment,
use `gflow character create-from-images` and `gflow character update`.
The same operations are available through the SDK and MCP; deletion requires
explicit confirmation. References need verified local catalog copies in the
selected profile/project. See the [character guide](docs/CHARACTER.md#native-characters-from-existing-images-flow-october-2026)
and [MCP tool reference](docs/MCP.md#native-existing-image-character-tools) for
examples, validation and recovery from partial mutations.

The fork also exposes portable [native MP4 upload and reversible whole-batch archive](docs/self-hosted/NATIVE_MEDIA.md), with per-request consent and safe recovery identities. Live proof for each new adapter is recorded separately.

Image Auto aspect from local references or owned native image UUID dimensions is available in CLI and MCP; see [Auto aspect](docs/AUTO_ASPECT.md) for the approximation policy and reference limits.

Saved speech and permanent individual-media deletion now have source-derived portable adapters. Creation is preset-based TTS rather than cloning; permanent deletion is separate from reversible batch archive. Read [saved voices](docs/self-hosted/VOICES.md) and [native media](docs/self-hosted/NATIVE_MEDIA.md) for controls and final E2E proof limits.

Source-derived native Omni video editing and model discovery are available as draft adapters; [scope and pending live proof](docs/VIDEO_EDIT.md).

Native account [credit balance inspection](docs/NATIVE_CREDITS.md) is source-derived; final live read-only proof remains pending.

Native standalone video continuation uses `video extend-native` with account model
discovery in `video extension-models`. Omni existing-video editing uses
`video edit-native` / `video edit-models`; existing image/audio ingredients use
`video reference-native` / `video reference-models`. These are source-derived
native transports with final E2E acceptance tracked separately. See
[extension](docs/self-hosted/NATIVE_VIDEO_EXTENSION.md),
[editing](docs/VIDEO_EDIT.md), and
[reference video](docs/self-hosted/NATIVE_REFERENCE_VIDEO.md).

Current source contains 40 MCP tools. Native credit and model/catalog reads passed live. One owned synthetic clip's permanent deletion was confirmed by later native reads after transient visibility. Saved TTS remains unaccepted: an initial preview was ambiguous and its preset capitalization was corrected, then one captured corrected request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7). A native browser-token reference-video attempt was Google-rejected. A controlled CapSolver VIDEO_GENERATION trial also solved once and submitted once, but Google rejected it with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), with no retry and zero accepted outputs. Provider-backed acceptance, full feature lifecycle verification and all-three-account operation remain unproven; this is not full useapi parity.

Final measured scope: permanent synthetic upload/deletion passed in 28.91 seconds, preserving original active media. Corrected Charon TTS submitted one captured no0P6 request and received PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), with no accepted audio or binding lifecycle. Extension/edit rendering was not additionally billed after the account's refusals; catalog availability is verified separately.

Native media retrieval: `gflow project get-media` reads fresh owned image/video/audio metadata (audio metadata only); `gflow project download-media` verifies and downloads content without generation or upscaling. See [commands and limits](docs/USAGE.md#fresh-native-media-lookup-and-download).

Character show supports --include-urls --json for fresh confidential native
reference-image/thumbnail detail, mirrored by MCP include_urls. Metadata-only
defaults remain unchanged; unresolved ownership refuses rather than guessing.

Native Google project inventories support bounded multi-page reads:
`gflow project list --source google --all-pages --max-pages 2 --json`.
Direct MCP mirrors `all_pages/max_pages`; self-hosted REST uses
`allPages/maxPages`. A page cap preserves continuation, and pagination
exhaustion does not establish complete account history or deletion.

Native project listing optionally includes observed media/workflow/character/
saved-voice catalogs with `--include-catalogs --max-projects 1`. SDK and direct
MCP use `include_catalogs/max_projects`; REST uses `includeCatalogs/maxProjects`.
Returned counts, unread listed IDs and later-page cursor are separate; complete
account history and absence-based deletion are not implied.

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

Native video promotion: SDK/CLI video upscale-native/upscale-models, direct MCP twins, HTTP explicit operation=promotion. Targets720p/1080p/4k require fresh tier/model/source proof. Paid acceptance remains R12. See [native promotion](docs/self-hosted/NATIVE_VIDEO_PROMOTION.md).

Fresh native image reference budgets: SDK/CLI image reference-models, direct MCP twin, HTTP images/reference/models. Effective=min(advertised,transport), fresh before upload/mint; Lite3 conservative. See [budgets](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/IMAGE_REFERENCE_BUDGETS.md).

Confirmed permanent-delete retries preserve requested deleted IDs, separate newly/already deleted IDs and make zero mutation calls for receipt-backed already-gone batches. Fresh account/project and exact GetMedia NOT_FOUND proof required; arbitrary absent UUIDs refuse. See [native media](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/NATIVE_MEDIA.md#confirmed-deletion-retries-r09).

HTTP native image/video aliases require explicit fresh-owned registration; reads revalidate and removal deletes only the local mapping. Opaque URL-safe prefixes never establish vendor/account ownership; supported HTTP input fields resolve exact registered mappings with fresh proof. SDK/CLI/MCP retain UUID inputs. See [alias API](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-native-imagevideo-aliases).

Bounded native history: SDK list_native_history defaults to one page; existing project-list CLI --include-history/--history-cursor/--history-max-pages/--history-max-media, MCP snake_case and HTTP includeHistory/historyCursor/historyMaxPages/historyMaxMedia enrich Google project discovery. Up to50 pages/1000 media/45seconds; URL-free observations, complete unknown and no absence-based deletion. See [history API](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#bounded-native-account-history).

HTTP character/saved-voice aliases also support explicit scoped registration and fresh detail reads; only local mappings are removed. Supported HTTP generation/operation inputs now resolve exact mappings before queueing; Google resource deletion and character CRUD mutation inputs remain raw. SDK/CLI/MCP UUID inputs remain unchanged. See [resource aliases](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-character-and-saved-voice-aliases).

Native catalog resume accepts SDK/MCP catalog_project_ids, repeat CLI --catalog-project-id and HTTP catalogProjectIds with native catalog inclusion;1–20unique ordered IDs, incompatible account pagination, bounded remaining IDs. REST-only observations also retain empty projects/characters/saved-user voices without URL persistence or ownership/deletion authority. See [catalog resume](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#explicit-native-catalog-resume).

HTTP alias inputs resolve registered image/video/character/saved-voice mappings before account selection and queueing, with fresh same-account/project/type proof and preserved slots. Queued jobs carry canonical UUIDs, not protected URLs. SDK/CLI/MCP raw contracts and presets are unchanged. See [HTTP alias inputs](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#registered-aliases-as-http-inputs).

General HTTP video image aliases now fill the private verified image cache before queueing; raw UUID and public image-read behavior remain unchanged. See the alias-input API for limits and proof status.

HTTP project-list defaults now return generated-history summaries (source=history); media-list defaults now read native Google inventory. Explicit source=local retains managed cache and project source=google retains catalog discovery. SDK/CLI/MCP history adds summary fields without new flags/tools. See [default changes](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/API.md#generated-history-summaries-and-http-defaults). Actual default-summary/media BDD passed65.84seconds with zero generation; final gates passed6746tests; sourceea9cc2c5 is published/deployed with all3 production HTTP200 reads, zero generation; complete history is not claimed.
