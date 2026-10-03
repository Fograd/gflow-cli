# Veo five-aspect codec inspection

Status: bounded offline primary-bundle inspection; implementation blocked on a
measured route supporting distinct requested ratios. No browser, generation or
source selector/enum modifications.

The published useapi POST videos contract advertises Veo 16:9, 9:16, 1:1,
4:3 and 3:4. The fork currently exposes two video choices, while its pure API
enum also contains square. That discrepancy alone is insufficient to add wire
values.

The previously captured deployed Google Flow project bundle, SHA-256
`fde0520503cde337170e1314e9904b1da4e279d0fea2f10df7cb417ac448d31b`,
defines five shared presentation ratios. Its video conversion function MXa
collapses them as follows:

| Presentation ratio | Video conversion | Image conversion NXa |
|---|---:|---:|
| 16:9 LANDSCAPE | 2 | 3 |
| 4:3 LANDSCAPE_4_3 | 2 | 5 |
| 1:1 SQUARE | 0 | 1 |
| 3:4 PORTRAIT_3_4 | 1 | 4 |
| 9:16 PORTRAIT | 1 | 2 |

The same bundle's named wire mapping contains only
VIDEO_ASPECT_RATIO_LANDSCAPE and VIDEO_ASPECT_RATIO_PORTRAIT. The image mapping
has distinct four-three/three-four names. Current native composer video controls
also map only landscape/portrait; the legacy video UI refuses square. Thus adding
five CLI/MCP/HTTP choices and copying the image codec would not establish exact
video output ratios and could silently substitute a different ratio.

This does not prove Google lacks the documented feature. A different route or
model-specific request may exist. Next work must locate a distinct video wire
contract or an observed UI request preserving the desired ratio, then add shared
enum/codec, model restrictions and mirrored adapter validation. Do not report
this gap closed or promise a square/4:3/3:4 paid output from this inspection.

## Current deployed bundle confirmation and numerical seeds
The independently captured current project bundle build poKdDH1IwKU.2018.O,
SHA-256 ae8067a7a275b92bd3026bf065643f78a01aab6e686b2322e3290653ab4bc9cf,
still defines MXa at offset3502007 with the same collapse:
LANDSCAPE/LANDSCAPE_4_3 ->2, PORTRAIT/PORTRAIT_3_4 ->1, SQUARE ->0.
Native ingredient/edit adapters accept square where actual model capabilities
and measured source aspect permit; this is separate from the legacy UI choices.
The image NXa enums remain distinct and cannot be copied into video requests.

The current t7a generation builder is3508characters, offsets3665353 through
3668861 (before u7a). Its l(outputIndex) helper puts UUID-derived assignment
seeds into metadata fields5/6. These are output-identity seeds, not numerical
generation seeds. TEXT, REFERENCES, FRAMES, EDIT_VIDEO and EXTEND_VIDEO branches
do not encode c.seed. This inspection supports retaining explicit refusal of
unsupported numerical seed controls on those native adapters.

The one c.seed occurrence belongs to UPSAMPLE_VIDEO at3668482: n5a field4
encodes a numerical promotion seed. Its RPC p0UkFb maps to
VideoFxService.BatchAsyncGenerateVideoUpsampleVideo, and n5a aspect isfield3.
That is a separate native resolution-promotion contract for R07; do not claim
that all Google video operations lack numerical seeds.

R05 bounded discovery is complete with source-backed limits, rather than
invented enums or a successful reproduction claim. A different vendor/legacy
route may support the documented controls; no such current working generation
contract was established. Numerical generation seed and distinct4:3/3:4 output
acceptance remain parity limits. No browser writes or credits were used.
