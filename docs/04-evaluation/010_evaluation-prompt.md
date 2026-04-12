# Evaluation Prompt

Use the prompt below to evaluate the added value of Serena's tools against your agent's built-in tools on a project of your choice.
All evaluations that you find in our documentation were created in one-shot sessions, only using this prompt and
then following up with a separate [summary prompt](011_followup-summary-prompt)


# Evaluate Serena's Tools Against Built-Ins

You have access to Serena's coding tools alongside your built-in tools (Read, Edit, Write, Glob, Grep, Bash, etc.). I want a thorough, evidence-based evaluation of **what Serena's tools add on top of the built-ins**, assuming both toolsets are used correctly.

This is an evaluation, not a user guide, and it is not a binary adoption pitch. Your job is to answer: *if a competent user of both toolsets had only the built-ins, what concrete capabilities and efficiency wins would they be missing, and by how much?* A reader who finishes your report should have a clear, specific picture of what Serena adds — in terms of capabilities that weren't available at all, workflows that collapsed from many calls to one, and efficiency multipliers that show up across a session. Not a thumbs-up/thumbs-down, but a sharp description of the delta.

Failure modes from misuse, silent-failure traps, gotcha comparisons, and "be careful of X" warnings are out of scope. They belong in onboarding material for a developer learning the tools, not in a delta analysis of what the tools add.

**Describe the added value sharply, don't hedge.** A "both have their place" or "complementary, not rivals" opener is not a description of added value — it conveys zero information about what a reader would actually gain or lose by adding the tool. If Serena adds substantial capabilities, name them and quantify them. If it adds marginal capabilities, say that and show why. The two toolsets are complementary — that's a given, not the answer. The answer is a specific list of what Serena contributes to a correct-use workflow that built-ins alone cannot provide.

## Ground rules

### Starting conditions

- Start fresh. Do not read project memories, CLAUDE.md shortcuts, or prior notes about the repo. Do not read documentation files either. Explore as if you've never seen it, focusing on code.
- Use git as your safety net — experiment freely. Any edit can be reverted with `git checkout -- <file>` or `git stash`. Run edits for real; don't simulate. A hands-on comparison is worth far more than a thought experiment.
- After each experiment, verify the working tree is clean with `git status --short` before moving on.

### How to compare — correct use only

- **Correct-use rule.** Evaluate each tool on inputs and tasks it was designed for, called the way a competent user would call it. A tool doing exactly what its contract says is not a finding, even if a careless caller could misuse it. Examples of what *not* to report:
- Destructive write tools accepting what you send them — that is the contract of a destructive write, not a silent failure mode.
- Addressing schemes that require you to know what you're addressing — that is how addressing works.
- Tools refusing out-of-scope input (semantic tools on non-code files, single-expression refactorings on multi-branch functions, safe-delete on symbols with usages) — those are correct refusals.
- Mid-session friction that only appears if you mix tool families incorrectly — a caller managing their session properly doesn't hit it.
- Transient glitches may appear after `git checkout --` or other file-system mutations. Wait a moment before continuing after doing such a checkout, and in case of failure, retry once. If it then succeeds, the finding is a non-finding.
- **Know the contract before you call.** Before invoking any tool, have a one-sentence understanding of what it does. If you expect an error or "not applicable," don't make the call.
- **Refactoring semantics are real.** Inlining requires a substitutable function (typically single-expression, no side effects); moving requires a legal target; safe-delete requires no surviving usages. If the repo has no suitable candidate for a given refactoring, report "no suitable candidate in this codebase" and skip it — don't contrive a broken input.

### How to compare — workflow level, not single-call level

- For every task, write out the full end-to-end call chain on each side before declaring a winner. Not just "Serena does it in one call" vs "Grep returns line N" — spell out every call you'd make to reach the goal, including the next step after whichever tool you called first. Many apparent wins and losses evaporate once you include the follow-up.
- Don't score a tool on criteria that only matter in the other toolset's workflow. If you find yourself penalizing Serena for missing a feature (line numbers, text anchors) or penalizing built-ins for missing a feature (name paths, type hierarchy), check whether that feature is actually needed in the tool's own native follow-up. If it's only needed because you're planning to fall back to the other toolset, you're holding the tool to the wrong workflow.
- Ephemeral addressing is a liability. Line numbers and byte offsets go stale the moment a file is edited. Stable addressing (name paths) is an efficiency win, even when the output looks smaller.

### How to measure

