@e2e @e2e_auth
Feature: Restored browser tabs stay bounded while the saved login is reused
  Scenario: Two cold browser opens retain identity without accumulating tabs
    Given an explicit authenticated profile for restored page pool checks
    When the Flow client cold opens that profile twice
    Then both opens keep exactly the configured page pool and the current account
