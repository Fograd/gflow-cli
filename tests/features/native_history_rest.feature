@e2e @e2e_auth
Feature: Fresh REST account history and observed synchronization
  Scenario: Bounded history pages and scoped observations are returned together
    Given an explicitly authenticated REST account history configuration
    When two native account history pages are requested through REST
    Then history joins and persistent observation counts are returned without claiming completeness
