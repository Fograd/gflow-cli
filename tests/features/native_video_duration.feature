@e2e @e2e_auth
Feature: Native edit source duration
  Scenario: Read an owned source duration without generation
    Given an explicitly configured duration metadata read
    When one owned native video snapshot is read
    Then its default virtual frame end is measured and bounded
