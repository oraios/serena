# Contributing to Serena

Thank you for your interest in contributing to Serena!

## Scope of Contributions

The following types of contributions can be submitted directly via pull requests:
  * isolated additions which do not change the behaviour of Serena and only extend it along existing lines (e.g., adding support for a new language server)
  * small bug fixes
  * documentation improvements

For other changes, always open an issue first to discuss your ideas with the maintainers and do not submit a PR 
until a solution has been agreed upon.

Fixes to "problems" in the code that are uncovered by AI via theoretical code analysis or by applying components
in a way that does not reflect their actual usage in Serena are not considered valuable contributions.
Problems being fixed must be real problems that have either been observed in practice or that can indeed be expected
to occur in practice.

Do not work on beta features (unless they are trivial bug fixes); instead, provide feedback via issues or discussions.
At present, the Serena REPL is a beta feature.

### Adding Support for a New Language Server

See the corresponding [memory](.serena/memories/adding_new_language_support_guide.md).

## Licensing and Contributor License Agreement (CLA)

Serena is multi-licensed by component (see [LICENSE](LICENSE)):
the Serena application is licensed under GPL-3.0-or-later, while SolidLSP (`src/solidlsp`) is licensed under MIT.

All contributions to this repository require acceptance of our [Contributor License Agreement](CLA.md).
The CLA lets you keep the copyright to your work while granting Jain & Panchenko IT-Berater Partnerschaft (Oraios AI) the rights needed to maintain and
distribute Serena under different terms in the future (including the free community edition and possible
commercial editions).

Acceptance is handled automatically by [CLA assistant](https://cla-assistant.io/):

* When you open your first pull request, the CLA assistant bot comments on it with a link to accept the CLA.
* You accept it once, authenticated with your GitHub account; the acceptance is remembered for all future PRs
  (you will only be asked again if the CLA text changes).
* PRs cannot be merged until the `license/cla` status check passes.

The CLA is required repository-wide for operational simplicity, i.e. also for SolidLSP-only changes.
This does not change SolidLSP's MIT license.

When adding new source files, include the SPDX identifier that matches the component:
`# SPDX-License-Identifier: GPL-3.0-or-later` for Serena application code and
`# SPDX-License-Identifier: MIT` for SolidLSP.

## Submitting Pull Requests

When submitting a PR, ensure a well-defined scope.
Every PR should cover a single logical change or a set of closely related changes.

Before submitting a PR, be sure to document your relevant changes (i.e. new features, fixes) in `CHANGELOG.md`.
Use a concise style and add your change to the appropriate section
("Language Servers", "Tools", "JetBrains", "CLI", "Memories", "Dashboard", "Hooks", "General", "Security").
The change log is for users to understand how the changes affect them; technical details belong in the 
commit message/PR description.
No changelog entry for documentation changes or fixes for problems weren't present in the last release.

If you are using AI to generate your contribution, it is expected that you add value by reviewing it carefully
and/or testing it in practice before submitting it.

Submission limit: No more than 3 PRs per contributor can be open simultaneously. If you try to open additional PRs, 
you will get a permission error (which, unfortunately, does not explain this limit).

## Python Environment Setup

You can install a virtual environment with the required as follows

1. Create a new virtual environment: `uv venv -p 3.13`
2. Activate the environment:
    * On Linux/Unix/macOS or Windows with Git Bash: `source .venv/bin/activate`
    * On Windows outside of Git Bash: `.venv\Scripts\activate.bat` (in cmd/ps) or `source .venv/Scripts/activate` (in git-bash) 
3. Install the required packages with all extras: `uv sync --extra dev`

## Local Installation as Tool

To install Serena from the local source, run

```shell
uv tool install --reinstall -p 3.13 .
```

## Poe Tasks

We use poe to execute development tasks:

- `poe format` - run code auto-formatters
- `poe type-check` - run type checkers

## Testing Tool Executions

The Serena tools (and in fact all Serena code) can be executed without an LLM, and also without
any MCP specifics (though you can use the mcp inspector, if you want).

An example script for running tools is provided in [scripts/demo_run_tools.py](scripts/demo_run_tools.py).