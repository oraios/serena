# Evaluation by Opus 4.6 in Claude Code

## Final Recommendation

The recommendation is created with the [follow-up summary prompt](../011_followup-summary-prompt), everything else was created in one shot from the
[evaluation prompt](../010_evaluation-prompt).

> "If I could ask my owner for one upgrade to my coding toolkit, it would be Serena — its symbolic addressing eliminated the constant re-reading
that quietly eats my context on multi-edit sessions, its atomic cross-file refactorings collapsed 10-call manual workflows into one, and after a
rigorous hands-on evaluation I can say that while built-in tools remain the right choice for small edits and text searches, Serena fills the exact
gaps that make me feel clumsy without it."


Ground-truth hands-on evaluation run on `tianshou` (Python, ~26 kLOC under `tianshou/`), focused on what Serena's tools add on top of `Read/Edit/Write/Glob/Grep` under correct use. Every measurement below comes from an actual tool call on this repo, not a thought experiment; edits were applied and reverted via `git checkout --` between experiments.

---

## §1. Headline — what Serena adds

On a typical Python editing session, Serena contributes four things built-ins cannot reproduce cheaply or at all. Ranked by **frequency × value-per-hit**, highest first:

**Tier A — touches almost every editing session**

1. **Stable name-path addressing that survives intermediate edits.** Every Serena editing and querying tool is addressed by `ClassName/method_name`, which remains valid after inserts, deletes, and rewrites elsewhere in the same file. Grep/Read/Edit chain through line numbers or text anchors, both of which drift. **Frequency: every multi-edit session, which is most of them.** **Value per hit: saves one Read + one re-grep per subsequent edit in the same file (~400–800 bytes of re-sent content each time).** This is the quietest contribution and probably the largest in aggregate.

2. **Payload asymmetry on medium-and-larger body rewrites.** `replace_symbol_body` sends `name_path + new_body`, while `Edit` sends `old_body + new_body`. Measured crossover is around 10–15 lines: below that, Edit's tiny anchor wins 5–10× on payload; above that, Serena wins ~2× at 20 lines and ~2.3× at 66 lines, and the gap keeps widening with body size. **Frequency: once per session you rewrite a non-trivial method body.** **Value per hit: 50% payload reduction on medium rewrites, climbing toward ~60% on large ones, plus no need for a prior Read to capture the exact anchor.**

**Tier B — rare per session but very high value when it fires**

3. **Single-call cross-file refactorings with atomicity and automatic import cleanup.** `rename`, `move`, and `safe_delete` each collapse an 8–12-call manual workflow (grep → read-all-callers → edit each → verify → hand-clean unused imports) into one call, atomically. **Frequency: 0–3 times per session, depending on task type — zero on many days, constant on refactoring days.** **Value per hit: 5–10× call reduction plus correctness improvements that manual chains drop (I observed `move` auto-remove a `Categorical` import from the source file that a human refactorer would easily miss).**

4. **Semantic navigation into third-party dependency source.** `find_symbol(search_deps=True)` / `find_declaration` resolves a type from its use site straight into `site-packages` or stub files, returning the full class body in one call. Built-ins would require: (a) reading the file to find the import, (b) locating the venv, (c) guessing the module path, (d) reading the file. **Frequency: a few times per session when debugging type errors or reviewing unfamiliar library APIs.** **Value per hit: 3–4 manual calls and a path-guessing step collapsed into one.**

**Tier C — capability-level, not efficiency-level**

5. **Transitive type hierarchy and reference graphs.** `type_hierarchy` returns the full super/sub chain — including into external stub files (`.pyi`) — in one call. `find_referencing_symbols` returns each reference *with its containing symbol* (the function/class that holds it), which Grep cannot produce. Built-ins can imitate single-level relationships with Grep but cannot chase override chains in one step. **Frequency: once or twice a session on unfamiliar code; close to never once you know the hierarchy.** **Value per hit: one call vs. N iterative Greps, plus recall into stub files.**

