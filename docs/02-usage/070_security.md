# Security Considerations

As fundamental abilities for a coding agent, Murena contains tools for executing shell commands and modifying files.
Therefore, if the respective tool calls are not monitored or restricted (and execution takes place in a sensitive environment), 
there is a risk of unintended consequences.

Therefore, to reduce the risk of unintended consequences when using Murena, it is recommended to
  * back up your work regularly (e.g. use a version control system like Git),
  * monitor tool executions carefully (e.g. via your MCP client, provided that it supports it),
  * consider enabling read-only mode for your project (set `read_only: True` in project.yml) if you only want to analyze code without modifying it,
  * restrict the set of allowed tools via the [configuration](050_configuration),
  * use a sandboxed environment for running Murena (e.g. by [using Docker](docker)).
