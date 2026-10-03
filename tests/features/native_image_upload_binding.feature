@e2e @e2e_auth
Feature: Correlate a toolbar image upload before canonical binding
  Scenario: One synthetic image upload binds its acknowledged owned identity
    Given an explicit one-upload no-generation allowance
    When the toolbar uploads a synthetic image and binds its canonical slot
    Then the exact owned image is attached and archived without generation
