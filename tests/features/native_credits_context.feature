@e2e @e2e_auth
Feature: Native credit reads use the page-owned JavaScript context
  Scenario: Patchright sees the same native globals as the Flow application
    Given a real Patchright browser with all credit requests intercepted
    When the SDK reads the native credit balance
    Then one native read returns the observed credit balance without a mint
