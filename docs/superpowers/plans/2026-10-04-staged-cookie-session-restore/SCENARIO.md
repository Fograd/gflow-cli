# Owned staged Session import scenario

Given a fresh validated cookie table containing Session cookies and a newly created private .cookie-staging/candidate-* profile, population accepts the cookies and gracefully closes Chrome. Before fresh identity and selected-project verification reopen that owned profile, configure Chrome session restore through private atomic preferences.

Baseline: actual cold reopen prunes three synthetic Session cookies while preserving the persistent control. Corrected: actual reader retains all original session cookies and unchanged expires_utc0/is_persistent0/has_expires0; no invented expiry. Keep parser input intact.

Refusal cases: original/nonstaged profile, replaced creation inode, nonprivate candidate, symlink Default/Preferences, FIFO/oversized/malformed JSON or non-object session settings; failed atomic replacement preserves old preferences and removes temporary file. Persistent-only imports leave preferences untouched.

Authentication remains a separate fresh server decision: no_session, mismatched actual Google principal and unavailable selected project each reject, clean owned staging and preserve the original profile. Restore preference or cookie presence alone cannot publish or activate an import.

Offline browser isolation is installed at launch (dead proxy + resolver block), then synthetic document fulfillment and every other request abort. Root alone runs one fresh standalone real expected-principal/exact-project proof after release and records safe structural booleans. No paid generation or CAPTCHA solve is part of this feature.
