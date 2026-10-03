# Reference/voice scenarios

Preserve prompts with no reserved markers, emails and unknown @words. Bind only
whole ASCII documented slot tokens; leading-zero/out-of-range reserved indexes
fail, while unrecognized families/suffixes remain literal. The exact token-boundary
policy is a conservative local grammar, not an undocumented backend equivalence.
Missing/null/empty slots fail without browser access. Mixed-case markers use
canonical body slot names. Every repeated span remains ordered but identical
UUID aliases consume one attachment/budget entry. Unmentioned body slots remain
attachments. Unicode surrounding text keeps exact offsets and text.

Character budgets count each distinct verified entity's image references, not
one per entity. Unknown/zero/noninteger counts fail before submit. Video frames
cannot coexist with ingredients; end frame requires start. Quality forbids
ingredients, Veo ingredients require 8s/default 8 and cap 3 images/1 voice with an
image/character prerequisite; Omni R2V cap 7 images/5 voices, V2V cap 5 images/3 voices
with no explicit duration. Actual native caps still constrain public transport.

Bundled voices stay offline and byte-compatible, even without a profile. Google
catalog mode requires an explicit valid project UUID before profile resolution.
SDK checks out one page, parses measured native presets, and checks in on every
outcome. CLI/MCP report safe preset names/descriptions/public samples, source and
unknown completeness. Names/descriptions render literally. No custom voice CRUD,
rendered speech or generation-binding claim follows from listing presets.
