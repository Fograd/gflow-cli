@e2e @e2e_data
Feature: Native character system preset metadata assignment
  Scenario: Set and change a preset without speech generation
    Given an authenticated profile and two owned existing image media for a preset assignment
    When the native character driver assigns then changes the system preset and deletes the owned character
    Then both presets persisted while metadata and source images were preserved
