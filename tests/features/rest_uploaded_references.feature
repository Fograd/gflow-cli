@e2e @e2e_image
Feature: Two uploaded image references through the deployed REST worker
  # One public generation invocation, not an independent native wire count.
  Scenario: Uploaded native references stay on their account and produce an image
    Given a private authorized REST reference case with an unused allowance
    When two reference assets and one image request use the selected account
    Then the queued references stay native and one image decodes
