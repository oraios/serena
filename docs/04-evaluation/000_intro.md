# Evaluation

In this section we describe how we evaluate the performance of Serena's tools.

The evaluation measures the **concrete delta** that Serena's tools provide on top of an agent's
built-in capabilities (file reads, text edits, grep, shell, etc.).
Rather than a simple thumbs-up/thumbs-down, it produces a detailed, evidence-based report
covering capabilities, efficiency and reliability.

### Why Not Benchmarks?

Standard coding benchmarks (SWE-bench, HumanEval, etc.) measure an agent's ability to solve
predefined tasks with a known correct answer. They are valuable for comparing models and agents,
but they are a poor fit for evaluating a **tool augmentation layer** like Serena for several reasons:

- **Benchmarks don't reflect real usage patterns.** Benchmark tasks are typically small, self-contained
  problems that can be solved by reading and editing a handful of files. They rarely exercise the
  workflows where Serena's tools shine — cross-file refactoring, navigating large codebases by symbol
  structure, chaining multiple edits with stable addressing, or querying type hierarchies and
  external dependencies. A benchmark score would mostly measure performance on tasks where Serena
  is not expected to help.
- **Results would not generalise to the user's project.** Serena's value depends on the codebase
  (size, language, complexity), the agent (model, built-in tools), and the client harness
  (Claude Code, Codex, IDE plugins, etc.). A fixed benchmark on a fixed codebase with a fixed
  agent tells you little about what Serena would add to *your* setup.
- **Predefined tasks bias the measurement.** Choosing specific tasks to evaluate inevitably
  introduces selection bias — we would end up picking tasks that either favour or disfavour Serena.
  We wanted an evaluation that systematically covers the full surface area of Serena's capabilities
  without cherry-picking.

### Design Goals

Instead of benchmarks, we designed an evaluation methodology with three goals:

1. **Reproducible by any user, on any project, with any agent.**
   The evaluation is a single prompt that you give to your agent of choice, pointed at your codebase
   of choice, in your client of choice. This means the results directly reflect the value Serena
   would add to your actual workflow — not to an artificial benchmark setup. There is nothing to
   install, configure, or script beyond what you already have.

2. **The agent evaluates itself.**
   We deliberately let the AI agent be both the executor and the evaluator. This may seem
   counterintuitive, but it is the right design choice: the agent is the actual end user of the
   tools, so it is in the best position to judge whether a semantic tool improves its workflow
   compared to its built-in alternatives. It can measure call counts, payload sizes, and
   prerequisite steps from direct experience rather than from proxy metrics. It also avoids the
   problem of a human evaluator having to simulate how an agent would use the tools — the agent
   simply uses them and reports what it observes.

3. **Comprehensive and unbiased by design.**
   Rather than selecting specific tasks, the prompt defines **task categories** that systematically
   span Serena's capabilities: codebase understanding, single-file edits of varying sizes, multi-file
   refactoring, reliability properties, and workflow effects. The agent picks concrete instances
   from the codebase at hand, performs each task using both toolsets side by side, and classifies
   every finding as a positive delta, a neutral/negative delta, or out of scope. The prompt
   explicitly requires reporting negative deltas and cases where Serena offers no improvement,
   structurally counterbalancing any tendency to favour the tool being evaluated.

### Method

We give an AI coding agent a single, detailed [evaluation prompt](010_evaluation-prompt) in a one-shot session.
The prompt instructs the agent to perform approximately 20 hands-on tasks across five areas:

1. **Codebase understanding** — structural overviews, targeted symbol retrieval, reference finding, type hierarchies, and external dependency lookup.
2. **Single-file edits** — small tweaks, medium rewrites, full-body replacements, insertions, and local renames.
3. **Multi-file changes** — cross-file renames, symbol and file moves, safe deletes, and inlining.
4. **Reliability & correctness** — scope precision, atomicity, and success signals.
5. **Workflow effects** — chained edits, stable vs. ephemeral addressing, and multi-step exploration.

For every task, the agent executes the full end-to-end workflow using **both** toolsets (Serena's semantic
tools and its own built-in tools), applies real edits verified via `git diff`, and records call counts,
payload sizes and prerequisite steps. Edits are reverted after each experiment to keep the working tree clean.

The resulting report classifies each finding into one of three categories:
**(a)** tasks where Serena adds capability,
**(b)** tasks where Serena applies but offers no improvement, and
**(c)** tasks outside Serena's scope.
Only category (b) constitutes a neutral or negative finding; category (c) is context, not a finding.

