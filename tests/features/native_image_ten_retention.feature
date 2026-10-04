@e2e @e2e_auth
Feature: Ten native image inputs survive the current composer
  Scenario: Requested model retains ten ordered native image chips before submission
    Given a selected real image model and ten owned native references
    When its canonical request is intercepted and aborted before Google generation
    Then all ten exact references and their prompt order survive without dispatch
