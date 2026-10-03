@e2e @e2e_auth
Feature: Native preset audio preflight without generation
  Scenario: Fresh available system preset reaches both generation boundaries
    Given an explicit native profile and project for preset audio preflight
    When the SDK validates positional system preset references for reference and edit video
    Then both token boundaries are reached without minting or generation
