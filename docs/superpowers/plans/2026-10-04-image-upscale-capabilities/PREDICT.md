# Predict: per-owned-image upscale capability reads

## Verdict: CAUTION
Confidence: 7/10. Five personas reviewed independently in two batches because the native agent cap permits four active agents. Architect GO8; security CAUTION8; performance CAUTION7; CLI/MCP UX CAUTION6; Devil's Advocate CAUTION6.

The existing native ownership lookup and UI menu are reused. Discovery exposes observations, never subscription entitlement or permission to submit. Exact detail/menu/target identity, bounds, cleanup and zero-mint/zero-dispatch verification are mandatory. Missing, hidden or ambiguous items remain unknown. Engine-specific selector timeouts become unknown; failure to verify ownership remains an error. No new job type, persistence, cache, provider control or paid fallback is added.

Required mitigations: bounded page checkout and inspection; one menu opening; exact detail URL; unique visible download/menu/target anchors; structural role/icon anchors with invariant2K/4K tokens; private URL handling; selected-engine timeout normalization; mirrors and intercepted real Patchright BDD. Existing paid upscale retains its enabled-item gate and second check after mint.
