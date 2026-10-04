@e2e @e2e_auth
Feature: Fresh verified character and saved voice aliases
  Scenario Outline: Register read and locally remove an exact owned resource alias
    Given an explicit authenticated REST account with an existing owned <kind> resource
    When an unknown resource alias is refused and the owned alias is registered and read
    Then local resource alias removal preserves the original native resource

    Examples:
      | kind      |
      | character |
      | voice     |
