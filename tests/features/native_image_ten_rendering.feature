@e2e @e2e_image
Feature: Ten native image inputs produce a decoded owned output
  Scenario: Authorized count-one model accepts ten ordered owned reference images
    Given a selected real image model and ten owned native references
    When its validated canonical request is submitted exactly once
    Then all ten ordered references produce one decoded owned image
