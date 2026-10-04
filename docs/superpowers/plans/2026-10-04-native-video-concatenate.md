# Native video inputs for local concatenation

Predict constraints: exact all-input scope/kind preflight before downloads; existing global
cache foreign scope refuses; repeated clip slots preserved, only downloads deduplicated.
Native cache references still require fresh strict ownership; inventory is not authority.
Private contained MP4 bytes/size and FFprobe must validate before queue. No URLs in queue.

Scenarios: exact aliases derive projectdifferentfromaccountdefault; explicit owned rawUUID
cache; mixedalias/project/account refuses before downloads; unknownmapping never stripsUUID;
wrongkind/refusal no job; two clipsretainorder/trims; duplicateclipusesonecachetwoslots;
cachednativefreshproof stillruns; downloadescape/oversize/badMIME/identity/bytecount fail
cleansprivateoutput/nojob; managedlocalMP4 unchanged; actualFFmpeg joinsclips/colors/audio.

Plan: REDHTTP tests and existing localFFmpeg regression; private bounded video cache helper
via existing asset-download worker; concatenate-only server normalizer/preflight; inputsCount
from normalized worker list; focused tests/Ruff/types. Root sole authenticated caller.
