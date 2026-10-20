@e2e @e2e_auth
Feature: Explicit Nano Banana 2.1 selection
  Scenario: Select the advertised model without generating
    Given an explicitly configured native Flow account for Nano Banana 2.1
    When Gflow reads its live image models and selects Nano Banana 2.1
    Then BELUGA is advertised and its settings are applied without generation
