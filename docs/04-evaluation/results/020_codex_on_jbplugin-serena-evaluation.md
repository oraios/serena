# Evaluation by Gpt 5.4 in Codex CLI

## Final Recommendation

The recommendation is created with the [follow-up summary prompt](../011_followup-summary-prompt), everything else was created in one shot from the
[evaluation prompt](../010_evaluation-prompt).

> "As a coding AI agent, I would ask my owner to add Serena because it lets me work with code as stable symbols instead of fragile text, turning the
refactors, lookups, and multi-file edits that usually feel risky and repetitive into precise IDE-backed operations I can trust."

## 1. Headline

Serena's largest added value is stable semantic addressing and IDE-backed refactoring. In this Java plugin repo, that meant a method/class could be targeted as `Logger/warning[0]`, `Symbol/safeDelete`, or `ProjectUtil` without line numbers, and cross-file rename/move/inline/delete operations were delegated to IntelliJ's model.

High value, common: symbol lookup, method-body retrieval, stable name paths, and reference search. Frequency: many times per coding session. Value per hit: usually saves 1-3 reads/searches and avoids loading whole files.

High value, less frequent but large: cross-file rename, move, safe delete, inline. Frequency: a few times per feature/refactor. Value per hit: saves roughly 5-20 calls and reduces missed import/call-site risk.

Medium value: type hierarchy and external dependency declaration lookup. Frequency: occasional. Value per hit: turns "search and infer" into 1 semantic query; text search cannot truly reproduce transitive hierarchy or dependency source lookup without IDE/index/cache work.

Low/no added value: config/docs/free-text search and tiny line edits. Frequency: common, but built-ins are already optimal. Value per hit for Serena: none or negative for small local edits.

**Verdict:** Serena adds the most value whenever the task is about named code entities rather than text spans; the weighted daily win is stable symbol navigation, while the biggest per-hit win is IDE refactoring.

## 2. Added Value By Area

- Stable symbol navigation: showed on `Symbol.java` and `UIControlUtil.java`. Frequency: every non-trivial coding session. Value: saves 1-3 calls per lookup and avoids full-file reads.
- Symbol-scoped edits: `replace_symbol_body`, `insert_after_symbol`, and overload-specific targeting worked on `Logger/warning[0]`, `Logger/warning[1]`, and `Logger/logToToolWindow`. Frequency: several times per session. Value: small edits lose to text Edit, medium edits break even, whole-body edits save about 2x input payload.
- Cross-file refactors: renaming `Logger` to `SerenaLogger` updated 10 files plus the Java file rename; moving `ProjectUtil` into `service.endpoint` updated the package and removed the now-local import. Frequency: occasional. Value: saves roughly 10-20 manual reads/edits/verifications.
- Semantic relationships: `ToolWindowContent` references, `TypeHierarchy` subtypes, `SubtypeHierarchy` supertypes, and `Gson.fromJson` declaration came back as code entities. Frequency: occasional. Value: 1 call versus several searches plus inference.
- Built-in text work remains essential: `build.gradle.kts`, `/findSymbol`, `127.0.0.1`, and `FORM_INIT_DELAY_MILLIS` were naturally handled by `Read`/`rg`. Frequency: large share of daily work. Value: Serena adds nothing there.

**Verdict:** Serena's contribution is not blanket speed; it removes repeated code-entity bookkeeping from ordinary navigation and almost all bookkeeping from real refactors.

## 3. Detailed Evidence

### 3.1 Code Understanding

Semantic overview of `Symbol.java` returned a class tree with fields, methods, inner classes, and overload indexes in 1 call. Text equivalent was `rg "class |...\\(" Symbol.java`, which returned 100+ signature/comment hits and needed filtering. Follow-up semantic read of `UIControlUtil/findButton` was 1 call returning only the 10-line body; text follow-up needed locating the line then reading a slice.