- Track observations while you work, not at the end. For every tool call, note: number of calls needed, approximate size of what you sent (including re-sent content), size of what you got back, and any prerequisite reads or follow-up verification. These are the raw material for the final report.
- Separate call count, input payload, output payload, and verification cost as distinct axes. A tool that halves call count but doubles payload may not be a net win.
- When comparing two approaches on the same task, include prerequisite Reads and post-hoc verification Greps in the cost — don't hide them outside the comparison. A cross-file rename via Edit isn't "one Edit call"; it's `grep + read × N + edit × N + verify`.

## Exploration phase — tasks to actually perform

Work through the following. Each item exercises a specific capability under correct use; substitute an equivalent if an item isn't applicable ("no suitable candidate in this codebase" is a valid reason).

### Codebase understanding

1. Get a high-level overview of the repository structure — top-level layout, main packages, entry points.
2. Pick one large source file (300+ lines). Get a structural overview of it. Do it with semantic overview tools and with Glob/Grep/Read. Then write out the concrete next step on each side ("after this overview, to read the body of method X I'd call _____") and compare the pair of calls, not just the overview call. Whichever tool's output most directly feeds its own follow-up wins on workflow terms.
3. Pick a specific method inside a class and retrieve its body without reading the surrounding file.
4. For one non-trivial symbol, find all references across the codebase. Compare recall and precision under the question "who uses this in code?" vs "where is this mentioned anywhere, including docs?" — these are different questions, and each toolset is naturally suited to one of them.
5. For a class, list its subclasses / implementations and its supertypes, including transitively. Compare against what text search would need to do (and whether it can follow an override chain or cross into stub files in one step).
6. For at least one symbol from an external dependency (a third-party library), try to retrieve its definition or signature. Note whether each toolset can do this at all and what infrastructure it requires (env activation, site-packages discovery, etc.).

### Single-file edits — span the full range of edit sizes

Do all three sizes below, not just one. The comparison between content-anchored editing (Edit) and symbol-body replacement is size-dependent: Edit's payload grows with the old+new anchor pair, while symbolic body-replace grows with the full new body. They cross over, and where they cross is the whole point. Only testing small edits hides the crossover.

7a. Small tweak (1–3 lines inside a method). Change an error message or rename a local variable inside a larger method. Do it with `Edit` and with `replace_symbol_body`. Compare payload sent, payload received, and prerequisite reads.

7b. Medium rewrite (replace ~10–30 lines — most of a method body). Rewrite the main logic of a method while keeping its signature. Do it both ways. Note that for Edit you may need a long anchor to keep the old_string unique, and that for symbolic replacement the new body is similar in size to what you'd send for Edit's new_string alone.

7c. Large/whole-body rewrite. Pick a method of 50+ lines and rewrite the entire body. Do it both ways. This is where symbolic body replacement is designed to win: Edit has to send the entire old body as an anchor and the entire new body, while `replace_symbol_body` sends only the new body + a short name path. Measure the ratio.

8. Insert a new function/method at a specific structural location (e.g., "right after this existing method"). Try both the symbolic-insert path and the manual Edit path.
9. Rename a private helper used only within one file. Compare doing it by hand vs. using a semantic rename.

### Multi-file changes

10. Rename a symbol (function, class, or method) used across several files including imports. Compare the semantic path against the built-in equivalent chain. Under correct use, a semantic rename is paired with a short post-rename `Grep` for text-surface references (docstrings, markdown, notebooks) — count that as a complementary step, not a Serena failure.
11. Move a symbol from one module to another, updating imports at all call sites. Use the semantic move tool if available; plan the built-in equivalent honestly (how many Reads, Edits, and import-cleanup decisions would it take?).
12. Delete a symbol safely, checking it has no remaining usages. Compare "search-then-delete" with a safe-delete tool.
13. Inline a small helper into its call sites — only if the codebase contains a function that is legally inlinable (single-expression body, no early returns, no side effects, substitutable at its call sites). If no such candidate exists, report "no suitable candidate" and skip. Do not contrive a broken input.

### Reliability & correctness under correct use

14. Scope precision. Demonstrate that semantic tools address symbols by name path and can target a specific class method, override, or overload that text search would over-match. The point is to show the capability — precision under correct use — not to manufacture a rename that breaks polymorphism through careless targeting.
15. Atomicity. A semantic cross-file refactoring is atomic: either all sites are updated or none. A chain of `Edit` calls is not. You don't have to force a failure — report on what this means for reliability on real failures (disk full, interrupted process, transient permission errors).
16. Success signals. For each completed refactor, note what each tool returns on success. Both toolsets report mechanical success only; semantic intent is always the caller's responsibility to verify with a diff. Note this as a baseline for both sides, not as a weakness of either.

### Workflow effects across multiple edits

