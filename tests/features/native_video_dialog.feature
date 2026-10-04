@e2e @e2e_auth
Feature: Native video upload selects the current one-time rights agreement
  Scenario: Positive dialog indexing works with the configured browser engine
    Given an intercepted real browser with the current three-button video rights dialog
    When gflow uploads an explicitly owned synthetic MP4
    Then exactly one upload succeeds and the persistent agreement is untouched
