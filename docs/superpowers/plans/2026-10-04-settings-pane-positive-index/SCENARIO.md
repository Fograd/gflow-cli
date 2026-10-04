# Settings pane scenarios

1. One overlay with three radiogroups and eleven radio controls resolves through index zero in both Playwright and Patchright.
2. An unrelated hidden trailing menu is excluded by the existing radiogroup filter.
3. With two settings overlays, the newest matching pane is selected and its groups must be visible.
4. If the pane disappears after the initial group wait, selection refuses instead of emitting a negative index.
5. Ordinary cookie dismissal, trigger click, visible waits and failure diagnostics remain active.
