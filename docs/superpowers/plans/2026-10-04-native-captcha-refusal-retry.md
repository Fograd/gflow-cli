# Explicit native CAPTCHA refusal retries

Implement only explicit captchaRetry1..10 (default1). Supplied tokens alwaysoneattempt.
Fresh private provider scope and fresh native attempt each time. Retry only typed
WafRejectionError plus active submitted provider terminal rejected. Never retry accepted,
unacknowledged/timeout, network/cancellation, content/auth/throttle, or saved-voice save errors.
Existing native attempt functions recreate requested UUIDs; preserve final refusal.

Scenarios: two confirmed refusals followed by exact acceptance; maximumten refusals;
lateWAF afteracceptance stops; WAF withoutpositive rejection stops; supplied and defaults
stopafterone; cancellation unwinds scope/statistics; allfive native worker wrappers forward
sameproject/action/controls. Root sole livecaller; offline TDD before public controls.
