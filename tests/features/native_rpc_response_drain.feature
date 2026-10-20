@e2e @e2e_auth
Feature: Keep canonical project responses readable across navigation
  Scenario: A fresh project read uses one scoped stream workaround
    Given an explicit authenticated read-only project
    When the SDK reads its authoritative project timeline once
    Then its scoped catalog stream reaches clean EOF and the canonical payload validates
