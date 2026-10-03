@e2e @e2e_auth
Feature: Final native feature acceptance batch
  @e2e_video
  Scenario: Explicit saved TTS voice lifecycle and character binding
    Given a privately configured final native batch with a one-shot TTS allowance
    When one saved voice is created, read, bound to an owned character and deleted
    Then only the acknowledged test voice and character have been removed

  Scenario: Permanent deletion of a newly uploaded synthetic clip
    Given a privately configured final native batch with a free synthetic allowance
    When one synthetic clip is uploaded and permanently deleted by its exact media identity
    Then every original active media identity remains active

  Scenario: Native extension and edit model inventory
    Given a privately configured final native batch with explicit read-only permission
    When native extension and edit model catalogs are read
    Then both model catalogs contain observed model identities


  @e2e_image
  Scenario Outline: Local-reference Auto through public image adapters
    Given a privately configured count-one Auto image allowance for "<surface>"
    When the "<surface>" adapter submits one local-reference Auto image
    Then one image decodes with the derived aspect metadata

    Examples:
      | surface |
      | CLI     |
      | MCP     |
