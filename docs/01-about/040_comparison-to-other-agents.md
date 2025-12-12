# Comparison with Other Coding Agents

To our knowledge, Serena is the first fully-featured coding agent where the
entire functionality is made available through an MCP server, 
thus not requiring additional API keys or subscriptions if access to an LLM
is already available through an MCP-compatible client.

## Subscription-Based Coding Agents

Many prominent subscription-based coding agents are parts of IDEs like
Windsurf, Cursor and VSCode.
Serena's functionality is similar to Cursor's Agent, Windsurf's Cascade or
VSCode's agent mode.

Serena has the advantage of not requiring a subscription.

More technical differences are:

* Serena navigates and edits code using a language server, so it has a symbolic
  understanding of the code.
  IDE-based tools often use a text search-based or purely text file-based approach, which is often
  less powerful, especially for large codebases.
* Serena is not bound to a specific interface (IDE or CLI).
  Serena's MCP server can be used with any MCP client (including some IDEs).
* Serena is not bound to a specific large language model or API.
* Serena is open-source and has a small codebase, so it can be easily extended
  and modified.

## API-Based Coding Agents

An alternative to subscription-based agents are API-based agents like Claude
Code, Cline, Aider, Roo Code and others, where the usage costs map directly
to the API costs of the underlying LLM.
Some of them (like Cline) can even be included in IDEs as an extension.
They are often very powerful and their main downside are the (potentially very
high) API costs.
Serena itself can be used as an API-based agent (see the [section on Agno](../03-special-guides/custom_agent.md)).

The main difference between Serena and other API-based agents is that Serena can
also be used as an MCP server, thus not requiring
an API key and bypassing the API costs.

## Other MCP-Based Coding Agents

There are other MCP servers designed for coding, like [DesktopCommander](https://github.com/wonderwhy-er/DesktopCommanderMCP) and
[codemcp](https://github.com/ezyang/codemcp).
However, to the best of our knowledge, none of them provide semantic code
retrieval and editing tools; they rely purely on text-based analysis.
It is the integration of language servers and the MCP that makes Serena unique
and so powerful for challenging coding tasks, especially in the context of
larger codebases.