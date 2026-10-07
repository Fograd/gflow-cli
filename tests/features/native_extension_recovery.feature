@e2e @e2e_auth
Feature: Extension output recovery without generation spending
  Scenario: Retained owned output uses exact polling and validated fresh download
    Given an explicitly configured original pro3 retained video
    When extension recovery polls and downloads with all mutations blocked
    Then the retained MP4 validates and no campaign allowance is consumed
