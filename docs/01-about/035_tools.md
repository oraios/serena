# List of Tools

Find the full list of Serena's tools below (output of `<serena> tools list --all`).

Note that in most configurations, only a subset of these tools will be enabled simultaneously (see the section on [configuration](../02-usage/050_configuration) for details).

* `activate_project`: Activates a project based on the project name or path.
* `check_onboarding_performed`: Checks whether project onboarding was already performed.
* `create_text_file`: Creates/overwrites a file in the project directory.
* `delete_lines`: Deletes a range of lines within a file.
* `delete_memory`: Deletes a memory from Serena's project-specific memory store.
* `execute_shell_command`: Executes a shell command.
* `find_file`: Finds files in the given relative paths
* `find_referencing_symbols`: Finds symbols that reference the symbol at the given location (optionally filtered by type).
* `find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (optionally filter
  ed by type).
* `get_current_config`: Prints the current configuration of the agent, including the active and available projects, tools,
  contexts, and modes.
* `get_symbols_overview`: Gets an overview of the top-level symbols defined in a given file.
* `initial_instructions`: Provides instructions on how to use the Serena toolbox.
* `insert_after_symbol`: Inserts content after the end of the definition of a given symbol.
* `insert_at_line`: Inserts content at a given line in a file.
* `insert_before_symbol`: Inserts content before the beginning of the definition of a given symbol.
* `jet_brains_find_referencing_symbols`: Finds symbols that reference the given symbol
* `jet_brains_find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (option
  ally filtered by type).
* `jet_brains_get_symbols_overview`: Retrieves an overview of the top-level symbols within a specified file
* `list_dir`: Lists files and directories in the given directory (optionally with recursion).
* `list_memories`: Lists memories in Serena's project-specific memory store.
* `onboarding`: Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
* `prepare_for_new_conversation`: Provides instructions for preparing for a new conversation (in order to continue with th
  e necessary context).
* `read_file`: Reads a file within the project directory.
* `read_memory`: Reads the memory with the given name from Serena's project-specific memory store.
* `remove_project`: Removes a project from the Serena configuration.
* `rename_symbol`: Renames a symbol throughout the codebase using language server refactoring capabilities.
* `replace_lines`: Replaces a range of lines within a file with new content.
* `replace_content`: Replaces content in a file (optionally using regular expressions).
* `replace_symbol_body`: Replaces the full definition of a symbol.
* `restart_language_server`: Restarts the language server, may be necessary when edits not through Serena happen.
* `search_for_pattern`: Performs a search for a pattern in the project.
* `summarize_changes`: Provides instructions for summarizing the changes made to the codebase.
* `switch_modes`: Activates modes by providing a list of their names
* `think_about_collected_information`: Thinking tool for pondering the completeness of collected information.
* `think_about_task_adherence`: Thinking tool for determining whether the agent is still on track with the current task.
* `think_about_whether_you_are_done`: Thinking tool for determining whether the task is truly completed.
* `write_memory`: Writes a named memory (for future reference) to Serena's project-specific memory store.