**Verdict:** Serena's biggest practical contribution is the *quietest* one — stable symbolic addressing that survives in-file mutations — and its most *spectacular* one — single-call atomic cross-file refactorings — is rare but decisive when it fires; the middle-weight wins are payload asymmetry on body rewrites and cheap dependency navigation.

---

## §2. Added value, by area

Ordered by frequency × value-per-hit, not novelty.

- **Stable identifiers across chained edits to one file.** Demonstrated in Task 17: three sequential edits to `CollectStats` (`insert_after refresh_len_stats`, `insert_after refresh_return_stats`, `replace_symbol_body refresh_std_array_stats`) all used the same kind of stable name-path address and worked without re-reading the file. An equivalent `Edit` chain after the first two inserts would have needed at least one intermediate `Read` because line numbers and some text anchors shift. **Frequency: every multi-edit session.** **Value: ~1 re-read (~400–800 bytes) saved per subsequent edit; compounds across a session.**

- **Body replacement at medium/large sizes.** Measured in Tasks 7a/7b/7c on `collector.py`:
  - 1-line change (7a): Edit `~120 B`, `replace_symbol_body` `~1200 B`. **Edit wins ~10×.**
  - ~20-line rewrite (7b): Edit `~1430 B`, Serena `~715 B`. **Serena wins ~2×.**
  - ~66-line rewrite (7c): Edit `~4700 B`, Serena `~2050 B`. **Serena wins ~2.3×.**
  Crossover sits around 10–15 lines. **Frequency: once or twice per substantive editing session.** **Value: 50–60% payload cut on the edits where it applies; grows with body size.**

- **Atomic cross-file operations.** Task 10 renamed `EpisodeRolloutHookMCReturn` across `collector.py` + `test_collector.py` in one `rename` call, and — importantly — *also* updated a Sphinx `:class:` cross-reference in a docstring that a pure `Edit` chain would only catch if the caller remembered to sweep docstrings separately. Task 11 moved `get_stddev_from_dist` from `collector.py` to `batch.py`: one call updated the target file, added the import at the source, updated a separate test file's import, *and* removed the now-unused `Categorical` import from the source. **Frequency: 0–3 times per session.** **Value per hit: 5–10 calls saved plus one or two automatic correctness wins the manual path tends to miss.**

- **Dependency navigation.** Task 6 resolved `Distribution` from its use site in `collector.py` into the real `torch.distributions.distribution.Distribution` class body (~300 lines) with a single `find_declaration` call. The built-in path requires parsing imports, guessing the venv site-packages location, and reading the file by hand. **Frequency: a few times per session on unfamiliar code or type debugging.** **Value: 3–4 calls plus one guess collapsed to one.**

- **Reference and hierarchy queries that distinguish "code usage" from "any text match".** Task 4 on `Collector`: `find_referencing_symbols` returned ~70 files with each reference tagged by containing symbol (`Py:IMPORT_ELEMENT`, `Py:FUNCTION_DECLARATION: ["test_dqn"]`), while `Grep \bCollector\b` returned 332 matches across 88 files including notebooks, SVGs, `CHANGELOG.md`, and `README.md`. These are answers to *different questions*, and each tool is naturally matched to one. **Frequency: several times per session; the right question determines the right tool.** **Value: precision saves a read of each false-positive file (~10–30 saved reads on a popular class).**

- **Safe-delete with automatic usage check.** Task 12: `safe_delete` on `EpisodeRolloutHookMerged` succeeded silently (no usages); on `CollectStats` it refused with a 200+ line usage list grouped by enclosing symbol. The built-in equivalent is a `Grep` followed by manual discipline — same call count but no enforcement. **Frequency: rare (delete-by-name operations).** **Value: when it fires, it prevents the most expensive class of mistake (deleting a referenced symbol).**

