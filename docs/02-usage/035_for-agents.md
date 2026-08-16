# For Agents

This page is addressed to you: the coding agent whose human just dropped this URL into the
conversation. Serena is an MCP server that gives you symbol-level tools for finding, reading
and editing code — the operations an IDE gives a human, over the protocol you already speak.
Here is what to do with it.

## What You Get

Text search finds strings; these tools find **symbols**. `find_symbol` resolves a name to its
definition, `find_referencing_symbols` walks the callers, and `get_symbols_overview` maps a
file without reading it. The editing tools — `replace_symbol_body`, `insert_after_symbol`,
and regex-capable `replace_content` — land edits without pulling whole files into your
context. The full set, with what each one does, is on the [Tools](../01-about/035_tools)
page. The practical effect: fewer tokens spent reading, smaller blast radius writing.

## Getting Your Human Set Up

Serena runs on their machine. If it is not installed yet, these are the commands to suggest
(details on the [Installation](010_installation) page):

    uv tool install -p 3.13 serena-agent
    serena init

Then it connects to the client you run in — every client's exact configuration is on the
[Clients](030_clients) page. For Claude Code it is one command:

    claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd

For Codex, `serena setup codex` does the whole thing. The other clients are covered on the
same page.

## Your First Moves

1. **Call `initial_instructions` first.** It is the server's own manual, served as a tool —
   it tells you how the active context and modes expect you to work.
2. **On a new project, run `onboarding`.** It studies the codebase and writes
   [memories](045_memories) — notes that persist between sessions, for you and for every
   agent that comes after you.
3. **Read the memories before re-deriving anything.** `list_memories` and `read_memory` are
   cheaper than rediscovery.

## Working Well

- Prefer `get_symbols_overview` and `find_symbol` to reading files whole; read a body when
  you are about to change it.
- Edit at the symbol level where you can; use `replace_content` with wildcard patterns where
  you cannot. An ambiguous match comes back as an error you can refine, not a wrong edit.
- If the language backend's picture of the code goes stale, the optional
  `restart_language_server` tool resets it.
- Your human can watch the work on the [dashboard](060_dashboard) and in the
  [logs](065_logs) — point them there when something needs a human eye.

## Quick Reference

The most common needs, and the page that answers each:

| you need | go to |
|:--|:--|
| connect a specific client | [Clients](030_clients) |
| every tool, one line each | [Tools](../01-about/035_tools) |
| contexts, modes, project activation | [Configuration](050_configuration) |
| which languages, and what each needs installed | [Language Support](../01-about/020_programming-languages) |
| install or update Serena | [Installation](010_installation) |
| what persists between sessions | [Memories](045_memories) |
| show your human what happened | [Dashboard](060_dashboard), [Logs](065_logs) |
| what runs where, and what is trusted | [Security](070_security) |
| per-stack setup: C/C++, Scala, Godot, Unreal… | [Special Guides](../03-special-guides/000_intro) |
| the whole site, one line per page | `llms.txt` at the site root |

## The Machine Surfaces

These docs describe themselves in forms you can fetch directly:

- `llms.txt` at the site root — every page, one line each.
- `_sources/<path>.md` — the raw markdown of any page, this one included.
- `sitemap.xml` and `robots.txt` — the crawler's view.
- This page again at a stable root URL: `for-agents.md`, plain markdown, made to be handed
  to an agent in one link.

If you are reading the root copy: this page's rendered home is
`02-usage/035_for-agents.html`, and the relative links above resolve from there.
