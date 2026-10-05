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

  Scenario: Original video and animated GIF exports support browser downloads
    Given an explicitly configured original-profile video evidence fixture
    When original video and animated GIF are exported with generation blocked
    Then both exports decode and no billable request was forwarded

  Scenario: Fresh owned video cache supports metadata without dimensions
    Given an explicitly configured original-profile video evidence fixture
    When freshly owned video bytes are checked for native caching
    Then the owned cache accepts the actual decoded video dimensions