17. Chain at least three edits in one file. Report what each toolset requires between edits. Pay particular attention to whether identifiers survive mutation: name paths stay valid across edits in other regions of the file; line numbers and byte offsets don't. This is the single biggest workflow-level efficiency effect.
18. Multi-step exploration across the repo. Note whether intermediate results (overviews, reference lists) remain useful across later edits, or whether they have to be refreshed. Stable output survives a session; ephemeral output does not.

### Things where the comparison shouldn't be interesting

19. Read and understand a non-code file (config, changelog, docs, notebook). Semantic-code tools don't apply — use `Read`. State the applicability boundary once and move on.
20. Search for a free-text pattern across the repo (log string, magic constant, URL). Use `Grep`. Don't call symbolic search on free text.

## Evaluation phase

Write a report structured for progressive disclosure — lead with the strongest insights; a reader should be able to stop at any point and still walk away informed.

**Value-weighting is not optional.** For every contribution you name — in §1, §2, §7, and anywhere else you list what Serena adds — you must estimate *how much it matters in general coding work*, not just whether it's novel. A capability that saves 10 calls but is used once a month is a smaller practical contribution than a capability that saves 1 call but is used every editing session, and a reader needs to be able to tell which kind of contribution each item is. Be explicit about **frequency** (how often does this matter in typical Python coding?) and **value per hit** (when it matters, how much does it save?). Order by the product, not by how impressive the individual feature sounds.

**Every section must end with a one-sentence verdict** (a short paragraph labelled "**Verdict:** ...") that gives the reader the single-sentence takeaway for that section. This applies to every top-level section §1–§9 and to each subsection under §3. The verdict is a recommendation in context — e.g. "use symbolic addressing whenever you expect multiple edits to one file," "every task in this group is a clear Serena win," "built-ins only; this is not a contest." Not a hedge, not a summary — a pointed one-liner a reader can act on.

1. **Headline: what Serena adds.** Open with a sharp description of the delta Serena provides on top of the built-ins — not a thumbs-up/thumbs-down, not a "they're complementary" hedge, but a specific list of what Serena contributes that built-ins alone cannot. Structure it as a short list of *capabilities* (things that become possible) and *efficiency multipliers* (things that get cheaper by how much), **ordered by how much value each contribution actually delivers in general coding work — not by novelty**. For each item, state frequency (how often does this matter?) and value per hit (when it matters, how much?). Group items into high/medium/low value tiers if the gap is large enough that a reader should care about the ordering. A reader stopping after this section should know not only what the added value is but also how much of their daily work it touches. If your opening paragraph could be written about a toolset that adds *nothing*, rewrite it. End with a one-sentence verdict.
2. **Added value, by area (3–6 bullets).** Each bullet answers: *what would a built-ins-only workflow be missing here, and how much would it miss it?* Lead with the areas of largest weighted value — not the most novel capability, but the one whose frequency × value-per-hit product is biggest. Each bullet must include a concrete frequency estimate and a concrete value-per-hit estimate (in calls saved, tokens saved, or correctness improved). Bullets should describe what Serena contributes, not "wins" or "losses" against the built-ins. If you catch yourself writing "Serena wins at X," rewrite as "Serena adds X, which shows up in [frequency] coding work and saves [value]." End with a one-sentence verdict.
3. **Detailed evidence, grouped by capability.** Per-task: what you tried, the full end-to-end call chain on each side (including prerequisite reads and complementary follow-up steps), payloads sent and received. Be specific — "1 call vs ~10, and the Serena call sent ~200 tokens while the Edit equivalent would have sent ~450 after including the prerequisite Read" is useful; "Serena was faster" is not. End each subsection with its own one-sentence verdict in context (e.g. "Verdict (multi-file refactors): every task in this group is a clear Serena win").
4. **Token-efficiency analysis.** Separate from raw call count. Address:
   - Payload asymmetry as a function of edit size. Where's the crossover between content-anchored editing and symbolic body replacement? Show the ratio at small, medium, and large edit sizes.
   - Forced reads: does a tool make you load content into context that you don't actually need?
   - Stable vs ephemeral addressing. Name paths survive edits; line numbers don't. The output-size comparison must account for shelf life, not just raw tokens returned.

   End with a one-sentence verdict on when token economics favor each toolset.
5. **Reliability & correctness analysis** — under correct use. Address:
   - Precision of matching: semantic identifiers vs textual matches, with concrete cases where the question shape determined which tool was the right one.
   - Scope disambiguation across override chains and overloads.
   - Atomicity of multi-file operations, and what it means on real failures.
   - Transitive semantic queries (type hierarchy, reference chains, dependency lookups) that text search cannot approximate in one step.

   End with a one-sentence verdict on where correctness weight favors each toolset.
