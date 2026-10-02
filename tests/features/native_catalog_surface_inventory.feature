@e2e @e2e_auth
Feature: Native inventory is exposed consistently without local catalog mutation
  Scenario: CLI and MCP report the same scoped native projects and mixed media
    Given a logged in native inventory profile and project
    When CLI and MCP read native project pages and project media
    Then their IDs and mixed media kinds agree with unknown completeness
