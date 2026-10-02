@e2e @e2e_image
Feature: Native image CAPTCHA token overrides
  Scenario: A fresh token replaces the page-owned token in an accepted request
    Given a verified Flow profile for image token testing
    When a fresh same-page token overrides the native image request
    Then Google accepts the overridden request and returns an image
