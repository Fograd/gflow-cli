Feature: Optional idle native project-access maintenance
  Scenario: A due idle profile schedules only one read across restart
    Given an enabled due profile and an idle durable queue
    When maintenance admission is checked twice across a restart
    Then only one native project-access health job is accepted

  Scenario: Disabled maintenance leaves the queue untouched
    Given an enabled due profile and an idle durable queue
    When the maintenance interval is disabled
    Then no maintenance job is accepted

  Scenario: Accepted generation takes precedence over maintenance
    Given an enabled due profile and an idle durable queue
    When generation already occupies the profile queue
    Then no maintenance job is accepted
