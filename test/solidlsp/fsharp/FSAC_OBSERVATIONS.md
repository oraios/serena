# FsAC 0.81.0 Position Observations (Test Fixtures)

Based on raw `textDocument/documentSymbol` responses captured for the small F# test repo (`Calculator.fs.008100.json`, `Program.fs.008100.json`):

* Coordinates are 0-based; we convert to 1-based for Serena output.
* For symbols with leading `///` doc comments, FsAC anchors both `range` and `selectionRange` on the blank line immediately before the doc comment (not on the doc comment or the identifier).
* `selectionRange` matches `range`; FsAC does not move it to the identifier. We need to re-anchor it in post-processing.
* End lines often stop one line before the closing brace/last line of the construct (e.g., spans stop before the final `}`).
* Multi-line doc comments: the span start is still offset to the blank line above the first `///`.
* Attributes preceding a binding/class are included in the span; doc-comment starts are still offset upward to the preceding blank.

Post-processing implications:
1. Convert to 1-based.
2. Shift start down to the doc comment or identifier.
3. Re-anchor `selectionRange` to the identifier line/column.
4. Extend end to include the closing brace/last line when FsAC stops early.
