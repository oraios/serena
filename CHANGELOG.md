# Latest

Changes prior to the next official version change will appear here.

* Serena core:
    * Bugfix in `FindSymbolTool` (a bug fixed in LS)
    * Fix in `ListDirTool`: Do not ignore files with extensions not understood by the language server, only skip ignored directories
      (error introduced in previous version)
    * Merged the two overview tools (for directories and files) into a single one: `GetSymbolsOverviewTool`
    * One-click setup for Cline enabled
    * `SearchForPatternTool` can now (optionally) search in the entire project
    * New tool `RestartLanguageServerTool` for restarting the language server (in case of other sources of editing apart from Serena)
    * Fix `CheckOnboardingPerformedTool`:
        * Tool description was incompatible with project change
        * Returned result was not as useful as it could be (now added list of memories)

* Language Servers:
    * Add further file extensions considered by the language servers for Python (.pyi), JavaScript (.jsx) and TypeScript (.tsx, .jsx)
    * Updated multilspy, adding support for Kotlin, Dart and C/C++ and several improvements.
    

# 2025-04-07

> **Breaking Config Changes**: make sure to set `ignore_all_files_in_gitignore`, remove `ignore_dirs`
>  and (optionally) set `ignore_paths` in your project configs. See [updated config template](myproject.template.yml)

* Serena core:
    * New tool: FindReferencingCodeSnippets
    * Adjusted prompt in CreateTextFileTool to prevent writing partial content (see [here](https://www.reddit.com/r/ClaudeAI/comments/1jpavtm/comment/mloek1x/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button)).
    * FindSymbolTool: allow passing a file for restricting search, not just a directory (Gemini was too dumb to pass directories)
    * Native support for gitignore files for configuring files to be ignored by serena. See also
      in *Language Servers* section below.
    * **Major Feature**: Allow Serena to switch between projects (project activation)
        * Add central Serena configuration in `serena_config.yml`, which 
            * contains the list of available projects
            * allows to configure whether project activation is enabled
            * now contains the GUI logging configuration (project configurations no longer do)
        * Add new tools `activate_project` and `get_active_project`
        * Providing a project configuration file in the launch parameters is now optional
* Logging:
    * Improve error reporting in case of initialization failure: 
      open a new GUI log window showing the error or ensure that the existing log window remains visible for some time
* Language Servers:
    * Fix C# language server initialization issue when the project path contains spaces
    * Native support for gitignore in overview, document-tree and find_references operations.
      This is an **important** addition, since previously things like `venv` and `node_modules` were scanned
      and were likely responsible for slowness of tools and even server crashes (presumably due to OOM errors).
* Agno: 
    * Fix Agno reloading mechanism causing failures when initializing the sqlite memory database #8
    * Fix Serena GUI log window not capturing logs after initialization

# 2025-04-01

Initial public version
