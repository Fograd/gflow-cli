@e2e @e2e_auth
Feature: Persistent observed catalogs through explicit REST resume
  Scenario: Repeated owned character catalog resume
    Given a private REST account with an explicit existing owned character
    When the selected project catalog is resumed twice and its observations are merged
    Then repeated fresh reads preserve observed counts without duplicate characters
