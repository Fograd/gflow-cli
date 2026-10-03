@e2e @e2e_auth
Feature: Native audio eligibility for video editing
  Scenario: Fresh project audio preflight makes no generation request
    Given an explicit native profile and project for read-only edit audio preflight
    When the fresh project payload is checked for exclusive active owned audio
    Then non-audio is refused and only owned audio passes without generation
