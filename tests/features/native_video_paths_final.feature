@e2e
Feature: Final acceptance of native standalone video paths
  @e2e_video
  Scenario Outline: One explicitly allowed native video generation
    Given a private one-shot native video allowance for "<mode>"
    When the selected native video path submits once using a discovered model
    Then exactly one assigned video decodes and its checkpoint is complete

    Examples:
      | mode      |
      | extension |
      | edit      |
      | reference |

  @e2e_auth
  Scenario: Native reference-video models and credits are read without generation
    Given a private read-only native reference catalog configuration
    When reference model catalogs and native credits are read once
    Then observed native model identities and a nonnegative credit balance are returned

  @e2e_video
  Scenario: One TTS preview is bound and used by one reference video
    Given a private one-shot native audio-reference lifecycle allowance
    When one TTS voice is saved, read and bound to an acknowledged test character
    And the selected native video path submits once using a discovered model
    Then exactly one assigned video decodes and its checkpoint is complete
    And only the acknowledged test voice and character are deleted after video success
