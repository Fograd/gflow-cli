@e2e @e2e_auth
Feature: Native owned audio reference preflight
  Scenario: Existing owned audio builds both final requests without minting
    Given an explicit profile project and existing audio for video reference preflight
    When fresh audio and model data build reference and edit requests at the mint boundary
    Then both requests retain audio slot three and no token or generation is sent
