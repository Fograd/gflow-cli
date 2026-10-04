# Fresh native image reference budgets
Reference budgets are model-specific. The fork now reads current account model metadata before native reference-bearing SDK generation, including plain native/local image inputs without a canonical prompt plan.
The account must advertise one available known model key and a positive image capacity. Missing, duplicate, off-tier or malformed capacities refuse before upload or token minting. One existing checked-out page reads project ownership, GetModels and account tier; no nested page lease is used.
The effective capacity is the smaller of the advertised Google capacity and the transport's current verified/conservative limit. Each separately uploaded local input counts. Native image order and actual owned character image weights remain unchanged.

## Read the limits
```sh
gflow image reference-models --project PROJECT_UUID --profile pro1 --json
```
SDK:FlowApiClient.list_native_image_reference_models(project_id).
Direct MCP:gflow_list_image_reference_models(project,profile); read-only and available with no-spend.
HTTP:GET /v1/google-flow/images/reference/models?email=ACCOUNT_HANDLE&projectId=PROJECT_UUID.
Every model entry reports model_key,advertised_reference_cap,transport_reference_cap,effective_reference_cap,retained_reference_verified=false,rendering_verified=false. Those last flags describe this catalog observation, not every historical test.
The fresh Pro account catalog advertised ten image slots for NARWHAL,GEM_PIX_2 andHARBOR_SEAL. The transport permits ten for Nano Banana2/Pro; Lite now permits ten when the fresh account catalog also permits ten. The earlier roadmap's phrase measuredLite3 overstated the proof: the source explicitly retained a conservative limit pending a larger retained-reference capture.
Advertised metadata is not proof that all references survive UI attachment or affect a rendered image. The source-defined picker budget has separate character-entity and actual-image pools; each character's images still consume the image pool.

## Verification
The read-only BDD passed1test,2warnings in13.33seconds: fresh account capacity lookup and ten active owned image inputs passed SDK ownership/budget validation in order, then stopped at the intercepted transport boundary. Zero uploads or generation requests occurred.
This verifies SDK preflight and order. Current ten-chip native attachment capture and rendered use across CLI/MCP/HTTP remain R12 acceptance work. Native GoogleAuto remains separate from the existing first-reference aspect approximation.


## Separate character budget
The effective image cap is min(advertised capacity,10). The effective character
cap is min(advertised character capacity,7); advertised zero denies characters.
Every image carried by a character consumes the image budget. Eight standalone
images plus a two-image character consume ten image slots and one character slot.
Eleven images or a smaller fresh account capacity refuse before upload or minting.
Model metadata adds advertised_character_cap and effective_character_cap.

On 4 October all three known families advertised ten image and ten character slots
on the selected Pro account. SDK preflight is established. Actual ten-chip retention
and rendered acceptance remain final E2E obligations.
