@e2e @e2e_data
Feature: Native characters reuse an existing image without generation credits
  Scenario: An API caller creates, edits and removes its own character
    Given an authenticated character endpoint and a registered native image
    When the API caller creates and edits a uniquely named character
    Then the character retains its image and notes and can be removed while the source remains
