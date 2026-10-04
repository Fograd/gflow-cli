@e2e @e2e_auth
Feature: Clearing a native multi-reference prompt clears every chip
  Scenario: Chip-local shortcuts cannot leave stale prompt references
    Given a real composer with ten chips and a chip-local select-all shortcut
    When gflow clears the entire prompt
    Then all chips and prompt text are removed by an editing event
