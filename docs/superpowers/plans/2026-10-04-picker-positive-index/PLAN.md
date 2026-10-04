# Library picker positive-index repair

Root authorized only the async _picker_pane helper and its four existing call sites after the settings pane negative-index fault was proved. The most recent matching library popover remains the selected pane, including after search retries.

- [x] Reproduce single-picker negative-index emptiness with the actual Patchright engine and isolated HTML.
- [x] Return nth(max(count-1, 0)) and await the helper at opening, grace hidden wait, confirm lookup and final hidden wait.
- [x] Keep marker filtering and existing visible/hidden/confirm semantics.
- [x] Finish affected composer tests and strict gates (187 passed; lint, format, types and whitespace clean).
- [ ] Root's separate native verification, if needed for the live picker flow.

No first-pane substitution, forced click, DOM removal, signed-context access or Google generation. Browser contexts abort every external request.

See [scenarios](SCENARIO.md).
