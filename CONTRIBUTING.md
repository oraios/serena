# Contributing to Murena


Murena is under active development. We are just discovering what it can do and where the limitations lie.


## Scope of Contributions

The following types of contributions can be submitted directly via pull requests:
  * isolated additions which do not change the behaviour of Serena and only extend it along existing lines (e.g., adding support for a new language server)
  * small bug fixes
  * documentation improvements

For other changes, please open an issue first to discuss your ideas with the maintainers.

## Developer Environment Setup

You can have a local setup via `uv` or a docker interpreter-based setup. 
The repository is also configured to seamlessly work within a GitHub Codespace. See the instructions
for the various setup scenarios below.

Independently of how the setup was done, the virtual environment can be 
created and activated via `uv` (see below), and the various tasks like formatting, testing, and documentation building
can be executed using `poe`. For example, `poe format` will format the code, including the 
notebooks. Just run `poe` to see the available commands.

### Python (uv) setup

You can install a virtual environment with the required as follows

1. Create a new virtual environment: `uv venv`
2. Activate the environment:
    * On Linux/Unix/macOS or Windows with Git Bash: `source .venv/bin/activate`
    * On Windows outside of Git Bash: `.venv\Scripts\activate.bat` (in cmd/ps) or `source .venv/Scripts/activate` (in git-bash) 
3. Install the required packages with all extras: `uv pip install --all-extras -r pyproject.toml -e .`

## Running Tools Locally

The Murena tools (and in fact all Murena code) can be executed without an LLM, and also without
any MCP specifics (though you can use the mcp inspector, if you want).

An example script for running tools is provided in [scripts/demo_run_tools.py](scripts/demo_run_tools.py).

## Adding a New Supported Language

See the corresponding [memory](.murena/memories/adding_new_language_support_guide.md).