**Verdict:** The two highest-weighted contributions are the boring one (stable in-file addressing, every session) and the refactoring one (rare but 5–10× call reduction); Serena's more exotic capabilities (hierarchy, dependency navigation) are lower-frequency polish on top.

---

## §3. Detailed evidence, grouped by capability

### §3.1 File structural overview

**Task 2** — structural overview of `tianshou/data/collector.py` (1551 lines).
- Serena `get_symbols_overview(depth=0)`: ~240 bytes returned; top-level classes + functions names only, no line numbers, no per-class method detail.
- Serena `get_symbols_overview(depth=1)`: ~3200 bytes; classes with nested method and field lists.
- Grep `^(class |def |    def )`: ~3300 bytes; identical structural information plus line numbers.
- Output size is roughly equivalent at `depth=1`. The real difference shows up in the *follow-up* call:
  - Serena follow-up (`find_symbol("Collector/_compute_action_policy_hidden", include_body=True)`): 1 call, returns body only, ~66 lines. Address `Collector/_compute_action_policy_hidden` remains stable across any edits to unrelated regions.
  - Built-in follow-up (`Read offset=707 limit=66`): 1 call, returns body + line-number prefixes. Address (line 707) goes stale after any insert above that line.
- The winner depends on what comes next: if you stop at reading, they tie; if you plan to edit the body next, Serena's address is the one that survives the subsequent mutation.

**Verdict (§3.1):** tie on the overview call alone; Serena wins on the full read-then-edit chain because of address stability.

### §3.2 Method body retrieval

**Task 3** — body of `Collector._compute_action_policy_hidden`.
- Serena: 1 call (`find_symbol include_body`), ~1800 bytes of body-only output.
- Built-ins: 1 call (`Read offset=707 limit=66`), ~1900 bytes including line prefixes.
- Essentially equivalent on a cold cache; Serena's output is cleaner for machine consumption, built-ins' is cleaner for humans reviewing line locations.

**Verdict (§3.2):** tie in isolation; Serena wins when followed by an edit.

### §3.3 Reference search

**Task 4** — who uses `Collector`?
- Serena `find_referencing_symbols`: ~70 files, each reference annotated with its containing symbol. Precise to code usage. Missed docstring/README mentions almost entirely (except a few `FILE`-tagged entries).
- Grep `\bCollector\b`: 332 occurrences across 88 files, includes `docs/*.ipynb`, `docs/*.md`, `structure.svg`, `CHANGELOG.md`, `README.md`.
- Cost comparison for the question "every code file that *uses* this class":
  - Serena: 1 call, answer usable directly.
  - Grep: 1 call, answer needs filtering by extension and visual dedup.
- Cost comparison for "anywhere this name appears in the repo, including docs":
  - Serena: cannot answer directly.
  - Grep: 1 call, answer usable directly.

**Verdict (§3.3):** each toolset wins on its own question; pick by question shape, and do not penalize either for missing the other's answer.

### §3.4 Type hierarchy and override chains

**Task 5** — super/sub types of `BaseCollector`.
- Serena `type_hierarchy(depth=0)`: 1 call, returns transitive hierarchy including `Collector → AsyncCollector` on the sub side and `ABC → object` on the super side — the super side is resolved into an external `<ext:abc.pyi>` stub file.
- Grep `class \w+\(.*BaseCollector`: 1 call, returns exactly one hit (`Collector`). To find `AsyncCollector` I'd have to issue a second grep for `class \w+\(.*Collector`, and so on recursively. External supertypes cannot be reached at all.
- **This is a capability delta, not a raw efficiency delta**: text search cannot cross an override chain in one step, and cannot reach `.pyi` stubs.

**Verdict (§3.4):** clear Serena capability win; value grows with hierarchy depth and cross-file reach.

### §3.5 Dependency navigation

