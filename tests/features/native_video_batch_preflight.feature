@e2e @e2e_auth
Feature: Current native generic video batch request proof without spending
  Scenario: Four requested outputs bind to one exact intercepted request
    Given an explicitly configured authenticated native batch project
    When four generic video outputs are prepared and the exact request is aborted
    Then four distinct assigned output identities were observed and zero submissions forwarded
