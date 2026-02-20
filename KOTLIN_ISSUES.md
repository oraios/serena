# Kotlin Support — Issue Tracker

Comprehensive tracking of issues identified in Serena's Kotlin language support.
Based on testing report from 2026-02-20 against the JetBrains Kotlin Language Server v261.13587.0.

## Key Insight

Most P0/P1 issues stem from the Kotlin Language Server's incomplete LSP implementation
(textDocument/references, textDocument/hover). Serena correctly delegates to the LSP but
gets empty/useless responses. Fixes fall into two categories:

- **Upstream (Kotlin LSP)**: Issues in the language server itself — we can't fix these, only work around them or document them.
- **Serena**: Issues in our code that we can fix directly.

---

## P0 — Critical

### 1. `find_referencing_symbols` — Non-Functional for Cross-File Kotlin References

| Field | Value |
|-------|-------|
| **Root cause** | Kotlin LSP's `textDocument/references` returns empty for cross-file references |
| **Category** | Upstream (Kotlin LSP) |
| **Where** | `src/solidlsp/ls.py` → `request_references()` → LSP returns `[]` |
| **Impact** | Cannot find usages of classes, methods, or properties across files |
| **Evidence** | 5/6 symbols tested returned `{}`. Only same-file property access (dateSlot) returned 1 result. IntelliJ finds 15-40 refs for the same symbols. |
| **Status** | Open |

**Possible actions:**
- [ ] File upstream issue with JetBrains kotlin-lsp if not already tracked
- [ ] Document the limitation clearly in Serena's Kotlin docs
- [ ] Consider adding a warning when `find_referencing_symbols` returns empty for Kotlin, suggesting `search_for_pattern` as a fallback
- [ ] Investigate if workspace indexing needs to complete before references work (timing issue?)
- [ ] Test with the very latest kotlin-lsp version to see if it's been improved

### 2. `include_info=true` — Silently Returns No Data for Kotlin

| Field | Value |
|-------|-------|
| **Root cause** | Kotlin LSP's `textDocument/hover` returns empty/null for most symbols |
| **Category** | Upstream (Kotlin LSP) |
| **Where** | `src/serena/symbol.py:579` (`request_info_for_symbol`) → `src/solidlsp/ls.py:1537` (`request_hover`) → LSP returns null |
| **Impact** | No way to get signature/type info without reading the full body (`include_body=true`), which is much more expensive |
| **Evidence** | Tested on 5 symbol kinds (class, method, property, enum, data class) — none returned info |
| **Status** | Open |

**Possible actions:**
- [ ] Verify hover is truly non-functional (test against our test repo, not just backend-kotlin)
- [ ] If hover returns null, consider falling back to extracting a summary from the body (first line / signature only)
- [ ] Document the limitation
- [ ] Check if the Kotlin LSP advertises `hoverProvider` capability (it does — see `_start_server` asserts)

---

## P1 — Moderate

### 3. Inconsistent Kind Mapping — Kotlin Classes Reported as "Struct" (kind 23)

| Field | Value |
|-------|-------|
| **Root cause** | Kotlin LSP reports some classes as `Struct` (kind 23) instead of `Class` (kind 5) |
| **Category** | Upstream (Kotlin LSP), but Serena could remap |
| **Where** | Kotlin LSP `textDocument/documentSymbol` response → `src/solidlsp/ls_types.py` SymbolKind |
| **Impact** | `include_kinds=[5]` misses classes reported as Struct. `is_low_level()` (kind >= 13) incorrectly classifies data classes as low-level, hiding them from `get_symbols_overview`. |
| **Evidence** | `data class SolverConfig` → Struct; `class Stage1Lesson` (annotated) → Struct; plain classes → Class |
| **Status** | Open |

**Critical side-effect:** `is_low_level()` in `src/serena/symbol.py:232` returns `True` for `Struct` (23 >= 13), which means data classes and annotated classes are **hidden from `get_symbols_overview`** by the filter at `src/serena/tools/symbol_tools.py:75`.

**Possible actions:**
- [ ] **HIGH PRIORITY**: Add Kotlin-specific kind remapping in Serena (Struct → Class) so that `is_low_level` and `include_kinds` work correctly
- [ ] Alternatively, adjust `is_low_level()` to exclude Struct from the "low level" threshold
- [ ] File upstream issue — `data class` should be kind 5 (Class), not 23 (Struct)
- [ ] Fix the wrong comment in `test_kotlin_basic.py:33`: `# 23 = Class` should be `# 23 = Struct`

### 4. Constructor Parameters vs Body Properties — Kind Inconsistency

| Field | Value |
|-------|-------|
| **Root cause** | Kotlin LSP reports constructor `val`/`var` params as `Variable` (13) but body `val`/`var` as `Property` (7) |
| **Category** | Upstream (Kotlin LSP) |
| **Where** | Kotlin LSP `textDocument/documentSymbol` |
| **Impact** | Filtering by kind is unreliable — `include_kinds=[7]` misses constructor-declared properties |
| **Evidence** | `Stage1Lesson/id` (constructor val) → Variable; `Stage1Lesson/weeklyPattern` (body var) → Property |
| **Status** | Open |

**Possible actions:**
- [ ] Consider Kotlin-specific remapping of constructor `Variable` children to `Property`
- [ ] Document the distinction for users
- [ ] This is lower priority than #3 since it's less impactful

### 5. Extension Functions Not Addressable via Receiver Type

