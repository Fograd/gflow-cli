# Native upscale verification on a self-hosted Pro profile

The v0.82.1 image upscale path reached `raise_if_migrated` inside the shared client's token mint before submitting anything. The fork integrates the existing upstream PR #922 rather than implementing another private RPC transport.

## Measured evidence

- The existing Pro profile submitted native 2K through the Flow detail view download menu.
- Flow called `SPrCad` with request arguments `[source_media_uuid, 1, client_context]`; the context contained the owning project UUID.
- The reply contained a base64 JPEG. The saved output was 3,334,707 bytes, with dimensions **2752 × 1536**, from the original **1376 × 768** image. This is exactly twice each source dimension.
- A second spike confirmed the same request fields and output length. The capture is gitignored under `scripts/dev/_spike_out/`; the script is `scripts/dev/spike_selfhost_upscale_wire.py`.
- The source media, account and project identifiers are omitted from these public findings.

## Hardening and regression

The listener now correlates the response to the requested source media, project, and observed 2K numeric resolution. A 4K numeric value has not been measured on this Pro account and is not guessed. Decoding enforces a 50 MiB image base64 cap and strict base64 validation; logs never print the encoded data or raw parsing exception. Video export has a 350 MiB base64 cap, respects the explicit labs host override, and validates IDs before navigating.

`tests/features/selfhost_native_upscale.feature` binds to a real-profile BDD test with three cases: shared-client native2K, MCP native2K, and Pro4K refusal. It preserves the explicitly configured profile home and compares output dimensions to the source image. No new image generation is required by these cases.

## Limits

No Ultra account is available here, so successful 4K output is unverified. No existing video was supplied for the Pro profile, so video1080p, original720p, and animatedGIF exports have offline coverage only. Native2K evidence does not establish full useapi parity.

## HTTP MCP gallery virtualisation regression

After more test images were generated, the same existing source failed via HTTP MCP
with a missing tile error. The incident showed a healthy Flow project and twelve
image DOM nodes. A leased read-only spike measured eight recent media tiles in a
720-pixel viewport and a 3511-pixel virtual scroll container; the older source was
not present in the gallery DOM. Direct navigation to its `/project/.../edit/...`
view rendered the download control correctly.

The image upscale driver now opens the validated detail URL directly, as the video
export driver already does, so gallery size and scroll state no longer determine
whether an existing image can be upscaled. A focused regression failed against the
old gallery lookup and passed after the change.

The authenticated Streamable HTTP MCP endpoint was then exercised through a real
MCP ClientSession: discovery returned eighteen tools including both upscale tools,
and `gflow_upscale_image` completed successfully. The server recorded 3,334,707
bytes for the native 2K output; the corresponding saved JPEG measures
2752 × 1536. This confirms the actual HTTP adapter, in addition to the earlier
direct MCP function and REST verification. No image generation or video credits
were needed for this regression test.
