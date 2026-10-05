@e2e
Feature: Owned Chrome startup preserves the original authenticated profile
  @e2e_auth
  Scenario: Compare ordinary and owned CDP startup without a mutation
    Given an explicitly opted-in original pro3 profile and existing owned media
    When both shared and standalone browsers read the same account and existing media
    Then browser policies and loopback ownership are recorded with no mutation or cookie import
    And each browser exits before the original profile lease can be acquired again

  @e2e_video
  Scenario: One reserved native promotion uses the deployed owned CDP launcher
    Given one explicitly reserved pro3 promotion and a private registered MCP connection
    When the native promotion tool is invoked exactly once without solver or retry controls
    Then one new native 1080p MP4 decodes with preserved source identity
