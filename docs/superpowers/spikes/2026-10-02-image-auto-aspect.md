# Native image automatic aspect investigation

Date: 2026-10-02. Scope: one owned reference image in a native Flow project, Nano Banana 2, requested square output. No solver tasks or Google image generations were performed. Production source was unchanged.

## Contract

[useapi POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) documents `aspectRatio:auto` only for image-to-image requests with at least one reference. The backend derives aspect from the first reference; multiple references can produce differing orientations. It does not specify a square fallback for text-only requests or an algorithm for mapping arbitrary dimensions to fixed ratios.

[useapi POST videos](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) does not list `auto`. Its video ratios are an independent model-specific contract.

## Observed evidence

- An existing owned image was selected in the target project. The native paused image request contained its reference identifier; only presence was recorded, not the identifier or raw body.
- The envelope contained one output row. Its numeric aspect slot was `1` for the explicitly requested square image. This is evidence about square, not an automatic-aspect sentinel.
- A separate inspection immediately before the submit handler verified that a reference was bound. It observed the current composer button `Nano Banana 2 crop_square x1`.
- Opening the settings chooser failed the expected radiogroup selector with `UiSelectorDriftError`. A bounded scan of button/radio labels did not observe an Auto label. The chooser choices were not successfully discovered, so this does not establish that native Auto is absent.
- The request guard aborted the paused wire inspection. The final UI inspection raised before the native submit handler/click. No generation or solver call occurred.

## Outcome and next step

Automatic aspect handling remains **inconclusive**. The self-hosted image API retains HTTP501 for `aspectRatio:auto` because its native request/UI contract has not been measured. It must not silently substitute square or the nearest supported ratio.

The next investigation should resolve the actual post-reference settings chooser using its observed DOM, then capture an aborted Auto request if the control is present. If local dimension inference is offered instead, name and document that policy separately, use the first numeric reference slot consistently, and expose the resolved explicit ratio. It is not established useapi/native Auto parity.

Evidence consists of private, redacted structural summaries kept by the operator. Raw CAPTCHA tokens, signed media URLs, account IDs and provider keys are excluded from this document.

## Bounded chooser DOM follow-up

A final exclusively leased probe selected the same owned I2I reference and intercepted the submit handler before its click. It located exactly one visible composer button matching the previously observed model/square/count label, clicked that button directly, and scanned visible roles and strictly allowlisted ratio/Auto labels rather than assuming radiogroups. The visible scan counted49buttons,63image-role nodes, one navigation and one separator; it captured no radiogroup/option role and no allowlisted ratio/Auto choice. It then aborted before generation.

This observation does not establish native Auto absence or fixed-only choices. No Auto selector or wire sentinel was measured, so there was no Auto selection or further submit capture. Investigation remains inconclusive and production behavior remains501. No repeated blind selector attempts, solver tasks or image generations followed. The private safe summary is i2i-auto-dom-probe.log; no DOM identifiers, prompts or secret values were recorded.
