Feature: Private cookie table validation
  Scenario: A valid table yields private browser input without an authentication claim
    Given a bounded session cookie table
    When the cookie table is parsed
    Then the private browser input contains one cookie
    And the public representation contains neither its value nor a health claim

  Scenario: An ambiguous table is rejected without exposing its cookie value
    Given a duplicate cookie table
    When the cookie table is parsed
    Then validation fails with a safe message
