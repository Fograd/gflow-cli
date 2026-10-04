Feature: Generic image provider controls retain durable queue boundaries
  Scenario: Explicit provider controls survive the registered queued image call
    Given a synthetic queued image tool with no browser
    When a registered image call requests CapSolver and one total attempt
    Then the image queue codec retains only nonsecret provider controls

  Scenario: Confidential tokens refuse before the image queue
    Given a synthetic queued image tool with no browser
    When a registered image call supplies a confidential token
    Then no confidential image input reaches the durable queue