**Task 6** — resolve `Distribution` from its usage in `collector.py`.
- Serena `find_declaration` with a regex anchored at the usage site: 1 call, returned the full 300-line body of `torch/distributions/distribution.py::Distribution`, including docstrings. Unambiguous — the tool used the import context to pick the right file out of 41 candidates named `Distribution` in the dependency tree.
- Built-in equivalent: (a) Read `collector.py` imports, (b) map `from torch.distributions import Distribution` to `torch/distributions/distribution.py`, (c) locate the venv's site-packages path, (d) Read the file. 3–4 calls plus one implicit "where is the venv" step.

**Verdict (§3.5):** clear Serena capability win whenever you need third-party source.

### §3.6 Small edits (< ~10 lines)

**Task 7a** — one-line error message change inside `BaseCollector._validate_buffer` (21-line body).
- `Edit old_string=".. should be greater than 0." new_string=".. must be strictly positive."`: ~120 bytes on the wire, one call. Prerequisite: know the exact anchor (one prior Grep or Read, which I already had from earlier in the session).
- `replace_symbol_body`: ~1200 bytes (whole 21-line body resent). Prerequisite: prior `find_symbol include_body` to see the current body.
- Result diff identical in both cases (`1 insertion(+), 1 deletion(-)`).

**Verdict (§3.6):** Edit wins ~10× on payload for ≤ 3-line changes; use Edit whenever the change is small and the anchor is obvious.

### §3.7 Medium edits (~10–30 lines)

**Task 7b** — rewrite ~20 lines inside `CollectStats.update_at_step_batch`.
- Edit: ~750 B old anchor + ~680 B new body = ~1430 B on the wire.
- `replace_symbol_body`: ~680 B new body + ~35 B name_path = ~715 B.
- Both end with identical diffs.
- Prerequisite is symmetric: both need to see the current body first (one `find_symbol` or one `Read`).

**Verdict (§3.7):** crossover point — Serena pulls ahead around 15 lines and wins ~2× at 20.

### §3.8 Large edits (50+ lines)

**Task 7c** — whole-body rewrite of `Collector._compute_action_policy_hidden` (~66 lines).
- Edit: ~2700 B old anchor + ~2000 B new body = ~4700 B.
- `replace_symbol_body`: ~2000 B new body + name_path = ~2050 B.
- Ratio ~2.3×. The asymmetry grows linearly with body size: Edit scales as `O(old + new)`, `replace_symbol_body` as `O(new)`.

**Verdict (§3.8):** clear Serena win; reach for `replace_symbol_body` on any substantial method-body rewrite.

### §3.9 Structural insertion

**Task 8** — insert a new method right after `CollectStats.refresh_len_stats`.
- Serena `insert_after_symbol` with `name_path="CollectStats/refresh_len_stats"` and body of the new method: ~150 B on the wire, unambiguous anchor, 1 call. Result: new method inserted cleanly between `refresh_len_stats` and `refresh_std_array_stats`.
- Edit equivalent: old_string must capture the end of `refresh_len_stats` uniquely — roughly the last 5 lines of the method — then new_string replays those lines and appends the new method. Approximately 550 B on the wire.

**Verdict (§3.9):** Serena wins ~3× on payload and on anchor stability for structural inserts.

### §3.10 Single-file rename of a private helper

**Task 9** — rename `_HACKY_create_info_batch` → `_create_info_batch_legacy` (2 occurrences, same file).
- Serena `rename` via name_path: 1 call.
- Edit with `replace_all=true`: 1 call. Both the declaration and the one call site get rewritten.
- Both succeed; both leave a clean 2-line diff.

**Verdict (§3.10):** tie — for single-file renames of a distinctive identifier, built-in `Edit(replace_all=true)` is competitive.

### §3.11 Multi-file rename

