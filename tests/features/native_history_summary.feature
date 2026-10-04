@e2e @e2e_auth
Feature: Native inventory defaults and generated project summaries
  Scenario: Default REST inventory reads Google and persists scoped observations
    Given an opted-in owned image and a REST server without generation workers
    When the default project summary and media inventory are read
    Then generated counts and native media are returned with private observations
