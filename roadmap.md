# Roadmap

This document gives an overview of the ongoing and future development of Murena.
If you have a proposal or want to discuss something, feel free to open a discussion
on Github. For a summary of the past development, see the [changelog](/CHANGELOG.md).

Want to see us reach our goals faster? You can help out with an issue, start a discussion, or 
inform us about funding opportunities so that we can devote more time to the project.

## Overall Goals

Murena has the potential to be the go-to tool for most LLM coding tasks, since it is 
unique in its ability to be used as MCP Server in any kind of environment
while still being a capable agent. We want to achieve the following goals in terms of functionality:

1. Top performance (comparable to API-based coding agents) when used through official (free) clients like Claude Desktop.
1. Lowering API costs and potentially improving performance of coding clients (Claude Code, Codex, Cline, Roo, Cursor/Windsurf/VSCode etc).
1. Transparency and simplicity of use. Achieved through the dashboard/logging GUI.
1. Integrations with major frameworks that don't accept MCP. Usable as a library.

Apart from the functional goals, we have the goal of having great code design, so that Murena can be viewed
as a reference for how to implement MCP Servers. Such projects are an emerging technology, and
best practices are yet to be determined. We will share our experiences in [lessons learned](/lessons_learned.md).


## Immediate/Ongoing

- Support for projects using multiple programming languages.
- Evaluate whether `ReplaceLinesTool` can be removed in favor of a more reliable and performant editing approach.
- Generally experiment with various approaches to editing tools
- Manual evaluation on selected tasks from SWE-verified
- Manual evaluation of cost-lowering and performance when used within popular non-MCP agents
- Improvements in prompts, in particular giving examples and extending modes and contexts

## Upcoming

- Publishing Murena as a package that can also be used as library
- Use linting and type-hierarchy from the LSP in tools
- Tools for refactoring (rename, move) - speculative, maybe won't do this.
- Tracking edits and rolling them back with the dashboard
- Improve configurability and safety of shell tool. Maybe autogeneration of tools from a list of commands and descriptions.
- Transparent comparison with DesktopCommander and ...
- Automatic evaluation using OpenHands, submission to SWE-Bench
- Evaluation whether incorporating other MCPs increases performance or usability (memory bank is a candidate)
- More documentation and best practices

## Stretch

- Allow for sandboxing and parallel instances of Murena, maybe use openhands or codex for that
- Incorporate a verifier model or generally a second model (maybe for applying edits) as a tool.
- Building on the above, allow for the second model itself to be reachable through an MCP server, so it can be used for free
- Tracking edits performed with shell tools

## Beyond Murena

The technologies and approaches taken in Murena can be used for various research and service ideas. Some thought that we had are:

- PR and issue assistant working with GitHub, similar to how [OpenHands](https://github.com/All-Hands-AI/OpenHands) 
  and [qodo](https://github.com/qodo-ai/pr-agent) operate. Should be callable through @murena
- Tuning a coding LLM with Murena's tools with RL on one-shot tasks. We would need compute-funding for that
- Develop a web app to quantitatively compare the performance of various agents by scraping PRs and manually crafted metadata.
  The main metric for coding agents should be *developer experience*, and that is hard to grasp and is poorly correlated with
  performance on current benchmarks.