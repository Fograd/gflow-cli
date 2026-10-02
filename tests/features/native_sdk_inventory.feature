@e2e @e2e_data
Feature: Explicit native SDK inventory snapshots
  Scenario: Read project pages and a known image without inventing completeness
    Given an authenticated profile and an owned existing image project
    When the native SDK reads account project pages and project media
    Then returned identities are distinct and the image kind is observed without signed URLs
