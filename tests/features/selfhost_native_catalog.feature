@e2e @e2e_data
Feature: Native account and project catalogs without generation credits
  Scenario: An authenticated tool reads Google catalogs through the self-hosted API
    Given an authenticated native catalog endpoint
    When the tool reads native projects, characters and system voices
    Then native identities, pagination and voice sources are preserved
