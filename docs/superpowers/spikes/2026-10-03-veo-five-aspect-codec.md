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