| Field | Value |
|-------|-------|
| **Root cause** | Kotlin LSP reports extension functions as top-level `Function` symbols without receiver info |
| **Category** | Upstream (Kotlin LSP), fundamental LSP limitation |
| **Where** | Document symbol tree — extension fns are top-level, not nested under the receiver type |
| **Impact** | `find_symbol("Route/authRoutes")` returns empty; must use `find_symbol("authRoutes")` losing context |
| **Evidence** | `fun Route.authRoutes(...)` stored as top-level function `authRoutes` |
| **Status** | Open |

**Possible actions:**
- [ ] Document this as a known limitation
- [ ] Consider parsing extension function bodies to detect receiver types (expensive, fragile)
- [ ] This is fundamentally an LSP document symbol limitation — the spec doesn't have a concept of "receiver type"

---

## P2 — Minor

### 6. `get_symbols_overview` — No Directory Support

| Field | Value |
|-------|-------|
| **Root cause** | `GetSymbolsOverviewTool.apply()` only accepts file paths, not directories |
| **Category** | Serena |
| **Where** | `src/serena/tools/symbol_tools.py:36` |
| **Impact** | Must know exact file path before getting an overview. Initial exploration requires `find_file` + `list_dir` first. |
| **Status** | Open |

**Possible actions:**
- [ ] Add directory support: when given a directory, iterate over files and return a combined overview
- [ ] Consider adding a `limit` param to cap results when scanning directories
- [ ] Low priority — `list_dir` + per-file overview is a reasonable workaround

### 7. `find_file` — `relative_path` Is Required (Should Default to ".")

| Field | Value |
|-------|-------|
| **Root cause** | `FindFileTool.apply(file_mask, relative_path)` — `relative_path` has no default value |
| **Category** | Serena |
| **Where** | `src/serena/tools/file_tools.py:129` |
| **Impact** | Minor friction — must always pass `"."` or `"src"` for project-wide searches, while `find_symbol` defaults to the whole project |
| **Status** | Open |

**Possible actions:**
- [ ] Add `relative_path: str = "."` as default parameter
- [ ] Trivial fix, high consistency win

### 8. File-Level Symbol `body_location` Uses 0-Based Start

| Field | Value |
|-------|-------|
| **Root cause** | LSP uses 0-based line numbers; Serena passes them through without adjustment for File-level symbols |
| **Category** | Serena / By design |
| **Where** | `src/serena/symbol.py:261` — reads `location.range.start.line` directly |
| **Impact** | File-level symbols start at line 0, all others at 1+. Can cause off-by-one confusion. |
| **Status** | Open |

**Possible actions:**
- [ ] Investigate whether this is truly inconsistent or if all `body_location` values are 0-based (LSP spec is 0-based)
- [ ] If 0-based is correct for all symbols, this may be a non-issue — the "mixed convention" may be a misunderstanding
- [ ] Clarify in documentation

### 9. `find_symbol` — No Result Count Limit / Pagination

| Field | Value |
|-------|-------|
| **Root cause** | `FindSymbolTool.apply()` has no `limit` parameter |
| **Category** | Serena |
| **Where** | `src/serena/tools/symbol_tools.py:98` |
| **Impact** | Searching for common names (e.g., "logger") in a directory returns all matches, potentially flooding output |
| **Status** | Open |

**Possible actions:**
- [ ] Add a `limit` parameter (default maybe 20-50)
- [ ] `max_answer_chars` already truncates, but at the serialization level — a proper `limit` would be cleaner
- [ ] Consider adding a note in the truncation message about how many results were found vs shown

### 10. `search_for_pattern` — Output Spacing

| Field | Value |
|-------|-------|
| **Root cause** | Line numbers are right-justified to 4 chars (`rjust(4)`) in `TextLine.format_line()` |
| **Category** | Serena (by design) |
| **Where** | `src/serena/text_utils.py:43-52` |
| **Impact** | Different-width line numbers cause variable padding (e.g., `>  86:` vs `> 505:`) |
| **Status** | Open |

**Possible actions:**
- [ ] This is actually *correct* behavior — `rjust(4)` pads to 4 chars, so 2-digit and 3-digit numbers have different leading spaces
- [ ] The `>` marker is always `  >` (consistent). The variable part is the line number padding.
- [ ] Could increase rjust width or use dynamic width per file, but this is very low priority
- [ ] Consider closing as "by design"

---

## Summary

| # | Issue | Priority | Category | Difficulty | Quick Win? |
|---|-------|----------|----------|------------|------------|
| 1 | find_referencing_symbols broken | P0 | Upstream | N/A | No |
| 2 | include_info silent no-op | P0 | Upstream | N/A | No |
| 3 | Class/Struct kind inconsistency | P1 | Upstream + Serena | Medium | Partial (remap) |
| 4 | Constructor var vs body property | P1 | Upstream | Low | Document |
| 5 | Extension fns not addressable | P1 | Upstream | N/A | Document |
| 6 | get_symbols_overview file-only | P2 | Serena | Medium | No |
| 7 | find_file requires relative_path | P2 | Serena | Trivial | **Yes** |
| 8 | body_location 0-based | P2 | By design? | Low | Investigate |
| 9 | find_symbol no limit param | P2 | Serena | Low | Yes |
| 10 | search_for_pattern spacing | P2 | By design | N/A | Close |

### Recommended Fix Order

1. **#7** — Trivial default param fix (5 min)
2. **#3** — Struct→Class remapping + `is_low_level` fix (critical for `get_symbols_overview` correctness)
3. **#9** — Add limit param to `find_symbol`
4. **#2** — Add fallback info extraction from body when hover fails
5. **#1** — Investigate upstream, add fallback warning + `search_for_pattern` suggestion
6. **#6** — Directory support for `get_symbols_overview`
7. **#4, #5** — Document limitations
8. **#8, #10** — Investigate / close as by-design
