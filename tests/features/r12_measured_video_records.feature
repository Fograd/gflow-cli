@e2e @e2e_auth
Feature: Measured current video contracts without generation spending
  Scenario: Current completed video metadata preserves exact owned identities
    Given an explicitly configured original-profile video evidence fixture
    When the owned completed video metadata is read
    Then its generation record preserves the media project and workflow identities

  Scenario: Fast first and last frames use the measured interpolation key
    Given an explicitly configured original-profile frame fixture
    When the two-output frame request is intercepted and aborted
    Then the measured interpolation guard accepts both bound frames and zero submissions forwarded
