# Local video concatenation

The self-hosted service can join downloaded managed videos with FFmpeg. This is a **local equivalent** of useapi's `videos/concatenate`, not Google's server-side scene joining. It spends no Google credits and does not create an asset in the Flow project.

The callable module is `gflow_cli.selfhost.concatenate`:

- `Clip(path: Path, trim_start: float = 0, trim_end: float = 0)` selects a previously resolved managed local video. Trims remove seconds from the respective ends.
- `await probe(path) -> VideoInfo` reads duration, pixel dimensions, sample aspect ratio, and whether audio exists.
- `validate(clips, metadata) -> None` rejects invalid inputs with `ValueError`.
- `await execute(clips, output, timeout_s=300) -> ConcatenateResult` returns the published MP4 path, file byte count, duration, width and height. Processing errors use `RuntimeError`; timeouts use `TimeoutError`.

There must be 2–10 clips. Each trim must be finite, between 0 and 10 seconds inclusive, and the sum of both trims must be less than that clip's duration. Sources must have the same **pixel dimensions** and square pixels. This is stricter than accepting equal aspect ratios at different resolutions: resize such sources explicitly before joining. Width and height must be positive even integers.

The output is re-encoded to H.264, 30 frames per second, and AAC at 48 kHz stereo. Existing audio is preserved and normalised to this format; clips without audio receive silence. Re-encoding may slightly change quality and frame timing. The output writes to a temporary managed path and is published atomically only after FFmpeg succeeds and ffprobe validates the result.

The authenticated caller must resolve media IDs through its registry and enforce input/output path containment. HTTP clients must never supply filesystem paths directly. The module accepts local files only, disables network protocols, invokes subprocesses without a shell, refuses to overwrite a source, and cleans up its own process and temporary output on cancellation or failure. FFmpeg and ffprobe must be installed on the host.

The integration regression generates two synthetic clips locally, removes different amounts from their ends, and verifies resulting duration, image dimensions, clip order, preserved tone audio and inserted silence. It does not use a Google profile or credits.

## Native metadata without dimensions
Native-cache inputs retain fresh account/project/media ownership and bounded MP4
checks. When both width and height are absent, ffprobe measures the downloaded
owned bytes. Partial, invalid or mismatched supplied dimensions still refuse;
local protocol restrictions and matching-dimension join rules remain unchanged.
