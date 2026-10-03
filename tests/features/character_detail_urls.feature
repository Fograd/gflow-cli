@e2e @e2e_auth
Feature: Fresh owned character image detail
  Scenario: Reference preview and thumbnail URL without generation
    Given an explicitly selected logged in character detail project
    When one free copied image character is read with fresh detail URLs
    Then the thumbnail matches the owned reference and the fixture is removed without generation
