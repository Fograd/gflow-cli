@e2e @e2e_auth
Feature: Confirmed native deletion retries
  Scenario: Owned synthetic batch and mixed repeat deletion
    Given an explicitly authorized private synthetic delete retry campaign
    When two owned uploads are deleted then retried and mixed with one new owned upload
    Then confirmed gone ids cause no replay and original media remains
