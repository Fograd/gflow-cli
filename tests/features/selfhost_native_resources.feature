@e2e @e2e_data
Feature: Native resource operations without generation credits
  Scenario: A synthetic MP4 can be uploaded, listed, and archived natively
    Given an authenticated profile and a self-created one-second video
    When the native driver uploads and archives the video with explicit rights confirmation
    Then the returned media identity is present in the native project and archive acknowledgement
