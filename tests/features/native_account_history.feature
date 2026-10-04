@e2e @e2e_auth
Feature: Measured read-only native account history pagination
  Scenario: Two fresh account history pages preserve ownership without generation
    Given an explicit private native account profile with at least forty observed workflows
    When the SDK reads two native history pages with a forty-media bound
    Then two disjoint owned pages are returned without private fields or writes
