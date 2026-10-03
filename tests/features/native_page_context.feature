@e2e @e2e_auth
Feature: Native page-owned RPC execution under Patchright
  Scenario: Fresh native model reads use the authenticated page world without generation
    Given an explicit Patchright native profile and project for a read-only context check
    When the SDK reads fresh native video edit models
    Then available native model metadata is returned without mutation or generation
