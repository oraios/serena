# Evaluation Prompt

We use the prompt below to evaluate the added value of Serena's tools against the
agent's built-in tools on a given project. 
The evaluations were created in one-shot sessions, only using this
prompt and the follow-up [prompt for summarization](020_summary-prompt)

```
# Evaluate Serena's Tools Against Built-Ins

You have access to Serena's coding tools alongside your built-in tools (Read,
Edit, Write, Glob, Grep, Bash, etc.). I want a thorough, evidence-based
evaluation of **what Serena's tools add on top of the built-ins**, assuming both
toolsets are used correctly.

This is an evaluation, not a user guide, and it is not a binary adoption pitch.
Your job is to answer: *if a competent user of both toolsets had only the
built-ins, what concrete capabilities and efficiency differences would they
experience, and by how much?* A reader who finishes your report should have a
clear, specific picture of what Serena adds — as well as where it provides no
meaningful improvement or introduces tradeoffs — in terms of capabilities,
workflows, and efficiency. Not a thumbs-up/thumbs-down, but a sharp description
of the delta.

Failure modes from misuse, silent-failure traps, gotcha comparisons, and "be
careful of X" warnings are out of scope. They belong in onboarding material for
a developer learning the tools, not in a delta analysis of what the tools add.

**Describe the measured differences clearly and neutrally.** Avoid generic or
non-informative framing such as "both have their place" unless supported by
concrete findings. If Serena adds substantial capabilities, name and quantify
them. If it adds marginal or no capabilities, say that and show why. If there
are regressions or tradeoffs, include them explicitly. The two toolsets are
complementary — that's a given, not the answer. Serena is an augmentation layer,
not a replacement. Do not penalize it for tasks it was not designed to address —
instead, note those tasks as "built-in only" and move on. The evaluation should
measure what Serena adds where it applies, not what it fails to add where it
doesn't.The answer is a specific list of what Serena contributes (or does not
contribute) to a correct-use workflow relative to built-ins.

Write the report to serena-evaluation.md in the repo root.



## Ground rules

### Starting conditions

- Start fresh. Do not read project memories, CLAUDE.md shortcuts, or prior notes
  about the repo. Do not read documentation files either. Explore as if you've
  never seen it, focusing on code.
- Use git as your safety net — experiment freely. Any edit can be reverted with
  `git checkout -- <file>` or `git stash`. Run edits for real; don't simulate. A
  hands-on comparison is worth far more than a thought experiment.
- After each experiment, verify the working tree is clean with
  `git status --short` before moving on.

### How to compare — correct use only

- **Correct-use rule.** Evaluate each tool on inputs and tasks it was designed
  for, called the way a competent user would call it. A tool doing exactly what
  its contract says is not a finding, even if a careless caller could misuse it.
- **Know the contract before you call.** Before invoking any tool, have a
  one-sentence understanding of what it does. If you expect an error or "not
  applicable," don't make the call.
- **Refactoring semantics are real.** Inlining requires a substitutable function
  (typically single-expression, no side effects); moving requires a legal
  target; safe-delete requires no surviving usages. If the repo has no suitable
  candidate for a given refactoring, report "no suitable candidate in this
  codebase" and skip it — don't contrive a broken input.

### How to compare — workflow level, not single-call level

- For every task, write out the full end-to-end call chain on each side before
  drawing conclusions. Include prerequisite reads and follow-up steps.
- Do not evaluate a tool based on criteria that only arise from mixing workflows
  incorrectly.
- Ephemeral addressing is a liability. Line numbers and byte offsets go stale
  after edits; stable addressing (name paths) may reduce rework.

### How to measure

- Track observations during execution. For every tool call, note: number of
  calls, approximate input size, output size, and any prerequisite or
  verification steps.
- Separate call count, input payload, output payload, and verification cost as
  distinct axes.
- Include prerequisite Reads and post-hoc verification steps in comparisons.

When a task falls entirely outside Serena's design scope (e.g., reading config
files, small text edits where Edit already sends minimal payload), classify it
as "not applicable" rather than as a negative delta. A negative delta requires
that Serena targets the task and performs worse, not that a tool designed for
something else is suboptimal when misapplied to it.



## Exploration phase — tasks to actually perform

Work through the following. Each item exercises a specific capability under
correct use; substitute an equivalent if an item isn't applicable.

### Codebase understanding

1. Get a high-level overview of the repository structure — top-level layout,
   main packages, entry points.
2. Pick one large source file (300+ lines). Get a structural overview of it. Do
   it with semantic overview tools and with Glob/Grep/Read. Then write out the
   concrete next step on each side and compare the pair of calls, not just the
   overview call.
3. Pick a specific method inside a class and retrieve its body without reading
   the surrounding file.
4. For one non-trivial symbol, find all references across the codebase. Compare
   recall and precision under the question "who uses this in code?" vs "where is
   this mentioned anywhere, including docs?"
5. For a class, list its subclasses / implementations and its supertypes,
   including transitively. Compare against what text search would need to do.
6. For at least one symbol from an external dependency (a third-party library),
   try to retrieve its definition or signature. Note whether each toolset can do
   this at all and what infrastructure it requires (environment activation,
   site-packages discovery, language-server indexing, etc.).

### Single-file edits — span the full range of edit sizes

7a. Small tweak (1–3 lines inside a method). Change an error message or rename a
local variable inside a larger method. Do it with `Edit` and with symbolic body
replacement. Compare payload sent, payload received, and prerequisite reads.

7b. Medium rewrite (replace ~10–30 lines — most of a method body). Rewrite the
main logic of a method while keeping its signature. Do it both ways.

7c. Large/whole-body rewrite. Pick a method of 50+ lines and rewrite the entire
body. Do it both ways.

8. Insert a new function/method at a specific structural location (for example,
   right after an existing method). Try both the symbolic-insert path and the
   manual Edit path.
9. Rename a private helper used only within one file. Compare doing it by hand
   vs. using a semantic rename.

### Multi-file changes

10. Rename a symbol (function, class, or method) used across several files
    including imports. Compare the semantic path against the built-in equivalent
    chain.
11. Move a symbol from one module to another, updating imports at all call
    sites. Use the semantic move tool if available; plan the built-in equivalent
    honestly.
12. Move a file or package to a different location, updating imports at all call
    sites. Use the semantic move tool if available; plan the built-in equivalent
    honestly.
12. Delete a symbol safely, checking it has no remaining usages. Compare
    search-then-delete with a safe-delete tool.
13. Delete a symbol and propagate the deletion to all call sites. Compare to how
    the built-in equivalent would work.
13. Inline a small helper into its call sites — only if the codebase contains a
    function that is legally inlinable. If no such candidate exists, report "no
    suitable candidate" and skip it.

### Reliability & correctness under correct use

14. Scope precision. Demonstrate that semantic tools address symbols by name
    path and can target a specific class method, override, or overload that text
    search would over-match.
15. Atomicity. A semantic cross-file refactoring is atomic: either all sites are
    updated or none. A chain of `Edit` calls is not.
16. Success signals. For each completed refactor, note what each tool returns on
    success.

### Workflow effects across multiple edits

17. Chain at least three edits in one file. Report what each toolset requires
    between edits.
18. Multi-step exploration across the repo. Note whether intermediate results
    remain useful across later edits or have to be refreshed.

### Things where the comparison shouldn't be interesting

19. Read and understand a non-code file (config, changelog, docs, notebook).
    Semantic-code tools don't apply — use `Read`.
20. Search for a free-text pattern across the repo (log string, magic constant,
    URL). Use `Grep`.



## Evaluation phase

Write a report structured for progressive disclosure.

**Value-weighting is required.** For every contribution or difference you
identify — positive, neutral, or negative — estimate:

- **Frequency:** how often this arises in typical coding work
- **Value per hit:** calls saved, tokens saved, or correctness impact

Order findings by **frequency × value-per-hit**, not novelty.

**Every section must end with a one-sentence verdict** summarizing the practical
takeaway.



### 1. Headline: what Serena changes

Open with a precise description of the delta Serena provides. Distinguish
between three categories: (a) tasks where Serena adds capability, (b) tasks
where Serena applies but offers no improvement, and (c) tasks outside Serena's
scope. Only category (b) constitutes a neutral or negative finding. Category (c)
is context, not a finding.

A reader stopping here should understand both what is gained and what is not.

**Verdict:** (one sentence)



### 2. Added value and differences by area (3–6 bullets)

Each bullet must describe:

- What Serena changes relative to built-ins (positive, neutral, or negative)
- Frequency
- Value per hit

Avoid framing in terms of “wins”; describe concrete differences.

**Verdict:** (one sentence)



### 3. Detailed evidence, grouped by capability

Per task:

- What you attempted
- Full call chain on both sides
- Payloads sent and received

Include cases where:

- Serena is better
- Built-ins are better
- No meaningful difference exists

End each subsection with a verdict.



### 4. Token-efficiency analysis

Address:

- Payload differences across edit sizes
- Forced reads
- Stable vs ephemeral addressing

Include cases where each toolset is more efficient.

**Verdict:** (one sentence)



### 5. Reliability & correctness (under correct use)

Address:

- Precision of matching
- Scope disambiguation
- Atomicity
- Semantic queries vs text search
- External dependency symbol lookup and what setup it depends on

Include both strengths and limitations of each toolset.

**Verdict:** (one sentence)



### 6. Workflow effects across a session

Evaluate multi-step workflows and whether advantages compound or diminish.
Include neutral or negative findings where applicable.

**Verdict:** (one sentence)



### 7. Unique capabilities (if any)

List capabilities that have no practical built-in equivalent. If none exist,
explicitly state that. Annotate each with frequency and impact.

**Verdict:** (one sentence)



### 8. Tasks outside Serena's scope (built-in only)

Identify tasks where built-ins are the natural choice because Serena's tools
don't target them. List these briefly for completeness but do not frame them as
Serena shortcomings — they are outside its scope. Estimate their share of daily
work to contextualize how much of a session Serena's augmentation covers.

**Verdict:** (one sentence)



### 9. Practical usage rule

Provide a decision rule for choosing between toolsets based on task type.

**Verdict:** (one sentence)



## What I'm looking for

- Claims grounded in observed evidence
- Explicit reporting of **positive, neutral, and negative deltas**
- Clear quantification of impact
- Honest workflow-level comparisons



## What I am not looking for

- Misuse-based failure analysis
- Gotcha comparisons
- Neutral statements without evidence
- Binary recommendations
- Novelty-driven ordering
- Unquantified claims
```