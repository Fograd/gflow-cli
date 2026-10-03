@e2e @e2e_image
Feature: Canonical image grounding through actual public adapters
  # One public invocation and one returned output per scenario. The native
  # production guard and single-attempt regression cover dispatch ownership;
  # these adapter tests do not independently count network submissions.

  @grounding_cli
  Scenario: CLI canonical references produce one decoded image
    Given an explicitly authorized CLI grounding adapter and owned source images
    When that adapter receives one canonical count-one image request
    Then one output decodes and only the owned character fixture is removed

  @grounding_mcp
  Scenario: Registered MCP canonical references produce one decoded image
    Given an explicitly authorized MCP grounding adapter and owned source images
    When that adapter receives one canonical count-one image request
    Then one output decodes and only the owned character fixture is removed

  @grounding_http
  Scenario: Deployed HTTP canonical references produce one decoded image
    Given an explicitly authorized HTTP grounding adapter and owned source images
    When that adapter receives one canonical count-one image request
    Then one output decodes and only the owned character fixture is removed
