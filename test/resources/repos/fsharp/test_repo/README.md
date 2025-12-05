F# test repo fixtures.

Checked-in raw FsAC outputs (FsAC 0.81.0):
- `Calculator.fs.008100.json`
- `Program.fs.008100.json`

If FsAC behavior changes, regenerate these by pointing a small capture script or manual LSP request at the two files and replace the JSONs. Keep the fixture minimal; add files only when a specific behavior needs coverage.
