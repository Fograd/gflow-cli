@e2e @e2e_auth
Feature: Native saved voice quota classification preserves submission state
  Scenario: Explicit preview refusal is terminal
    Given a real browser with every native TTS request intercepted
    When Google explicitly refuses the preview with a unique quota reason
    Then one preview returns a terminal quota refusal without a save or replay

  Scenario: Save refusal preserves an accepted preview
    Given a real browser with every native TTS request intercepted
    When the preview is accepted but its metadata save is quota refused
    Then the accepted audio handles remain recoverable and the preview is never replayed
