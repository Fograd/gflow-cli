@e2e @e2e_auth
Feature: Existing owned image Auto sizing
  Scenario: Read native dimensions without generation
    Given an authenticated profile and an existing owned image for Auto sizing
    When the SDK resolves Auto from the native image metadata
    Then the ratio uses the documented policy and no generation is requested