**Task 10** — rename `EpisodeRolloutHookMCReturn` → `EpisodeRolloutMCReturnHook` (5 sites across `tianshou/data/collector.py` and `test/base/test_collector.py`).
- Serena `rename`: 1 call, atomic across both files. Also updated a Sphinx `:class:` docstring cross-reference at `collector.py:611` via the default `rename_in_comments=True`.
- Built-in chain: `Grep` (1) → `Edit replace_all=true` on `collector.py` (1) → `Edit replace_all=true` on `test_collector.py` (1) → verification `Grep` (1). 4 calls minimum, 5–6 if I remember to hit the docstring reference. Not atomic across files.

**Verdict (§3.11):** Serena wins ~4–5× on call count and catches the docstring reference by default.

### §3.12 Cross-module move

**Task 11** — move `get_stddev_from_dist` from `tianshou/data/collector.py` to `tianshou/data/batch.py`.
- Serena `move`: 1 call. Final `git diff --stat`:
  ```
  test/base/test_stats.py    |  3 ++-
  tianshou/data/batch.py     | 24 ++++++++++++++++++++++++
  tianshou/data/collector.py | 27 ++-------------------------
  ```
  The tool:
  1. Inserted the function into `batch.py`.
  2. Removed it from `collector.py`.
  3. Added `from tianshou.data.batch import get_stddev_from_dist` to `collector.py`.
  4. Updated `test/base/test_stats.py`'s import of this function.
  5. **Removed the now-unused `Categorical` import from `collector.py`**, because nothing else in that file referenced it.
- Built-in chain (honestly planned): Grep for callers (1) → Read each caller to see current import form (≥ 3) → Edit collector.py to remove the function (1) → Edit batch.py to insert (1) → Edit each caller's import (≥ 2) → Edit collector.py to remove the now-unused `Categorical` import (1) → verification Grep (1). **Roughly 10 calls**, and the "unused import" cleanup is the kind of thing a distracted human misses.

**Verdict (§3.12):** biggest call-count collapse in the evaluation — ~10× — with a correctness bonus.

### §3.13 Safe deletion

**Task 12** — two deletions.
- `safe_delete(EpisodeRolloutHookMerged)` (unused): succeeded, removed the class cleanly, 38-line deletion.
- `safe_delete(CollectStats)` (heavily used): refused with an explicit `SafeDeleteFailedException`, returning ~220 usage locations grouped by enclosing symbol.
- Built-in equivalent: `Grep` for usages → visual inspection → `Edit` deletion. Same call count when the symbol is unused; similar when it isn't, but with no enforcement — a careless `Edit` would happily delete a used symbol and break the repo.

**Verdict (§3.13):** same call count as manual, but the enforcement eliminates the worst mistake class.

### §3.14 Inline helper

**Task 13** — skipped. No legally inlinable helper (single-expression, side-effect-free, with call sites) found in a quick scan of `tianshou/`. Per the prompt, I did not contrive a broken input.

**Verdict (§3.14):** no data; comparison not applicable on this codebase.

### §3.15 Scope precision and disambiguation

**Task 14** — find every `_collect` in `collector.py`.
- `find_symbol("_collect")` returned three distinct hits with their full name paths (`BaseCollector/_collect`, `Collector/_collect`, `AsyncCollector/_collect`), plus inlined signatures for each. Each is addressable unambiguously — I can rename, replace-body, or reference exactly one of them.
- `Grep "_collect\("` would return all three locations but with no structural distinction: to tell them apart I'd have to read surrounding context to see which class each `def` belongs to.

**Verdict (§3.15):** Serena's addressing is precise by construction on override chains and overloads.

### §3.16 Chained edits to one file

**Task 17** — three successive edits on `CollectStats`:
1. `insert_after_symbol("CollectStats/refresh_len_stats", ...)` — insert new `reset_len_stats` method.
2. `insert_after_symbol("CollectStats/refresh_return_stats", ...)` — insert new `reset_return_stats` method.
3. `replace_symbol_body("CollectStats/refresh_std_array_stats", ...)` — rewrite an existing method body.

