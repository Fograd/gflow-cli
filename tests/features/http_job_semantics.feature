Feature: Durable local HTTP job semantics
  These scenarios exercise only the local adapter and queue, without Google submissions.

  Scenario: An asynchronous video request has a stable polling identity
    Given an authenticated local adapter with generation workers disabled
    When a caller submits an asynchronous video request
    Then the adapter returns 201 and a matching polling record

  Scenario: A synchronous deadline never creates a second generation
    Given an authenticated local adapter with generation workers disabled
    When a synchronous request expires and its caller switches to async with the same key
    Then the adapter reports 408 followed by 201 for exactly one durable job

  Scenario: An unknown worker outcome remains visible in polling and callbacks
    Given an authenticated local adapter with generation workers disabled
    When a queued job is marked interrupted after a worker stop
    Then polling and the terminal callback have the same nonretryable unknown outcome
