@e2e @e2e_auth
Feature: Original hosted session identity and cold health reuse
  Scenario: Two cold health checks verify the same original Google account
    Given an explicit original profile for R10 read-only health verification
    When health probing cold opens that profile twice
    Then both checks verify current identity and native project access without renewal
