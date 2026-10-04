@e2e @e2e_auth
Feature: Migrated login requires a live principal before automatic closure
  Scenario: Stale cookies do not close a server-refused login
    Given a real Flow-origin browser with synthetic migrated cookies
    When the native principal request is refused and the user closes the page
    Then cookie presence alone never completes the login

  Scenario: A Google challenge during post-read settlement does not complete login
    Given a real Flow-origin browser with synthetic migrated cookies
    When a fresh principal is followed by navigation to a Google challenge
    Then cookie presence alone never completes the login