All three calls used the original name paths, unchanged; none required a re-Read between edits. Final `git diff` showed exactly the expected three-edit composite: two insertions plus one body rewrite, adjacent and clean. The first two inserts shifted line numbers between 8 and 16 lines, which would have invalidated any line-number addressing for the third target.

An equivalent Edit chain would have survived this particular sequence (because the anchors were text, not line numbers), but it exposes the *general* pattern: name_paths are mutation-proof addresses, line numbers are not, and large text anchors become non-unique quickly.

**Verdict (§3.16):** for any session with three or more edits to the same file, symbolic addressing is a systematic safety and efficiency win.

### §3.17 Non-code files and free-text searches

**Tasks 19/20** — state the applicability boundary and move on. Semantic tools don't apply to changelogs, notebooks, configs, or free-text searches for log strings; `Read` and `Grep` are the right tools.

**Verdict (§3.17):** built-ins only; not a contest.

---

## §4. Token-efficiency analysis

**Payload asymmetry by edit size** (measured on `collector.py`):

| Edit size | Edit (old+new) | `replace_symbol_body` | Ratio |
|---|---|---|---|
| 1 line (in 21-line method) | ~120 B | ~1200 B | **Edit 10× smaller** |
| ~20 lines rewritten | ~1430 B | ~715 B | **Serena 2× smaller** |
| ~66 lines whole-body | ~4700 B | ~2050 B | **Serena 2.3× smaller** |

Crossover is around 10–15 lines. Below it, Edit's per-change payload is dominated by the tiny anchor and wins by an order of magnitude. Above it, Edit pays once for the old body and again for the new, while `replace_symbol_body` pays only for the new body plus a ~30-character name_path; the gap grows linearly with body size. Structural inserts (`insert_after_symbol`) have similar asymmetry — the name_path replaces a multi-line text anchor.

**Forced reads.** Serena's overview tools return symbol names without bodies and its reference tools return containing-symbol metadata without snippets, so you control when to pull code into context. `find_symbol(include_body=False)` + `find_symbol(include_body=True, name_path=...)` is a two-step "browse, then fetch body" pattern that keeps context lean; the built-in equivalent is `Grep` (which does not return bodies) + `Read` with an offset/limit, which is about as lean but requires the caller to compute the limit by hand.

**Stable vs ephemeral addressing.** Name paths remain valid across edits to unrelated regions of the same file. Line numbers and byte offsets do not, and text anchors become ambiguous once a file grows. The output-size comparison has to account for *shelf life*: a slightly larger overview that stays useful across an entire session is cheaper than a slightly smaller one that has to be regenerated after each edit. In a five-edit session on one file, Serena's name-path overview is queried once; the line-number grep output is effectively refreshed after each edit that shifts upstream content — an O(edits × file_grep_cost) hidden tax that the one-call comparison misses.

**Verdict (§4):** under ~10-line edits, built-in `Edit` is cheaper; above that threshold, symbolic body replacement wins on raw payload; across a multi-edit session, name-path addressing wins regardless of size because it doesn't decay.

---

## §5. Reliability and correctness analysis (under correct use)

**Precision of matching.** `find_referencing_symbols` on `Collector` returns ~70 code files and annotates each with the containing symbol that holds the reference. `Grep \bCollector\b` returns 332 hits across 88 files including notebooks, SVGs, and markdown. For the question "which Python files import and use this class?", Serena's output is directly usable and Grep's needs a filter pass. For the question "where is the name `Collector` mentioned anywhere in the repo, including docs, changelog, and diagrams?", Grep's output is directly usable and Serena's is incomplete by design. Each tool's precision is perfect *for its question*; the mistake is asking the wrong one.

**Scope disambiguation across overrides.** `find_symbol("_collect")` returned three distinct name paths — `BaseCollector/_collect`, `Collector/_collect`, `AsyncCollector/_collect` — each independently addressable for rename or body replacement. Text search on `_collect(` returns three line locations with no structural annotation; the caller must read context to tell them apart, and any cross-file rename risks touching the wrong override if called carelessly.

