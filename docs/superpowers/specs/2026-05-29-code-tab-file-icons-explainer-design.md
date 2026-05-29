# Code tab: file-explorer icons + explainer popover

**Date:** 2026-05-29
**Area:** `dashboard/` (Serena dashboard frontend — Svelte 5 runes + TS + Vite)
**Status:** Approved design

## Goal

Improve the dashboard **Code** tab in two ways:

1. **Icons in the file explorer** — directory icons (open/closed), file icons by
   type, and distinct icons for well-known filenames.
2. **An explainer** — a brief, discoverable note describing how the Code
   explorer and diagnostics work, which LSP tools back each pane, and what the
   user sees. Delivered as a `?` info popover.

Plus two scoped improvements requested alongside: **indent guides** in the file
tree and a **nicer loading state**.

Frontend-only. The `/code/*` HTTP API in `../src/serena/dashboard_code.py` is a
**frozen contract** — no backend changes.

## Context (current state)

- `dashboard/src/components/code/CodePage.svelte` — layout: `FileTree` aside +
  middle pane with tabs (Symbols / Search / Diagnostics). No header/toolbar.
- `dashboard/src/components/code/FileTree.svelte` — recursive tree. Files show an
  **empty** `.chev` spacer + name; dirs show a chevron + name. A hover-revealed
  stethoscope action runs diagnostics per row. Loading shows a bare `…`. No icons.
- `dashboard/src/lib/symbolTree.ts` — already maps **symbol kind → {icon,
  colorVar, label}** via `getKindMeta`, rendered as a tinted badge in
  `FileSymbols.svelte`. **This is the pattern to mirror for file types.**
- `dashboard/src/components/code/FileSymbols.svelte` — has 1px `::before` indent
  guides (depth-0 has none); the file tree lacks these.
- `dashboard/src/components/common/` — has `Icon`, `Spinner`, `Modal`,
  `Collapsible`. **No popover primitive exists.**
- Color tokens (`src/styles/tokens.css`, light + dark): `--accent`,
  `--chart-2` (blue), `--chart-3` (green), `--chart-4` (red), `--chart-5`
  (purple), `--chart-6` (gold), `--text-muted`, `--text-secondary`. There is no
  `--chart-1` (accent fills that role). **Never hardcode hex — use tokens.**
- Icons come from `@lucide/svelte` exclusively.
- Backend routes (`dashboard_code.py`) and the LSP methods they call:
  - `/code/list_dir` — filesystem listing (respects project ignores), not LSP.
  - `/code/file_symbols` — LSP `request_document_symbols`
    (`textDocument/documentSymbol`).
  - `/code/workspace_symbol_search` — LSP `request_workspace_symbol`
    (`workspace/symbol`).
  - `/code/diagnostics_summary` — LSP `request_text_document_diagnostics`
    (pull, `textDocument/diagnostic`), falling back to
    `request_published_text_document_diagnostics` (push/published).

## Approved decisions

- **Icon style:** Lucide line icons tinted with existing `--chart-N` / `--accent`
  / `--text-muted` color tokens, one accent color per category. No new
  dependency. Mirrors the Symbols-pane icon pattern.
- **Explainer:** a single `?` info button in a new slim Code-tab toolbar, opening
  a popover that covers the whole explorer (tree + all three panes + diagnostics
  caveat).
- **Extras included:** special-filename icons; indent guides + nicer loading.
- **Extras excluded:** diagnostic badges on tree rows (not selected this pass).

## Components & changes

### 1. `src/lib/fileIcons.ts` (new, pure module)

Mirrors `symbolTree.ts` `getKindMeta`. Pure, unit-testable, no Svelte state.

```ts
import type { Component } from 'svelte';

export interface FileIconMeta {
  icon: Component;
  colorVar: string; // CSS var name, e.g. '--chart-2'
  label: string;    // accessible / tooltip label, e.g. 'TypeScript source'
}

// kind: directory entry kind from DirEntry ('dir' | 'file')
// open: for dirs, whether currently expanded (open vs closed folder icon)
export function getFileIconMeta(
  name: string,
  kind: 'dir' | 'file',
  open?: boolean,
): FileIconMeta;
```

Resolution order inside `getFileIconMeta`:

1. **Directory** → `FolderOpen` if `open` else `Folder`, `colorVar: '--accent'`,
   label `'Folder'`.
2. **Special filename** (case-insensitive match on the basename, checked before
   extension):

   | Match | Icon | Token |
   |---|---|---|
   | `package.json` | `Package` | `--chart-6` |
   | `README*` | `BookOpen` | `--text-muted` |
   | `.gitignore`, `.gitattributes` | `GitBranch` | `--text-muted` |
   | `Dockerfile`, `docker-compose*` | `Container` | `--chart-2` |
   | `LICENSE*` | `Scale` | `--text-muted` |
   | `tsconfig*`, `*.config.*` | `FileCog` | `--chart-6` |
   | `.env*` | `KeyRound` | `--chart-4` |
   | `Makefile` | `Hammer` | `--text-muted` |
   | `*.lock`, `*-lock.json` (e.g. `package-lock.json`, `yarn.lock`) | `FileLock` | `--text-muted` |

