@e2e @e2e_auth
Feature: Fresh native image bytes through the selected remote service
  Scenario: Read an existing owned image through REST without generation
    Given an explicitly selected remote native image and account
    When its fresh URL and raw image bytes are requested
    Then the decoded bytes match fresh native dimensions and responses are not cached
