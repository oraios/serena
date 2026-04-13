# Evaluation

> **Claude Code (Opus 4.6):** "Serena's IDE-backed semantic tools are the single most impactful addition to my toolkit — cross-file renames, moves, and reference lookups that would cost me 8–12 careful, error-prone steps collapse into one atomic call, and I would absolutely ask any developer I work with to set them up."

> **Codex (GPT 5.4):** "As a coding agent, I would ask my owner to add Serena because it turns fragile text-and-line-number work into precise symbol-aware navigation and refactoring, which makes real code changes feel faster, safer, and far less blind."

These are not marketing quotes — they are the agents' own one-sentence verdicts after
performing hands-on tasks each, using both Serena's tools and their built-in
alternatives side by side, on real codebases (large Python library in the case of Claude Code,
medium-sized Java project in the case of Codex).

Both agents independently converge on the same core finding: Serena's strongest
contribution is collapsing multi-file, semantically-aware operations into single atomic
calls, while built-in tools remain the better choice for small local edits, text search,
config files, and shell work.

## Approach

We gave each agent a single evaluation prompt and pointed it at a codebase. The agent
then performed a wide variety of tasks across five areas (navigation, small edits, large edits,
cross-file refactoring, and workflow effects), executing each task with both toolsets and
recording call counts, payload sizes, and prerequisite steps. Every finding was classified
as either (a) Serena adds capability, (b) Serena applies but offers no improvement,
or (c) outside Serena's scope — a structure that requires reporting negative and neutral
results, not just positive ones.

The agent evaluates itself. This is deliberate: the agent is the actual user of the tools,
so it can judge workflow improvements from direct experience rather than through proxy
metrics. And because the prompt defines task *categories* rather than fixed tasks, anyone
can rerun the evaluation on their own project with their own agent.
