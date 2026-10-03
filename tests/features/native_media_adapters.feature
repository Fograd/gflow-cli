@e2e @e2e_auth
Feature: Portable owned synthetic native media lifecycle
  Scenario Outline: Explicit synthetic MP4 upload and whole-batch archive
    Given an explicitly authorized "<surface>" media adapter and synthetic owned MP4
    When the "<surface>" adapter uploads and archives only that new fixture
    Then the upload is archived and all original active media remain unchanged

    Examples:
      | surface |
      | sdk     |
      | cli     |
      | mcp     |
      | http    |
