@e2e @e2e_auth
Feature: Single-use supplied native tokens without Google generation
  Scenario: Live project scopes reach the native reference edit and audio boundaries
    Given an explicit native profile and free fixture for supplied token preflight
    When native supplied token scopes reach reference edit checkpoints and audio mint
    Then all supplied token boundaries are reached without Google generation
