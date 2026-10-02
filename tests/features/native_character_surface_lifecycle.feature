@e2e @e2e_auth
Feature: Native existing-image characters have matching CLI and MCP surfaces
  Scenario Outline: An adapter copies two images and manages metadata without generation
    Given two owned native images and a logged in character profile
    When the <surface> adapter creates a character with two references and a preset voice
    Then the <surface> adapter can update, read and delete only that character

    Examples:
      | surface |
      | CLI     |
      | MCP     |
