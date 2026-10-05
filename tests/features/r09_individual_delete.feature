@e2e @e2e_auth
Feature: R09 individual deletion compatibility
  Scenario: Invocation-owned image and video deletion with canonical repeats
    Given an explicitly authorised R09 image and video fixture allowance
    When SDK first deletion and CLI mixed deletion use only acknowledged fixture IDs
    Then exact gone evidence and receipts allow zero-write repeats and originals survive