3. **By extension → category → {icon, token}:**

   | Category | Icon | Token | Extensions |
   |---|---|---|---|
   | Code | `FileCode` | `--chart-2` | ts, tsx, js, jsx, mjs, cjs, py, rs, go, java, kt, c, h, cpp, hpp, cs, rb, php, swift, svelte, vue |
   | Data/config | `Braces` | `--chart-6` | json, yaml, yml, toml, ini, cfg |
   | Markup/docs | `FileText` | `--text-muted` | md, markdown, txt, rst, adoc |
   | Styles | `Hash` | `--chart-5` | css, scss, sass, less |
   | Images | `Image` | `--chart-3` | png, jpg, jpeg, gif, svg, webp, ico, bmp |
   | Data files | `Database` | `--chart-4` | sql, csv, tsv, db, sqlite, parquet |
   | Shell | `SquareTerminal` | `--chart-3` | sh, bash, zsh, fish, ps1, bat |
   | Archive | `FileArchive` | `--text-muted` | zip, tar, gz, tgz, bz2, xz, 7z, rar |
   | Fallback | `File` | `--text-muted` | (anything else) |

All icon names above must exist in `@lucide/svelte`; verify each at
implementation time and substitute the nearest available glyph if any is
missing (note the substitution in the PR).

### 2. `src/components/code/FileTree.svelte`

- Import `getFileIconMeta` and `Icon`.
- **Files:** replace the empty `.chev` spacer with the type icon, tinted via
  `style:--icon-color="var({meta.colorVar})"`, `size={14}`. Keep the name and
  the existing selected/hover behavior.
- **Dirs:** keep the expand/collapse chevron, and add the folder icon
  (`open = code.expanded.has(fullPath)`) tinted `--accent`, before the name.
- **Indent guides:** port the `FileSymbols` 1px `::before` guide keyed off
  `--depth` (depth-0 renders no guide). Reuse the same token (`--border`,
  `opacity: 0.6`) for visual consistency.
- **Loading:** replace the `…` `<li class="loading">` with the existing
  `Spinner` component + a "Loading…" label.
- Leave error rows, the stethoscope `diag-action`, and `runDiagnosticsForPath`
  untouched.

### 3. `src/components/common/Popover.svelte` (new, reusable primitive)

Generic anchored popover (no equivalent exists; `Modal` is too heavy for inline
help, `Collapsible` reflows layout).

- Props: `label` (trigger aria-label), trigger `children` snippet OR an `icon`
  prop for the trigger, and a `content` snippet for the panel.
- Behavior: click trigger toggles; closes on **Escape** and **click-outside**;
  `aria-expanded` on the trigger, `role="dialog"` + `aria-label` on the panel.
- Positioning: absolutely positioned relative to the trigger wrapper
  (top-right-anchored by default), within the dashboard's existing stacking;
  scoped CSS using tokens (`--bg-elevated`, `--border`, `--radius`, shadow var
  if present else a token-based box-shadow).
- No focus-trap requirement (it is a transient info panel, not a modal); focus
  returns naturally. Keep it minimal.

### 4. `src/components/code/CodePage.svelte`

- Add a slim toolbar row **above** the `.layout` grid: label "Code" on the left,
  a `?` button (`CircleHelp` from lucide) on the right wired to `Popover`.
- Adjust the `.layout` height (currently `calc(100vh - 140px)`) to account for
  the new toolbar row so the panes don't overflow.
- **Popover content** (concise, accurate to `dashboard_code.py`):
  - **File tree** — project files & folders from disk (respects project
    ignores). Hover a row → run diagnostics on that file/folder.
  - **Symbols (file)** — outline of the open file via LSP
    `textDocument/documentSymbol`. Click a symbol to copy `path:line`.
  - **Search (workspace)** — symbol search across the project via LSP
    `workspace/symbol`.
  - **Diagnostics (project / file / directory)** — errors & warnings via LSP
    `textDocument/diagnostic` (pull; falls back to published/push). Computing is
    slow and briefly pauses other LSP tools — run it only when needed.

## Out of scope

- Diagnostic badges/dots on tree rows.
- Any backend / `/code/*` contract change.
- Unrelated refactors of the Code tab.

## Testing

- `tests/file-icons.test.ts` (new) — unit-test `getFileIconMeta`:
  special-filename precedence over extension, extension→category mapping, folder
  open vs closed, case-insensitivity, fallback for unknown extensions.
- Update `tests/file-tree.test.ts` — assert icons render for dir/file rows,
  open-folder icon when expanded, spinner on loading state. Keep existing
  stethoscope/error assertions green.
- Add a render/interaction test for `Popover` (opens on click, closes on Escape
  and on outside click; `aria-expanded` toggles).
- Existing component-test conventions: render + interaction (Vitest + jsdom +
  Testing Library), per `dashboard/CLAUDE.md`.

## Verification & build-output contract

From `dashboard/`:

1. `npm run check` (svelte-check) — no errors.
2. `npm test` (Vitest) — all pass.
3. `npm run lint` and `npm run format`.
4. `npm run build` — regenerates `../src/serena/resources/dashboard/`
   (`index.html` + hashed `assets/`). **Commit the regenerated output**; CI
   fails the PR if it is stale. **Stage all changes** before committing so a
   partial stage doesn't leave files prettier-dirty.

## Risks / notes

- **Lucide glyph availability** — confirm each icon name exists in the installed
  `@lucide/svelte`; substitute the closest match if not, and note it.
- **Popover positioning** — keep it simple (CSS-anchored). If it clips at the
  viewport edge, prefer right-alignment over adding a positioning library.
- **Layout height** — the added toolbar must not push the panes into overflow on
  the `@media (max-width: 1000px)` stacked layout; re-check both breakpoints.
