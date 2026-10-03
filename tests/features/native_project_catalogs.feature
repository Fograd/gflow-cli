@e2e @e2e_auth
Feature: Observed native catalogs across account projects
  Scenario: One discovered project contributes four typed inventories without generation
    Given an explicit native account profile for read-only catalog aggregation
    When native project listing includes catalogs for at most one project
    Then owned typed catalogs and unread discovered project IDs are returned without generation
