# Settings overlay positive-index repair

Root authorized a bounded selector helper repair after proving base.count=1 and nth(0).count=1 but last.count=0 against the same populated settings pane. No profile, auth, transport or wire changes.

- [x] Reproduce against isolated synthetic DOM with real Playwright and Patchright, including one settings pane, trailing unrelated hidden menu and two matching panes.
- [x] After the initial visible group wait, count matching panes and select positive count-1.
- [x] Refuse disappearance through existing selector-drift handling; require the selected newest pane's groups visible.
- [x] Verify affected composer tests, formatting, lint, strict types and whitespace.
- [x] Root's separate no-generation generic T2V abort capture passed (exact RPC/project/count/context; zero forwarded).

All synthetic contexts abort every external request. Root owns the signed native browser and the live verification decision. No generation success is inferred from these tests.

See [scenarios](SCENARIO.md).
