@e2e @e2e_audio
Feature: Real native saved voice preview and playback
  Scenario: One authorized short TTS preview becomes an owned playable voice
    Given an explicitly reserved real audio preview
    When one short saved voice is created and its playback is looked up
    Then fresh owned audio bytes decode and no second preview is submitted
