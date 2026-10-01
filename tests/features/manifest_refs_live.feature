@e2e @e2e_image
Feature: A run config row generates from an earlier row's image, in place
  `"ref": "batch:N"` makes row N's generated image a reference for another row. The image
  is already in the run's project, so it is referenced where it is (by the handle Flow's
  reply returned), never downloaded and uploaded again, and the catalog records which
  image each generation was made from (#913).

  Scenario: Rows reference earlier rows without any upload, and the lineage is recorded
    Given a run config with row 0 plain, rows 1 and 2 referencing row 0, and row 3 referencing row 1
    When gflow run executes it on the live profile
    Then every row succeeds and saves its image
    And each referencing row attached its parent in place, with no upload
    And the catalog records each referencing row as image-to-image with its parent as input
