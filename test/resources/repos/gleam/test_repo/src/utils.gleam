import gleam/int
import gleam/string

/// Formats a label and integer value into a human-readable string.
pub fn format_output(label: String, value: Int) -> String {
  label <> ": " <> int.to_string(value)
}

/// Checks whether a string is non-empty.
pub fn is_non_empty(s: String) -> Bool {
  !string.is_empty(s)
}
