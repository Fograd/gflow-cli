@e2e @e2e_image
Feature: Self-hosted Flow REST image workflow
  Scenario: Tools can generate, reference and natively upscale an image
    Given an authenticated self-hosted Flow REST endpoint
    When a tool generates an image through HTTP
    And uploads the image and generates a referenced variation
    And requests native 2K upscaling through HTTP
    Then the upscale has twice the source width and height
