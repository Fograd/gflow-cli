@e2e @e2e_auth
Feature: Native character video editing preflight
  Scenario: Fresh owned source and character pass native model checks without generation
    Given an explicit profile and free synthetic video for character edit preflight
    When the native SDK validates source character and model capacities before minting
    Then preflight reaches the token boundary without generation and only the fixtures are removed
