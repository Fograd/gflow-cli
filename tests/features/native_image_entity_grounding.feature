@e2e @e2e_image
Feature: Native image character grounding
  Scenario: One image submit preserves an owned character and first-reference aspect
    Given an authenticated profile and existing owned image references for native grounding
    When one native image request carries verified character and image chunks
    Then one generated image is decoded and the owned character is cleaned up
