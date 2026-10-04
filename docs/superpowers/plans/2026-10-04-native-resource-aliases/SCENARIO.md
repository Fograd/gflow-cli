# Resource alias scenarios

Register exact owned character/entity/project/count; reject count mismatch,
foreign identity and malformed prefix/suffix. Optional voice workflow must bind
fresh active source=user owned audio; presets/deleted/unresolved playback refuse.
Register user voice only when workflow/project/audio UUID and protected audio
URL match. Identical binding revalidates; immutable conflicts refuse409.

Read uses exact registered scope; explicit foreign account/project refuses403.
Responses expose alias ref/nativeRef under no-store without persisting URLs.
Remove scoped mapping with googleResourceDeleted:false and no Google mutation.
Missing mapping404 is local absence, not Google nonexistence; asset route rejects
resource aliases400. Generation/mutation/reference inputs retain raw contracts.

Current57tests pass; actual character lifecycle/saved-user audio/full gates pending.

Coordinator actual REST BDD:pro1 character1passed,saved-voice1skipped(absent),
2warnings26.26seconds. Zero generation/Google mutation. Unknown alias404, fresh
registration, no-store GET, local removal/raw original read passed. Saved-user
fixture/user permission and final full gates remain open; owned pro1 character fixture cleanup subsequently passed with phase:cleaned,
original character IDs/source image preserved and zero generations. R02 remains unchecked.
