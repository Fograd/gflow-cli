@e2e @e2e_image
Feature: Native upscale on the migrated Flow composer
  Scenario: A Pro account receives a native 2K image
    Given an authenticated Pro profile and an existing Flow image
    When the shared client upscales the image to 2K
    Then the result is a valid image with doubled source dimensions

  Scenario: The MCP image upscale twin returns native 2K
    Given an authenticated Pro profile and an existing Flow image
    When the MCP image tool upscales the image to 2K
    Then the result is a valid image with doubled source dimensions

  Scenario: A Pro account cannot request Ultra 4K
    Given an authenticated Pro profile and an existing Flow image
    When the shared client requests 4K
    Then the account tier refusal prevents producing an output file
