@e2e @e2e_auth
Feature: Generic video supplied CAPTCHA envelope capture without submission
  Scenario: Capture the current text-to-video envelope and abort before Google dispatch
    Given an explicitly configured authenticated native Flow project
    When a one-output generic video request is intercepted before dispatch
    Then its known RPC project count and CAPTCHA context are verified without forwarding
