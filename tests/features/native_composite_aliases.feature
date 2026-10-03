@e2e @e2e_auth
Feature: Fresh verified native composite aliases
  Scenario Outline: Register read and locally remove an exact owned alias
    Given an explicit authenticated REST account with an existing owned <kind> fixture
    When an unknown alias is checked and the fixture alias is registered and read
    Then removing only the alias preserves fresh native media access

    Examples:
      | kind  |
      | image |
      | video |
