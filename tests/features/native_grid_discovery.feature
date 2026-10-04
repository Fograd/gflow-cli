@e2e @e2e_auth
Feature: Discover exact owned references across mounted grid windows
  Scenario: An owned image outside the initial grid window is discovered
    Given an explicitly configured no-submit native grid probe
    When a fresh owned unmounted image is discovered in the current project
    Then its exact token is resolved and grid position is restored without generation

  Scenario: Owned images with repeated captions bind by exact token
    Given an explicitly configured no-submit native grid probe
    When a fresh owned repeated-caption image is hydrated and attached
    Then its exact reference is attached without generation

  Scenario: An older owned image in a large virtualized library is discovered
    Given an explicitly configured no-submit native grid probe
    And an explicitly selected older owned image in a large project
    When a fresh owned unmounted image is discovered in the current project
    Then its exact token is resolved and grid position is restored without generation

  Scenario: An older owned image outside the initial picker window is attached
    Given an explicitly configured no-submit native grid probe
    And an explicitly selected older owned image in a large project
    When the selected older owned image is hydrated and attached
    Then its exact reference is attached without generation
