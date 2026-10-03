@e2e @e2e_auth
Feature: Fresh owned native media retrieval
  Scenario: Read and download owned image and video without generation
    Given an explicitly selected logged-in native asset project
    When fresh image and video metadata and content are retrieved
    Then content matches the owned media and no resource write was requested
