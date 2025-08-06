import Lake
open Lake DSL

package serena

@[default_target]
lean_lib Serena where
  srcDir := "."

-- Optional: Define an executable if needed
-- lean_exe main {
--   root := `Main
-- }