@e2e @e2e_image
Feature: Native seeded images through the self-hosted REST API
  Scenario: Google confirms the requested image seed
    Given an authenticated seeded-image REST endpoint
    When a caller requests two images with seed 12042
    Then both Google image results report the requested seed sequence
