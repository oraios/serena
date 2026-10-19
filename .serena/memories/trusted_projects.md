# Trusted Projects

- `trusted_project_path_patterns` matches project roots, not individual files.
- Trust enables specific features; it is not a sandbox.

Symbolic links:
- In untrusted projects
  - symbolic links are not followed when walking project subtrees
  - explicitly requested targets that resolve to locations outside the project root are rejected
- In trusted projects, links (that aren't ignored) are followed and can redirect to arbitrary locations
- Ignore rules match unresolved paths, not the resolved targets of symbolic links.
- Containment checks: Use `Project.validate_relative_path` in Serena's APIs;
  keep trust validation separate from ignore matching (which must be as fast as possible).

Other restrictions in untrusted projects:
- Do not run `activation_command`.
- Ignore project-level `ls_specific_settings`; global settings still apply.
- Language servers should not run project-local binaries (e.g. `tsserver` will use the version
  managed by Serena instead of a locally provided version in `node_modules`)
