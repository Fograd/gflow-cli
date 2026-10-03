@e2e @e2e_auth
Feature: Fresh native image reference budgets
  Scenario: Read only native model discovery and ordered owned references
    Given an explicit native account for read only image reference budgets
    When fresh model capacities and owned image references reach the SDK transport boundary
    Then the reference order is preserved without uploads or generation