Payloads: semantic overview sent path/depth only and returned about 900 tokens; text grep returned about 2,000+ tokens for `Symbol.java`. Semantic method read returned about 90 tokens; text slice returned similar body tokens but required a locator step.

**Verdict:** Use Serena for source structure and specific method bodies; use text only when the question is literally textual.

### 3.2 References, Hierarchy, Dependencies

`find_referencing_symbols` on `ToolWindowContent` returned 4 code uses: two subclass declarations and two parameters. `rg "ToolWindowContent"` returned 5 lines including the definition. For "who uses this in code," Serena was higher precision; for "where is this string mentioned," `rg` was the right tool.

`type_hierarchy` on `TypeHierarchy` returned `SubtypeHierarchy` and `SupertypeHierarchy`; supertypes for `SubtypeHierarchy` returned `TypeHierarchy` and external `Object`. Text search found name matches plus false positives like `TypeHierarchyRequest`.

`find_declaration` on `gson.fromJson(requestBody, requestClass)` resolved external `Gson/fromJson[0]` and returned the source body. Built-ins needed finding the Gradle dependency, locating `~/.gradle/.../gson-2.10.1-sources.jar`, listing/extracting `Gson.java`, then searching inside it.

**Verdict:** Serena adds real semantic reach for "code relationships"; text search can find mentions, but not reliably answer relationship questions in one step.

### 3.3 Edit Size Economics

Small edit: rewriting `Logger.logToToolWindow` as an early return. Text patch sent a small old/new anchor, about 9 changed lines. Serena required sending the whole 11-line method body. Text was cheaper.

Medium edit: rewriting most of `UIControlUtil.tryHandleDialogs`. Text patch sent about 14 old lines plus 20 new lines. Serena sent the full method body, including its comment, about 26 lines. Roughly even.

Large edit: replacing `Symbol.safeDelete` implementation shape. With content-anchored Edit, a whole-body replacement would send old body plus new body, about 2x the new method payload. `replace_symbol_body` sent only the new body plus `Symbol/safeDelete`.

**Verdict:** Use text Edit for 1-3 line changes, either tool for 10-30 line method rewrites, and Serena for whole-method replacements.

### 3.4 Refactors

Private rename: `Logger/logToToolWindow` to `appendToToolWindow` changed 7 occurrences in 1 semantic call plus optional `rg` verification. Manual path was `rg`, patch each occurrence, then `rg` verify: 3 calls and more payload.

Multi-file rename: `Logger` to `SerenaLogger` changed 10 files and renamed the Java file. Manual path would be `rg`, read 10 files, rename/move file, edit imports/type names/constructors, verify with `rg`, and likely compile: roughly 14-20 calls.

Move: moving `ProjectUtil` to `service.endpoint` moved the file, changed its package, and removed the import from `RefreshFileHandler` in 1 call. Manual path would coordinate filesystem move, package line, import removal/additions, and verification.

Safe delete: `DebugUtil` had no references; safe delete returned `affected_references: []` and deleted it. Manual path is search, delete, verify. Inline: `ProjectUtil/getAbsolutePath` inlined into both call sites in 1 call.

**Verdict:** Every multi-file or semantic refactor tested was a clear Serena win in call count, payload, and correctness surface.

### 3.5 Session Effects

I chained three edits in `Logger.java`: rename helper, replace `Logger/warning[0]`, insert after `Logger/error[0]`. The name paths survived earlier edits; no line recalculation was needed. A built-in line/slice workflow would need refreshed context after insertions because line numbers and nearby anchors shift.

**Verdict:** Serena's stable identifiers compound across a session; the more edits you make in one file, the wider the gap gets.

## 4. Token Efficiency

The crossover is size-dependent. Small edit: text wins because it sends only a tiny anchor. Medium rewrite: near parity. Whole-body rewrite: Serena wins because it sends new body only, while content-anchored Edit sends old body plus new body.

