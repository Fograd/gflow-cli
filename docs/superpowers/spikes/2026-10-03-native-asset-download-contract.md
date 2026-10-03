# Fresh native asset URL contract

Read-only investigation on2026-10-03. No generation, upload, archive, restore,
deletion, CAPTCHA solving or paid allowance was used. Private metadata and signed
URLs are retained outside Git in an operator-only directory and files.

One fresh selected-project snapshot supplied positive image/video identity and
kind evidence. Explicit GetMedia (as29s) reads matched the exact media/project/
workflow triples. Neither metadata read dispatched a guarded resource write.

## Public frontend evidence

Public unauthenticated project build poKdDH1IwKU.2018.O, SHA256
ae8067a7a275b92bd3026bf065643f78a01aab6e686b2322e3290653ab4bc9cf.
The older SE3VK6s4aGU.2018.O URL returned404; it was not treated as current.

The _.KI accessor at character998532 uses the exclusive media union and its
exclusive generated/uploaded inner union:

| Type | Variant | Zero-based URL path |
| --- | --- | --- |
| image | generated |6,0,13 |
| image | uploaded |6,1,3 |
| video | generated |7,0,8 |
| video | uploaded |7,4,2 |

The mapper at3523096/3524477 identifies uploaded branches explicitly.
Image MIME accessor _.H0 reads generated6,0,18 or uploaded6,1,6.
Original image download Qpb (4966542) fetches fresh GetMedia, then _.KI and _.H0.
Source video download T0 (approximately4968410) likewise fetches fresh GetMedia
and _.KI; alternate resolutions invoke a separate upsample operation.
Thumbnail URL transformation is separate. Do not mechanically rewrite signed
query URLs with =d or substitute metadata5,10 thumbnails.

## Measured content

Both live samples were uploaded variants. The image URL returned HTTP200,
image/jpeg,233225bytes, a decoded1024x1024JPEG. Metadata5,13 was233225.
The video URL returned HTTP200,video/mp4,8908bytes, decoded H.2641280x1280.
Video byte length was absent; uploaded inner integer fields are not inferred
as byte counts. Public notes contain no media UUIDs, signed URLs or raw payloads.

This proves asset-download fields and matching content for these two samples.
It does not prove byte-for-byte preservation of the upload, universal six-hour
expiry, every generated variant live, or resolution promotion. Source and codec
tests cover generated fields; representative final E2E remains separately owed.


## Saved audio detail fields
The same current public project bundle defines IQa as the audio sample, with
name field1 and performance field2. The KI accessor selects exclusive media
field11/audio field1, then playback field4 with field6 fallback.
The LZa audio projection around byte3554580 uses field5 (speaker field12/first
field1 fallback) for the base preset picker, and field8/performance-field2 fallback
for display description. RN independently treats field1 as display name, so it
must not be guessed as the base preset.
The implementation recognizes base presets only against the known system catalog,
keeps performance distinct from description, and reads dialogue field7.
This is current public-source/codec evidence. The selected project has no saved
user audio fixture; these metadata/playback changes have no new live acceptance.
HTTPS playback comes only from strict owned native responses; it is not an
arbitrary-URL download feature or a universal six-hour lifetime guarantee.
