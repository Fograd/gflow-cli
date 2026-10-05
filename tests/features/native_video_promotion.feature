@e2e @e2e_auth
Feature: Native video promotion preflight
  Scenario: Account-native promotion reaches checkpoint without generation
    Given an explicit native account and free video promotion fixture
    When promotion model discovery and a supported target reach the checkpoint
    Then promotion stops before dispatch and only its free fixture is archived

  Scenario: Existing dimensionless owned video reaches promotion preparation without mint
    Given an explicit existing owned native video promotion source
    When the original video is measured and promotion stops before real token mint
    Then the exact source and target are prepared without generation or source mutation
