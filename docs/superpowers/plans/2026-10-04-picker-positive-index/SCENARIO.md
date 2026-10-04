# Library picker scenarios

1. A single matching library popover resolves at positive index zero and exposes its search input in both engines.
2. An older hidden matching popover remains in the DOM; the newest visible picker is selected.
3. While the current picker is visible, the hidden wait times out rather than claiming commit from the old hidden picker.
4. The current pane's confirm remains visible and clickable; after confirm hides it, the hidden wait succeeds.
5. Unrelated trailing detached menus are excluded by the existing picker marker filter.
6. Zero matching panes produces a lazy nth(0) locator, preserving opening and already-closed hidden-wait behavior.
