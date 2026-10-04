Feature: Resumable native inventory observations
  Scenario: A discovered project remains pending when the read budget ends
    Given an account page with one observed project and a later page cursor
    When one synchronization read is allowed
    Then the project catalog remains pending with unknown completeness

  Scenario: Later absence does not remove previously observed media
    Given previously synchronized native project media
    When a fresh traversal returns no projects or history
    Then the observed media remains with unknown completeness
