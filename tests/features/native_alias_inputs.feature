@e2e
Feature: Verified composite image aliases as managed video inputs
  @e2e_auth
  Scenario: A freshly verified native image alias is materialized before queueing
    Given an opted-in existing owned image and a REST server with workers disabled
    When its exact alias is registered and submitted as a video start frame
    Then fresh downloaded image bytes and a canonical scoped job exist without generation

  @e2e_video
  Scenario: One allowed cheapest video uses canonical image and character aliases
    Given an opted-in one-shot video budget and an acknowledged owned character fixture
    When verified image and character aliases plus a preset voice are submitted once
    Then one native video decodes and the alias-input checkpoint is complete
