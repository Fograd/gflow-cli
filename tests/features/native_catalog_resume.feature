@e2e @e2e_auth
Feature: Explicit resume of bounded native project catalogs
  Scenario: Read a pending project catalog without generation
    Given an explicit authenticated native account for catalog resume
    When a capped project inventory is resumed using one pending project identity
    Then the fresh selected catalog is returned with unknown completeness and zero generation
