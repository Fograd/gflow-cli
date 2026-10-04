@e2e @e2e_auth
Feature: Native inventory synchronization can resume without writes
  Scenario: A second bounded call continues the first observed account traversal
    Given an explicit private account for native inventory synchronization
    When two bounded native sync calls share a private checkpoint
    Then committed scope observations persist without Google generation
