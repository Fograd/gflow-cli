@e2e @e2e_data
Feature: Native second character reference
  Scenario: Two existing images become distinct character copies without replacing the portrait
    Given an authenticated profile and two owned existing image media
    When the native character driver copies both images and deletes the owned test character
    Then both copied references were retained and both original images remain active
