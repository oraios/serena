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
| **Status** | **Mitigated** — signature fallback added |

**Fix applied:** When `textDocument/hover` returns null, Serena now falls back to extracting the first 5 lines of the symbol body as a signature summary. This provides useful type/signature info without the cost of `include_body=true`.
- Changed `request_info_for_symbol()` in `src/serena/symbol.py` to call `_extract_signature_fallback()` when hover returns null.

**Remaining upstream issue:**
- [ ] File upstream issue with JetBrains — `hoverProvider` is advertised but non-functional
- [ ] Full hover info (KDoc, resolved types) still unavailable — only raw source signature is shown

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
| **Status** | **Fixed** — `is_low_level()` corrected; Struct no longer hidden |

**Fix applied:** Adjusted `is_low_level()` in `src/serena/symbol.py` to exclude Struct (23), Event (24), Operator (25), and TypeParameter (26) from the "low level" classification. These are all structural types that should appear in `get_symbols_overview`. Also fixed the wrong comment in `test_kotlin_basic.py:33`.

**Remaining upstream issue:**
- [ ] Kotlin LSP still reports data classes as Struct (kind 23) instead of Class (kind 5) — `include_kinds=[5]` will still miss them
- [ ] File upstream issue with JetBrains

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
| **Status** | **Fixed** — directory support added |

**Fix applied:** `GetSymbolsOverviewTool.apply()` in `src/serena/tools/symbol_tools.py` now accepts directories. When a directory is passed, it delegates to `_apply_directory()` which iterates over all source files and returns a per-file grouped overview.

### 7. `find_file` — `relative_path` Is Required (Should Default to ".")

| Field | Value |
|-------|-------|
| **Root cause** | `FindFileTool.apply(file_mask, relative_path)` — `relative_path` has no default value |
| **Category** | Serena |
| **Where** | `src/serena/tools/file_tools.py:129` |
| **Impact** | Minor friction — must always pass `"."` or `"src"` for project-wide searches, while `find_symbol` defaults to the whole project |
| **Status** | **Fixed** |

**Fix applied:** Added `relative_path: str = "."` default in `FindFileTool.apply()` in `src/serena/tools/file_tools.py`.

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
| **Status** | **Fixed** |

**Fix applied:** Added `limit: int = 0` parameter to `FindSymbolTool.apply()` in `src/serena/tools/symbol_tools.py`. When limit > 0 and results exceed it, returns `{results, total_count, limited_to}` so the caller knows results were truncated. Default 0 means no limit (backward compatible).

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

| # | Issue | Priority | Category | Status |
|---|-------|----------|----------|--------|
| 1 | find_referencing_symbols broken | P0 | Upstream | Open |
| 2 | include_info silent no-op | P0 | Upstream + Serena | **Mitigated** (signature fallback) |
| 3 | Class/Struct kind inconsistency | P1 | Upstream + Serena | **Fixed** (`is_low_level` corrected) |
| 4 | Constructor var vs body property | P1 | Upstream | Open |
| 5 | Extension fns not addressable | P1 | Upstream | Open |
| 6 | get_symbols_overview file-only | P2 | Serena | **Fixed** (directory support added) |
| 7 | find_file requires relative_path | P2 | Serena | **Fixed** (default `"."`) |
| 8 | body_location 0-based | P2 | By design? | Open |
| 9 | find_symbol no limit param | P2 | Serena | **Fixed** (`limit` param added) |
| 10 | search_for_pattern spacing | P2 | By design | Open |

### Remaining Work

- **#1** — Investigate upstream Kotlin LSP `textDocument/references`, add fallback warning + `search_for_pattern` suggestion
- **#4, #5** — Document limitations for users
- **#8, #10** — Investigate / close as by-design
