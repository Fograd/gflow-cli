@e2e @e2e_auth
Feature: Fresh existing generated-video lookup
  Scenario: Download an owned generated video with omitted metadata dimensions
    Given an explicitly selected existing generated video
    When its fresh URL and MP4 are retrieved without generation
    Then missing metadata dimensions remain unknown and downloaded dimensions are measured
