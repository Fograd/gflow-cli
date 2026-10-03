@e2e @e2e_auth
Feature: Bounded native account project traversal
  Scenario: Two project pages preserve continuation without implying completeness
    Given an explicit native account profile for read-only project traversal
    When the native inventory traverses at most two project pages
    Then unique project identities and honest continuation are returned without generation
