// This file intentionally contains a semantic error: `undefined_symbol` is not
// defined anywhere, so the Gleam language server reports a diagnostic for it.
pub fn broken() -> Int {
  undefined_symbol
}
