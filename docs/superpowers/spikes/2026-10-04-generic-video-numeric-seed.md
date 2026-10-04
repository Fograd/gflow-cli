# Generic native video numeric seed investigation

Decision: do not implement numeric seed injection for generic T2V/I2V/first-last/R2V. Current primary Google frontend builders do not bind a numeric random seed to any of these RPCs. Inserting into a null slot would be a guessed schema change.

Evidence (read-only; no Google/provider calls):
- Cached public deployed frontend /tmp/gflow-public-project.js, SHA256 ae8067a7a275b92bd3026bf065643f78a01aab6e686b2322e3290653ab4bc9cf, 6,057,711 bytes.
- Google t7a builder starts at byte offset3665353 and independently constructs all four generic request rows.
- Actual private root abort-only YhhmEf capture was inspected for structural types only. Root object rpc,args; args length3; one request row length5 with types list/string/int/null/list. Its sole top-level numeric field is zero-based index2, value2. Google binds that field3 to setAspectRatio; it is not random seed. Prompt/token/project/IDs were never printed.
- XXa input normalization at3505035 contains model key, aspect, resolution, structured prompt, batch UUID, destination and references. It does not forward a numeric seed.
- All four generic t7a switch branches lack c.seed and numeric _.Kv assignment.
- Only t7a UPSAMPLE_VIDEO has _.Kv(D,4,c.seed), at3668763. This is separate p0UkFb promotion. dZa options normalization at3542758 does not itself set seed, so default UI promotion omits it too.
- _.Kv at256761 uses _.Bb; _.Bb at15693 explicitly labels int32 and applies a|0. This proves a signed32 setter for that separate promotion binding, not a generic video seed slot.
- _.yQ at3657937 returns seed from _.jr; _.jr at196150 generates a UUID string. Those requested-identity seeds must not be confused with model randomness.
- Prompt normalization _.MN at3492778 handles structured text/mentions; no seed binding is hidden in the generic prompt object.

Known generic row field maps (proto field = JSON zero-based index+1):
| RPC/mode | model | aspect | request metadata | other positively assigned fields | numeric random seed |
| YhhmEf/TEXT |2|3|5|prompt1, model-options7, resolution8|unbound|
| eb1hJf/START_FRAME |2|3|6|prompt1, start-image5, model-options9, resolution10|unbound|
| nprQif/START_END_FRAMES |2|3|7|prompt1, start5, end6, model-options9|unbound|
| MZZa6b/REFERENCES |3|4|6|prompt1, images2, audio8, model-options9, characters10, likeness11, resolution12|unbound|

The generic TEXT/I2V/first-last index3 null field (proto4) is unassigned by t7a. Its name/type are not established. R2V index4 (proto5) is likewise unassigned. No numeric duration setter appears in these generic branches; task/model keys choose supported model behavior. A nearby null is not evidence of seed.

Model variance: all current generic model keys pass through the same mode-specific builder, including Veo and reference variants; there is no branch assigning model-specific numeric seed. A fixed signed32 validation range cannot be truthfully attached to generic seed because there is no generic seed binding. The separate promotion int32 setter would justify explicit -2147483648..2147483647 validation only if that operation is separately scoped and tested.

Smallest deliverable: keep the existing explicit unsupported numeric seed response for generic/native generation; document this concrete reason. Reopen only with a primary Google request builder/descriptive schema assigning numeric random seed for the selected RPC, followed by abort-only count1 capture proving exact location and a body-preservation test. Do not silently accept or discard seed.

No production source changed. Public spike: docs/superpowers/spikes/2026-10-04-generic-video-numeric-seed.md.