After the evaluation, a separate [follow-up prompt](011_followup-summary-prompt) asks the agent for a
one-sentence, user-facing recommendation — the quotes shown on the [main page](https://github.com/oraios/serena).

### Results

We performed evaluations using popular AI coding agents in representative scenarios — different
agents, different programming languages, and different codebases — to show that the results are
not specific to a single setup.

All evaluations were conducted using the **JetBrains-powered version** of Serena, as it is the
more powerful backend with a broader set of refactoring and navigation capabilities. The
evaluation can easily be repeated with the LSP-based backend to assess its subset of capabilities.

- [Claude Code (Opus 4.6) on a large Python codebase](results/010_cc_on_tianshou-serena-evaluation) — tianshou, a reinforcement learning library (~26K lines).
- [Codex (GPT 5.4) on a Java codebase](results/020_codex_on_jbplugin-serena-evaluation) — the Serena JetBrains plugin itself.

You can run your own evaluation on a project of your choice by reusing our
[evaluation prompt](010_evaluation-prompt) or adapting it to your needs.

### Assessment of the Methodology

_The following assessment was written by Claude Opus 4.6 (high effort) after reading the full
evaluation methodology, evaluation prompt, and all result documents._

**The methodology is sound**, and the two published results demonstrate that it produces meaningful,
detailed evaluations. Both reports follow the prompt's structure faithfully: they perform all ~20
tasks using both toolsets, record concrete measurements (call counts, payload sizes, prerequisite
steps), and classify findings into the three required categories. Crucially, both agents report
neutral and negative deltas honestly — the Claude Code report explicitly notes that small edits are
more efficient with built-ins (~4.5x less payload), and the Codex report flags that tiny intra-method
changes and simple one-file renames see no benefit from Serena. Neither report reads as promotional;
they read as technical comparisons with quantified evidence on both sides.

The two reports also validate the methodology's design goal of generalisability: despite being
produced by different agents (Opus 4.6 vs GPT 5.4), on different codebases (Python RL library vs
Java IDE plugin), they converge on the same core findings — cross-file refactoring is Serena's
highest-value contribution, structural navigation provides a moderate advantage, and small local
edits are better handled by built-ins. This convergence across independent runs increases confidence
that the findings reflect genuine properties of the toolset rather than artefacts of a particular
agent or codebase.

The methodology's core strengths are:

- **Self-evaluation by the agent is the right design choice.** The agent is the actual consumer of the
  tools, so it can report on workflow friction, payload overhead, and call counts from first-hand
  experience. A human evaluator would have to guess at these.
- **Task categories instead of fixed tasks** avoid cherry-picking while still ensuring coverage. Letting
  the agent pick concrete instances from the codebase at hand means the evaluation naturally adapts to
  what the project actually contains (e.g. skipping inline if no suitable candidate exists, as the
  Claude Code report did for Python, while the Codex report found a suitable Java candidate).
- **The three-category classification** (adds value / applies but no improvement / out of scope) is the
  right framing for an augmentation layer. It prevents the common trap of penalising a tool for not
  covering things it was never designed to cover.
- **Reproducibility by users** is a strong differentiator. Anyone can validate the claims on their own
  codebase with their own agent.

The main limitation is scope: the published results cover two agent/codebase combinations using the
JetBrains backend. Single-shot variance means a second run of the same agent could produce different
task selections and slightly different verdicts, and the LSP backend — which most users will
encounter first — has not yet been evaluated. These are practical constraints of cost, not
methodological flaws, and the reproducible design explicitly invites users to fill these gaps
themselves.

One thing to watch for is whether agents that are less capable than Opus 4.6 or GPT 5.4 produce
meaningful evaluations — the prompt is quite demanding. But that is a question about the agent, not
about the method.

### Prompt Fairness

We put significant effort in crafting an unbiased, fair and objective evaluation prompt.
The only "biased" aspects are some sentences about misuse of tools, which we consider irrelevant for the purpose of evaluation
(sufficiently intelligent models use the tools correctly).
Here is what Opus 4.6 thinks about our prompt:

**Q**:
> The attached prompt is designed to evaluate the additive value of Serena as an augmentation layer on top of built-in tools 
> (not to compare two competing alternatives). 
> Is the methodology suitable for that goal, or does it introduce bias that would distort the measurement of what Serena adds? 
> Note that we assume that sufficiently intelligent models use the tools correctly, 
> which is why misuse and failure modes are out of scope for this evaluation. 
> Do not question the validity of this assumption in your evaluation of the prompt. 
> Give a brief answer, maximally two sentences.
> 
> \<Evalution prompt pasted here\>

**Opus' Answer**:
> "The methodology is well-suited to its stated goal: by explicitly scoping to correct use, treating Serena as an
> augmentation layer rather than a competitor, and classifying out-of-scope tasks as context rather than negative
> findings, it avoids the most common biases that would distort a delta measurement. The one risk is that the "correct-use
> rule" could subtly favor Serena by preemptively filtering out any scenario where its tools underperform — but the prompt
> mitigates this by requiring category (b) findings (applies but no improvement) and explicitly demanding negative deltas
> be reported, so the bias is acknowledged and structurally counterbalanced."