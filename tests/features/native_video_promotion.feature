@e2e @e2e_auth
Feature: Native video promotion preflight
  Scenario: Account-native promotion reaches checkpoint without generation
    Given an explicit native account and free video promotion fixture
    When promotion model discovery and a supported target reach the checkpoint
    Then promotion stops before dispatch and only its free fixture is archived