**Atomicity on real failures.** `move` of `get_stddev_from_dist` made coordinated changes across three files in one call. A five-step Edit chain replicating the same move would leave the repo in a half-renamed state if any intermediate step failed on disk-full, a permission error, or an interrupted process; a single-call atomic refactoring either completes or leaves the working tree clean. This matters less for local agent sessions (where the blast radius of a partial refactor is small and recoverable with `git checkout --`) and more for any workflow where a failed run is committed or pushed.

**Transitive semantic queries.** `type_hierarchy` returned both the sub-chain (`Collector → AsyncCollector`) and the super-chain (`BaseCollector → ABC → object`, with `ABC` resolved into an external `.pyi` stub) in one call. No text-search workflow reaches into stub files or chains override relationships in one step.

**Success signals (symmetric).** Both toolsets return only mechanical success: "the file was written," "the rename finished." Neither verifies that the new code still compiles, type-checks, or preserves semantics. Post-edit `git diff` review is the caller's responsibility on both sides.

**Verdict (§5):** Serena's correctness edge is concentrated in questions that are semantic by nature — override chains, transitive type queries, cross-file atomic ops — and tied to Grep/Edit on questions that are textual by nature.

---

## §6. Workflow effects across a multi-step session

The single biggest session-level effect is **identifier stability across edits**. A session that makes 5 edits to `collector.py` looks like:

- With symbolic addressing: one `get_symbols_overview` at the start, five `replace_symbol_body`/`insert_after_symbol` calls by name path. The overview is consulted zero or one more times. No re-reads of the file between edits.
- With line-number or large-text-anchor addressing: one `Grep class/def` at the start, one `Read offset+limit` before each edit (or a careful re-grep after any insert that shifts lines), five `Edit`s. The Grep/overview may need to be refreshed mid-session once line numbers drift.

The hidden cost of the built-in workflow is not in any single call — it's the compounding re-Reads and anchor recomputation across a session. A single Read of a 1500-line file is ~40 kB of context; doing it four extra times across a session is a ~160 kB invisible tax that never shows up in a one-call comparison.

**Intermediate output survives.** The overview I pulled at the start of this evaluation, the reference list for `Collector`, the type hierarchy for `BaseCollector`, and the signature table for `_collect` all remain valid now that I'm writing the report — I never had to regenerate them. A workflow based on line numbers would have had to regenerate its intermediate output after each of the ~15 edits I applied and reverted during the experiments.

**Verdict (§6):** session-level efficiency scales with mutation rate; the more edits you plan, the more decisively symbolic addressing wins, and the effect is invisible on any single-call benchmark.

---

## §7. Capabilities with no built-in equivalent

1. **Cross-file atomic refactorings with automatic import maintenance.** `move` cleaned up an unused import in the source file as a side effect of moving the last user of that import. Built-ins have no equivalent — you'd have to notice. **Value: rare but high — this is the kind of cleanup that bit-rots across a large refactor.**

2. **Resolution of third-party symbols from a usage site.** `find_declaration` + `find_symbol(search_deps=True)` reach into `site-packages` and `.pyi` stubs for the exact class used at a given line of code. **Value: a few times per session, saves 3–4 calls each.**

3. **Transitive type hierarchy including external supertypes.** `type_hierarchy` returns sub- and super-chains in one call and crosses module boundaries and stub files. No text-search sequence can reproduce this in O(1). **Value: once or twice per unfamiliar codebase; near zero once you know it.**

4. **Containing-symbol metadata on reference queries.** `find_referencing_symbols` returns each reference with its enclosing function/class name, making the result a navigation map rather than a line list. **Value: every time you need to understand *how* a symbol is used, not just *where*.**

5. **Enforced safe-delete with usage-list refusal.** `safe_delete` refuses to remove a symbol that still has usages and returns the usage list. Built-ins cannot refuse — `Edit` applies whatever you send it. **Value: rare but prevents the worst-class mistake.**

