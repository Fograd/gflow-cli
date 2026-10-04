@e2e @e2e_auth
Feature: Read-only image upscale capabilities in a real intercepted browser
  Scenario: Observe enabled disabled missing and ambiguous resolutions without dispatch
    Given an explicitly enabled intercepted Patchright image detail menu
    When the shared capability inspector observes the menu variants
    Then states remain distinct and no generation target is selected