6. **Workflow effects across a multi-step session.** How do efficiency gaps widen over a session? Do identifiers survive edits? Does intermediate output (overviews, reference lists) stay useful? This is often where the real gap lives — a one-call comparison can miss it. End with a one-sentence verdict.
7. **Capabilities with no built-in equivalent.** What Serena made possible that the built-ins genuinely cannot do, or can only approximate with a much longer workflow. Name each capability individually **and annotate each with how much it matters in general coding work** — a capability that's unique but rarely needed is a smaller contribution than one that's unique and needed constantly. End with a one-sentence verdict.
8. **Where built-ins remain the right default.** Which tasks are still best served by Grep/Read/Edit, and why. Include the non-code-file boundary and the post-rename text sweep explicitly. Estimate what share of daily coding these cases represent — this is what calibrates §1's weighting. End with a one-sentence verdict.
9. **Usage rule for a developer with both toolsets.** A per-task decision rule: given both toolsets installed, which do you reach for and when? This is the practical takeaway, not the headline — the description of added value belongs in §1. End with a one-sentence verdict.

## What I'm looking for

Ground every claim in something you actually measured or observed. If an initial impression turns out to be wrong as you gather more evidence, update the report.

**Pay particular attention to the "what does it add, and how much" question.** The §1 headline is the part a reader will actually remember. Before you write it, ask yourself: if a developer reads only that section, will they know (a) what specific capabilities and efficiency wins Serena contributes, and (b) how much those contributions actually matter in general coding work? A reader should be able to tell the difference between "rare but large" contributions and "common but small" ones without guessing. If the answer is no, rewrite it.

Also pay attention to:

- **Weighted value, not raw novelty.** A capability that saves 10 calls but is used once a month is a smaller practical contribution than one that saves 1 call but shows up every editing session. Your §1 and §2 ordering must reflect frequency × value-per-hit, not how impressive the individual feature sounds. Name both axes explicitly for each contribution.
- **Second-order effects visible only across a session.** Token cost of re-sending content, whether identifiers survive mutation, atomicity on failure, intermediate output staying valid. A one-call comparison misses these; a multi-edit session exposes them. These are often high-frequency contributions that look small per hit.
- **Workflow-level honesty.** Compare the full call chain on each side, not just the first call. Don't let one toolset's vocabulary set the evaluation axes.
- **Capability deltas under correct use.** What does Serena let you do that you genuinely couldn't do — or couldn't do cheaply — with built-ins alone? These are the findings that justify the heaviest weights in §1.

## What I am not looking for

- **Failures from misuse.** Calling a code-semantic tool on a non-code file, inlining an un-inlineable function, renaming without a valid name path, passing a body that drops a branch to `replace_symbol_body` without first reading the current body. These are caller errors, not tool findings.
- **Gotcha hunts and "symmetric failure mode" comparisons.** If you find yourself writing "tool X silently does Y when misused" or "tool A has a loud failure that tool B lacks," stop. You've drifted from evaluation into user guide. A destructive write accepting what you send it is a contract, not a flaw; an addressing scheme that forces you to see what you're addressing is a consequence of addressing, not a safety feature. Report capability and efficiency, not caller-discipline requirements.
- **Mid-session friction from tool mixing.** If a workflow only breaks because you're switching tool families mid-edit on the same file, that's a usage choice, not a tool finding.
- **Transient glitches after `git checkout --` or other file-system mutations.** Retry once; if it then succeeds, don't include it.
- **Hedged or neutral §1 openings.** "Both toolsets have their place" and "they're complementary, not rivals" are information-free openings that could be written about any tool pair. §1 must describe Serena's specific contribution — capabilities and efficiency multipliers — in a way that would not be true of a toolset that adds nothing. If your opening paragraph could be recycled for another tool, rewrite it.
- **Binary adoption pitches.** "Install it" and "don't bother" are also the wrong shape of answer. The question isn't whether to adopt — it's what the added value actually is, and how much of it. A good §1 lets the reader decide for themselves whether the described delta is worth it for their work, by being specific about what the delta is and how often it shows up.
- **Novelty-weighted ordering.** Listing Serena's most exotic capability first because it's the most impressive one misleads a reader about what they'll actually experience. If the most exotic feature is used once a month and a boring one is used every session, the boring one comes first. A contribution's weight is frequency × value-per-hit, not how surprising it is.
- **Unquantified "wins."** "Serena is faster here," "Serena is more reliable," "built-ins are cheaper" are all unhelpful without a quantity attached. Every claim about relative value needs a concrete number or a concrete frequency — calls saved, tokens saved, times per session, share of daily edits. An evaluation without magnitudes is a review, not a measurement.