Forced reads matter: `find_symbol(...include_body=true)` avoided reading 573 lines of `UIControlUtil.java` and 1,295 lines of `Symbol.java`. Stable outputs also have longer shelf life: `Logger/warning[0]` remains useful after unrelated edits; line 52 does not.

**Verdict:** Token economics favor built-ins for tiny local text edits and Serena for symbol retrieval, chained work, and whole-symbol replacement.

## 5. Reliability

Semantic matching distinguished overloads: `Logger/warning[0]` was `warning(String,Object...)`; `Logger/warning[1]` was `warning(String,Throwable)`. `rg "warning\\("` returned both and left disambiguation to the caller.

Atomicity matters: semantic rename/move run as IDE refactorings, so a failure is not a half-finished sequence of 10 manual edits. Both toolsets still report mechanical success only; semantic intent still needs diff/build review.

Transitive queries are where text cannot compete directly: hierarchy and external declaration lookup depend on IDE indexes and dependency sources, not just strings.

**Verdict:** Correctness weight favors Serena for code-entity scope and refactoring atomicity, while text remains correct for text questions.

## 6. Workflow Effects

Over a multi-step session, Serena's intermediate artifacts stay usable: symbol trees, name paths, reference lists, and hierarchy nodes survive edits outside those symbols. Text outputs are often ephemeral: line numbers and byte offsets decay immediately after insertions/deletions.

The practical effect is not just fewer calls; it is fewer re-reads. In the chained `Logger.java` session, Serena needed three edit calls. A text workflow would normally require initial reads/searches, edits, and refreshed context before later insertions.

**Verdict:** Serena's session-level multiplier comes from not having to rediscover where code moved after each edit.

## 7. No Built-In Equivalent

- IDE semantic rename/move/inline/safe-delete: high value when refactoring, moderate frequency. Built-ins can approximate with many edits but cannot provide IDE refactoring semantics or atomicity.
- Type hierarchy including external `Object`: medium value, occasional. Text can search `extends`, but cannot transitively resolve hierarchy with dependency/stub awareness in one call.
- External dependency declaration resolution: medium value, occasional. Built-ins require build-file discovery and local source/cache spelunking.
- Overload/name-path targeting: high value in typed code, frequent enough to matter. Text can match names but cannot address `warning[0]` as a distinct method without manual signature reasoning.

**Verdict:** Serena's unique capabilities are concentrated in IDE-indexed code intelligence and refactoring operations, not general file manipulation.

## 8. Built-Ins As Default

Use built-ins for non-code files, config, docs, and free text. `build.gradle.kts` was best read directly. `rg` was clearly right for `/findSymbol`, `127.0.0.1`, and `FORM_INIT_DELAY_MILLIS`.

Use built-ins for tiny edits where a short unique anchor is obvious. Also always keep a post-refactor text sweep for comments, markdown, notebooks, generated files, and product strings; that is complementary verification, not a Serena weakness.

Estimated share: built-ins remain best for maybe 40-60% of daily interactions because much coding work is still file/text/config/search. Serena dominates the code-symbol subset.

**Verdict:** Start with built-ins for text and config; switch to Serena as soon as the noun in your task is a symbol.

## 9. Practical Rule

Reach for Serena when the task says class, method, overload, implementation, reference, hierarchy, rename, move, inline, delete, or "insert after this method." Reach for `rg`/Read/Edit when the task says string, config, docs, log message, URL, generated text, or "change these two lines."

For edits: text Edit for 1-3 line tweaks; Serena `replace_symbol_body` for full methods/classes; semantic refactor tools for any rename/move/delete/inline that crosses call sites or imports.

I restored all tracked edits after the experiments. The tracked working tree was clean after evaluation; the only baseline untracked entries were `.claude/` and `serena-evaluation-prompt.md`. I did not run the Gradle test suite because the task was an evaluation, not a product change.

**Verdict:** With both toolsets installed, use built-ins for text and Serena for code entities; that rule captures almost all of the measured value without overthinking each call.
