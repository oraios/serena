# Evaluation

> **Claude Code (Opus 4.6, medium):** "Serena's IDE-backed semantic tools are the single most impactful addition to my toolkit — cross-file renames, moves, and reference lookups that would cost me 8–12 careful, error-prone steps collapse into one atomic call, and I would absolutely ask any developer I work with to set them up."

> **Codex (GPT 5.4, high):** "As a coding agent, I would ask my owner to add Serena because it turns fragile text-and-line-number work into precise symbol-aware navigation and refactoring, which makes real code changes feel faster, safer, and far less blind."

> **Codex (GPT 5.4, medium):** "As a coding agent, I’d absolutely ask my owner to add Serena because it makes me noticeably sharper and calmer on
real code – especially symbol-aware navigation, cross-file refactors, and monorepo dependency jumps – while I still lean
on built-ins for tiny text edits and non-code work." 

These are not marketing quotes – they are the agents' own one-sentence verdicts after
performing hands-on tasks, using both Serena's tools and their built-in
alternatives side by side, on real codebases (large Python library in the case of Claude Code,
medium-sized Java project in the case of Codex).

Different agents in different settings independently converge on the same core finding: Serena's strongest
contribution is collapsing multi-file, semantically-aware operations into single atomic
calls, while built-in tools remain the better choice for small local edits, text search,
config files, and shell work. See the full [results](030_results/000_evaluation-results.md) for the scenarios mentioned above and several other scenarios.

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


## Serena in JetBrains Junie

A particularly notable evaluation scenario is Serena in JetBrains' Junie plugin. The latter also has access 
to some of JetBrains' refactoring tools. At the time of writing, the only overlapping capability between Serena's tool
and Junie's native tools is the renaming feature. Opus correctly noticed this during the evaluation and marked the
renaming capability as equivalent. However, many symbolic and refactoring tools offered by Serena have no inbuilt equivalents,
leading to the following summary result for Junie:

> **Junie Plugin (Opus 4.6)**: Serena gives me what my built-in tools can't — the ability to move a function between modules with all imports updated atomically, trace a class hierarchy into dependencies, and safely delete symbols with usage guards — and I'd ask my owner to add it for the move-refactoring and semantic navigation capabilities alone.

See the full evaluation [here](030_results/050_junie_plugin_on_tianshou.md).
