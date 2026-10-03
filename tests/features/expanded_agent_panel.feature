@e2e @e2e_auth
Feature: Recover the expanded migrated agent composer without submitting
  Scenario: Expanded chat hides the pressed mode chip
    Given an explicitly configured migrated composer recovery probe
    When the expanded chat hides its chip and composer recovery runs
    Then classic settings are visible without any generation request