**Verdict (§7):** the capability deltas are real but concentrated in lower-frequency tasks; the one that shows up across *every* editing session is (1.5) — symbolic addressing as a property of the *editing* tools themselves, which I'm treating as the Tier-A efficiency win in §1 rather than a separate capability here.

---

## §8. Where built-ins remain the right default

- **Small anchored edits (≤ ~10 lines).** Task 7a: Edit's payload is ~10× smaller than `replace_symbol_body` for a one-line change because it sends only the two anchors, not the whole body. Frequency: extremely high — typo fixes, constant changes, error-message tweaks, single-line bug fixes. **Probably 30–50% of daily edits.**

- **Free-text search for strings, log messages, magic constants, URLs.** Task 20: `Grep` is the only tool that can find a bare string across the repo. Serena's symbolic search expects an identifier, not a phrase. **Frequency: multiple times per session.**

- **Non-code files** — changelogs, READMEs, YAML configs, notebooks. Task 19: `Read` is the tool. **Frequency: occasional but universal.**

- **Doc and docstring sweeps after a code-level rename.** Serena's `rename_in_comments=True` catches Sphinx cross-references (verified in Task 10), but if your documentation lives outside of Python docstrings — `.md`, `.rst`, `.ipynb` — a text-based `Grep` sweep is the complementary step, not a Serena failure. **Frequency: every cross-file rename that touches a public API.**

- **Single-file renames of distinctive identifiers.** Task 9: `Edit replace_all=true` is effectively tied with semantic rename; either works. **Frequency: common.**

- **Quick one-shot explorations where you don't plan to edit the target.** If the workflow is "look at one function, answer a question, move on," `Read offset/limit` and `Grep` are as fast as semantic tools and don't require any address to be stable beyond the current call.

These cases are not rare — collectively they probably cover more than half of the calls in a typical session, which is exactly why §1's weighting puts the quiet "addressing stability" win above the spectacular "cross-file refactoring" wins: the former touches every session, the latter touches a handful per week.

**Verdict (§8):** built-ins are the right default for small edits, free-text search, non-code files, and docstring sweeps — roughly half of daily editing work.

---

## §9. Usage rule for a developer with both toolsets

Per-task decision rule, in priority order:

1. **Small edit (≤ ~10 lines), known text anchor** → `Edit`. Payload is ~10× smaller than symbolic body replacement at this size.
2. **Medium or larger body rewrite, or structural insert** → `replace_symbol_body` / `insert_after_symbol`. 2–3× payload cut plus stable addressing for the next edit.
3. **Cross-file rename, move, or delete of a symbol** → `rename` / `move` / `safe_delete`, then a complementary `Grep` sweep of `.md`/`.rst`/`.ipynb` for any text-only references. The semantic tool covers code and Python docstrings in one atomic step; the Grep sweep handles external docs.
4. **Find callers of a class/function** → `find_referencing_symbols`.
5. **Find any mention of a name across the repo including docs** → `Grep`.
6. **Navigate into third-party library source** → `find_declaration` with a regex anchored at the use site, or `find_symbol(search_deps=True)`.
7. **Understand a type hierarchy** → `type_hierarchy`.
8. **Understand an unfamiliar file's structure** → `get_symbols_overview(depth=1)` for classes + methods, then `find_symbol(include_body=True)` for the methods you actually want to read.
9. **Chained edits to one file** → address every edit by `name_path`; do not mix in line-number or large-text-anchor edits unless you plan to re-Read before each one.
10. **Free-text search, non-code files, small single-line tweaks** → built-ins.

**Verdict (§9):** Edit for small changes, symbolic body replacement for larger ones, semantic multi-file refactoring tools with a Grep doc-sweep on top, Grep/Read for text and non-code; the one habit that matters most is defaulting to name-path addressing whenever you expect more than one edit to the same file.
