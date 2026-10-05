@e2e @e2e_image
Feature: R08 original-library image request preparation without generation
  Scenario: Fresh capacities, ordered references and controls stop before submission
    Given an original profile explicitly selected for R08 read only checks
    When its existing images and characters pass current image request preparation
    Then no upload mint solver or generation operation has occurred
