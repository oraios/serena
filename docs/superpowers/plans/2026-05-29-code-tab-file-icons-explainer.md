# Code-tab File Icons + Explainer Popover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add type-aware icons (folders open/closed, files by extension/special filename) to the dashboard Code tab's file explorer, plus indent guides and a spinner loading state, and a `?` info popover explaining how the explorer and diagnostics work.

**Architecture:** A new pure `fileIcons.ts` module maps a filename + kind to `{icon, colorVar, label}`, mirroring the existing `symbolTree.ts` `getKindMeta` pattern. `FileTree.svelte` renders those icons (tinted via a CSS var from a color token). A new reusable `Popover.svelte` common primitive (none exists today) hosts the explainer text, wired into a new slim toolbar in `CodePage.svelte`.

**Tech Stack:** Svelte 5 (runes) + TypeScript + Vite, `@lucide/svelte` icons, Vitest + jsdom + Testing Library. Colors come exclusively from CSS tokens in `src/styles/tokens.css`.

**Working directory:** All paths are relative to `dashboard/`. Run all `npm` commands from `dashboard/`. Spec: `docs/superpowers/specs/2026-05-29-code-tab-file-icons-explainer-design.md`.

**Verified facts (do not re-litigate):**
- All Lucide icon names below exist in `@lucide/svelte@1.17.0`. `CircleHelp` is a valid alias that re-exports `circle-question-mark.svelte`.
- `Spinner.svelte` takes no props, is fixed 16px, and renders `aria-label="Loading"`.
- Color tokens available: `--accent`, `--chart-2` (blue), `--chart-3` (green), `--chart-4` (red), `--chart-5` (purple), `--chart-6` (gold), `--text-muted`, `--text-secondary`, `--border`. There is **no** `--chart-1`.
- `Icon.svelte` renders `aria-label={label}` only when a `label` prop is passed; otherwise the icon is `aria-hidden`.
- `stubFetchRoutes` (in `tests/helpers.ts`) accepts a function body; it `await`s the function, so returning a never-resolving Promise keeps a request pending (used to test the loading state).

---

## File Structure

- **Create** `src/lib/fileIcons.ts` — pure filename→icon/color/label mapping. One responsibility: icon resolution. No Svelte state.
- **Create** `tests/file-icons.test.ts` — unit tests for the mapping.
- **Modify** `src/components/code/FileTree.svelte` — render icons, indent guides, spinner loading.
- **Modify** `tests/file-tree.test.ts` — add icon + spinner assertions (keep existing ones).
- **Create** `src/components/common/Popover.svelte` — reusable anchored popover primitive.
- **Create** `tests/popover.test.ts` — open/Escape/outside-click behavior.
- **Modify** `src/components/code/CodePage.svelte` — slim toolbar + `?` popover; relayout height.
- **Modify** `tests/code-page.test.ts` — add help-popover assertion (keep existing ones).
- **Regenerate** `../src/serena/resources/dashboard/` via `npm run build` (committed; CI-enforced).

---

## Task 1: `fileIcons.ts` mapping module

**Files:**
- Create: `src/lib/fileIcons.ts`
- Test: `tests/file-icons.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/file-icons.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { getFileIconMeta } from '../src/lib/fileIcons';
import {
  Folder,
  FolderOpen,
  FileCode,
  Braces,
  Image,
  File,
  Package,
  FileLock,
  FileCog,
} from '@lucide/svelte';

describe('getFileIconMeta', () => {
  it('returns a closed folder for a collapsed directory', () => {
    const m = getFileIconMeta('src', 'dir', false);
    expect(m.icon).toBe(Folder);
    expect(m.colorVar).toBe('--accent');
    expect(m.label).toBe('Folder');
  });

  it('returns an open folder for an expanded directory', () => {
    expect(getFileIconMeta('src', 'dir', true).icon).toBe(FolderOpen);
  });

  it('maps code extensions to FileCode / --chart-2', () => {
    const m = getFileIconMeta('main.ts', 'file');
    expect(m.icon).toBe(FileCode);
    expect(m.colorVar).toBe('--chart-2');
  });

  it('maps JSON to Braces', () => {
    expect(getFileIconMeta('data.json', 'file').icon).toBe(Braces);
  });

  it('maps images case-insensitively to Image', () => {
    expect(getFileIconMeta('logo.PNG', 'file').icon).toBe(Image);
  });

  it('lets a special filename win over its extension (package.json -> Package)', () => {
    expect(getFileIconMeta('package.json', 'file').icon).toBe(Package);
  });

  it('maps lock files to FileLock', () => {
    expect(getFileIconMeta('package-lock.json', 'file').icon).toBe(FileLock);
    expect(getFileIconMeta('yarn.lock', 'file').icon).toBe(FileLock);
  });

  it('maps *.config.* to FileCog', () => {
    expect(getFileIconMeta('vite.config.ts', 'file').icon).toBe(FileCog);
  });

  it('matches special names case-insensitively', () => {
    expect(getFileIconMeta('README.md', 'file').label).toBe('Readme');
  });

  it('falls back to File / --text-muted for unknown extensions', () => {
    const m = getFileIconMeta('mystery.xyz', 'file');
    expect(m.icon).toBe(File);
    expect(m.colorVar).toBe('--text-muted');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- file-icons`
Expected: FAIL — `Failed to resolve import "../src/lib/fileIcons"` (module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `src/lib/fileIcons.ts`:

```ts
import {
  Folder,
  FolderOpen,
  FileCode,
  Braces,
  FileText,
  Hash,
  Image,
  Database,
  SquareTerminal,
  FileArchive,
  File,
  Package,
  BookOpen,
  GitBranch,
  Container,
  Scale,
  FileCog,
  KeyRound,
  Hammer,
  FileLock,
} from '@lucide/svelte';
import type { Component } from 'svelte';

export interface FileIconMeta {
  icon: Component;
  colorVar: string; // CSS var name, e.g. '--chart-2'
  label: string; // accessible / tooltip label
}

// Extension category definitions.
const CODE: FileIconMeta = { icon: FileCode, colorVar: '--chart-2', label: 'Code' };
const DATA_CONFIG: FileIconMeta = { icon: Braces, colorVar: '--chart-6', label: 'Config' };
const DOCS: FileIconMeta = { icon: FileText, colorVar: '--text-muted', label: 'Document' };
const STYLES: FileIconMeta = { icon: Hash, colorVar: '--chart-5', label: 'Stylesheet' };
const IMAGES: FileIconMeta = { icon: Image, colorVar: '--chart-3', label: 'Image' };
const DATA_FILE: FileIconMeta = { icon: Database, colorVar: '--chart-4', label: 'Data' };
const SHELL: FileIconMeta = { icon: SquareTerminal, colorVar: '--chart-3', label: 'Shell script' };
const ARCHIVE: FileIconMeta = { icon: FileArchive, colorVar: '--text-muted', label: 'Archive' };
const FALLBACK: FileIconMeta = { icon: File, colorVar: '--text-muted', label: 'File' };

// extension (no dot, lowercase) -> category
const EXT_MAP: Record<string, FileIconMeta> = {};
function register(def: FileIconMeta, exts: string[]) {
  for (const e of exts) EXT_MAP[e] = def;
}
register(CODE, [
  'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'py', 'rs', 'go', 'java', 'kt',
  'c', 'h', 'cpp', 'hpp', 'cs', 'rb', 'php', 'swift', 'svelte', 'vue',
]);
register(DATA_CONFIG, ['json', 'yaml', 'yml', 'toml', 'ini', 'cfg']);
register(DOCS, ['md', 'markdown', 'txt', 'rst', 'adoc']);
register(STYLES, ['css', 'scss', 'sass', 'less']);
register(IMAGES, ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp']);
register(DATA_FILE, ['sql', 'csv', 'tsv', 'db', 'sqlite', 'parquet']);
register(SHELL, ['sh', 'bash', 'zsh', 'fish', 'ps1', 'bat']);
register(ARCHIVE, ['zip', 'tar', 'gz', 'tgz', 'bz2', 'xz', '7z', 'rar']);

// Special filename rules, matched (case-insensitive) BEFORE the extension map.
interface SpecialRule extends FileIconMeta {
  match: (lowerName: string) => boolean;
}
const SPECIALS: SpecialRule[] = [
  { match: (n) => n === 'package.json', icon: Package, colorVar: '--chart-6', label: 'Package manifest' },
  { match: (n) => n.startsWith('readme'), icon: BookOpen, colorVar: '--text-muted', label: 'Readme' },
  { match: (n) => n === '.gitignore' || n === '.gitattributes', icon: GitBranch, colorVar: '--text-muted', label: 'Git config' },
  { match: (n) => n === 'dockerfile' || n.startsWith('docker-compose'), icon: Container, colorVar: '--chart-2', label: 'Docker' },
  { match: (n) => n.startsWith('license'), icon: Scale, colorVar: '--text-muted', label: 'License' },
  { match: (n) => n.startsWith('tsconfig') || /\.config\./.test(n), icon: FileCog, colorVar: '--chart-6', label: 'Config' },
  { match: (n) => n.startsWith('.env'), icon: KeyRound, colorVar: '--chart-4', label: 'Environment' },
  { match: (n) => n === 'makefile', icon: Hammer, colorVar: '--text-muted', label: 'Makefile' },
  { match: (n) => n.endsWith('.lock') || n.endsWith('-lock.json'), icon: FileLock, colorVar: '--text-muted', label: 'Lock file' },
];

export function getFileIconMeta(
  name: string,
  kind: 'dir' | 'file',
  open = false,
): FileIconMeta {
  if (kind === 'dir') {
    return { icon: open ? FolderOpen : Folder, colorVar: '--accent', label: 'Folder' };
  }
  const lower = name.toLowerCase();
  for (const s of SPECIALS) {
    if (s.match(lower)) return { icon: s.icon, colorVar: s.colorVar, label: s.label };
  }
  const dot = lower.lastIndexOf('.');
  const ext = dot > 0 ? lower.slice(dot + 1) : '';
  return EXT_MAP[ext] ?? FALLBACK;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- file-icons`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add src/lib/fileIcons.ts tests/file-icons.test.ts
git commit -m "feat(dashboard): file-icon mapping module for Code tab"
```

---

## Task 2: Icons, indent guides & spinner in `FileTree.svelte`

**Files:**
- Modify: `src/components/code/FileTree.svelte`
- Modify: `tests/file-tree.test.ts`

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/file-tree.test.ts` (inside the file, after the existing `describe` block — add a new `describe`):

```ts
describe('FileTree — icons & loading', () => {
  it('renders a type icon for files and a folder icon for directories', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({
        entries: [
          { name: 'main.ts', kind: 'file' },
          { name: 'src', kind: 'dir' },
        ],
      }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    // 'main.ts' -> Code icon (label 'Code'); 'src' -> closed folder (label 'Folder').
    expect(await findByLabelText('Code')).toBeTruthy();
    expect(await findByLabelText('Folder')).toBeTruthy();
  });

  it('shows a spinner while a directory is still loading', async () => {
    stubFetchRoutes({
      // Never resolves -> dir_children stays undefined -> loading row stays.
      '/code/list_dir': () => new Promise<never>(() => {}),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    // Spinner renders aria-label="Loading".
    expect(await findByLabelText('Loading')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- file-tree`
Expected: FAIL — `findByLabelText('Code')` / `'Folder'` / `'Loading'` not found (no icons/spinner yet).

- [ ] **Step 3: Add imports and the icon to the script block**

In `src/components/code/FileTree.svelte`, replace the import block (lines 1-4) with:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '../common/Icon.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { getFileIconMeta } from '$lib/fileIcons';
  import { ChevronRight, ChevronDown, TriangleAlert, Stethoscope } from '@lucide/svelte';
```

- [ ] **Step 4: Replace the loading row with a spinner**

Replace:

```svelte
    {:else if !children}
      <li class="loading">…</li>
```

with:

```svelte
    {:else if !children}
      <li class="loading"><Spinner /><span>Loading…</span></li>
```

- [ ] **Step 5: Compute per-entry icon meta and render it in both rows**

Replace the `{#each ...}` body (the block from `{@const fullPath = joinPath(path, entry.name)}` through the closing of the dir/file `{#if}...{/if}`, i.e. current lines 36-66) with:

```svelte
        {@const fullPath = joinPath(path, entry.name)}
        {@const meta = getFileIconMeta(
          entry.name,
          entry.kind,
          entry.kind === 'dir' && code.expanded.has(fullPath),
        )}
        <li>
          <div class="row-wrap">
            {#if entry.kind === 'dir'}
              <button
                type="button"
                class="row dir"
                class:depth-0={depth === 0}
                onclick={() => code.toggleExpand(fullPath)}
                aria-expanded={code.expanded.has(fullPath)}
              >
                <span class="chev">
                  <Icon icon={code.expanded.has(fullPath) ? ChevronDown : ChevronRight} size={14} />
                </span>
                <span class="ficon" style:--icon-color="var({meta.colorVar})">
                  <Icon icon={meta.icon} size={14} label={meta.label} />
                </span>
                <span class="name">{entry.name}</span>
                {#if code.dir_errors[fullPath] !== undefined}
                  <span class="warn" title={code.dir_errors[fullPath]}>
                    <Icon icon={TriangleAlert} size={14} label="Error" />
                  </span>
                {/if}
              </button>
            {:else}
              <button
                type="button"
                class="row file"
                class:depth-0={depth === 0}
                class:selected={code.selected_path === fullPath}
                onclick={() => code.selectPath(fullPath)}
              >
                <span class="chev" aria-hidden="true"></span>
                <span class="ficon" style:--icon-color="var({meta.colorVar})">
                  <Icon icon={meta.icon} size={14} label={meta.label} />
                </span>
                <span class="name">{entry.name}</span>
              </button>
            {/if}
```

Leave the rest of the `<li>` (the `diag-action` button and the `{#if entry.kind === 'dir' && code.expanded.has(fullPath)}` recursive render) unchanged.

- [ ] **Step 6: Add styles for the icon, indent guide, and loading row**

In the `<style>` block, add `position: relative;` to the existing `.row` rule (so the guide can be absolutely positioned). The `.row` rule already sets `padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));`. Then append these rules to the end of the `<style>` block:

```css
  .ficon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    color: var(--icon-color, var(--text-secondary));
  }
  /* 1px indent guide per nesting level; depth-0 has no parent to draw under. */
  .row::before {
    content: '';
    position: absolute;
    left: calc(var(--space-2) + var(--depth, 0) * var(--space-3) - var(--space-1));
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border);
    opacity: 0.6;
  }
  .row.depth-0::before {
    opacity: 0;
  }
```

Then update the existing `.loading` rule to lay the spinner and text out in a row. Replace:

```css
  .loading {
    color: var(--text-secondary);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
  }
```

with:

```css
  .loading {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-secondary);
    padding: var(--space-1);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
  }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `npm test -- file-tree`
Expected: PASS — both the new `icons & loading` tests and the existing `run diagnostics action` tests.

- [ ] **Step 8: Type-check**

Run: `npm run check`
Expected: 0 errors (warnings about `state_referenced_locally` elsewhere are pre-existing and fine).

- [ ] **Step 9: Commit**

```bash
git add src/components/code/FileTree.svelte tests/file-tree.test.ts
git commit -m "feat(dashboard): type icons, indent guides & spinner in FileTree"
```

---

## Task 3: Reusable `Popover.svelte` primitive

**Files:**
- Create: `src/components/common/Popover.svelte`
- Test: `tests/popover.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/popover.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { CircleHelp } from '@lucide/svelte';
import Popover from '../src/components/common/Popover.svelte';

const content = createRawSnippet(() => ({ render: () => `<p>Help body</p>` }));

function renderPopover() {
  return render(Popover, {
    label: 'How it works',
    icon: CircleHelp,
    title: 'How it works',
    children: content,
  });
}

describe('Popover', () => {
  it('is closed initially and opens on trigger click', async () => {
    const { getByLabelText, queryByRole, findByRole } = renderPopover();
    expect(queryByRole('dialog')).toBeNull();
    await fireEvent.click(getByLabelText('How it works'));
    expect(await findByRole('dialog')).toBeTruthy();
  });

  it('closes on Escape', async () => {
    const { getByLabelText, findByRole, queryByRole } = renderPopover();
    await fireEvent.click(getByLabelText('How it works'));
    await findByRole('dialog');
    await fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(queryByRole('dialog')).toBeNull());
  });

  it('closes on outside click', async () => {
    const { getByLabelText, findByRole, queryByRole } = renderPopover();
    await fireEvent.click(getByLabelText('How it works'));
    await findByRole('dialog');
    await fireEvent.click(document.body);
    await waitFor(() => expect(queryByRole('dialog')).toBeNull());
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- popover`
Expected: FAIL — `Failed to resolve import "../src/components/common/Popover.svelte"`.

- [ ] **Step 3: Write the component**

Create `src/components/common/Popover.svelte`:

```svelte
<script lang="ts">
  import type { Snippet, Component } from 'svelte';
  import Icon from './Icon.svelte';

  interface Props {
    label: string; // aria-label for the trigger button
    icon: Component<{
      size?: number | string;
      strokeWidth?: number | string;
      class?: string;
      'aria-hidden'?: 'true' | 'false' | boolean;
    }>;
    iconSize?: number;
    title?: string; // optional heading + dialog aria-label
    align?: 'left' | 'right';
    children: Snippet;
  }
  let { label, icon, iconSize = 16, title, align = 'right', children }: Props = $props();

  let open = $state(false);
  let root: HTMLElement;

  function toggle() {
    open = !open;
  }
  function onWindowKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && open) open = false;
  }
  function onWindowClick(e: MouseEvent) {
    // The trigger's own click toggles `open` before this bubbles to window;
    // a click inside `root` never closes, a click outside always does.
    if (open && root && !root.contains(e.target as Node)) open = false;
  }
</script>

<svelte:window onkeydown={onWindowKey} onclick={onWindowClick} />

<span class="popover-root" bind:this={root}>
  <button
    type="button"
    class="trigger"
    aria-label={label}
    aria-haspopup="dialog"
    aria-expanded={open}
    onclick={toggle}
  >
    <Icon {icon} size={iconSize} />
  </button>
  {#if open}
    <div class="panel" class:left={align === 'left'} role="dialog" aria-label={title ?? label}>
      {#if title}<h4 class="panel-title">{title}</h4>{/if}
      <div class="panel-body">{@render children()}</div>
    </div>
  {/if}
</span>

<style>
  .popover-root {
    position: relative;
    display: inline-flex;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: var(--space-1);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .trigger:hover,
  .trigger[aria-expanded='true'] {
    color: var(--text-primary);
    background: var(--bg);
  }
  .panel {
    position: absolute;
    top: calc(100% + var(--space-1));
    right: 0;
    z-index: 10;
    width: 320px;
    max-width: 80vw;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 6px 24px color-mix(in srgb, var(--text-primary) 18%, transparent);
    padding: var(--space-2);
    text-align: left;
  }
  .panel.left {
    right: auto;
    left: 0;
  }
  .panel-title {
    margin: 0 0 var(--space-1);
    font-size: 0.9em;
    color: var(--text-primary);
  }
  .panel-body {
    color: var(--text-secondary);
    font-size: 0.85em;
  }
</style>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- popover`
Expected: PASS (3 tests).

- [ ] **Step 5: Type-check**

Run: `npm run check`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/components/common/Popover.svelte tests/popover.test.ts
git commit -m "feat(dashboard): reusable Popover common primitive"
```

---

## Task 4: Toolbar + explainer popover in `CodePage.svelte`

**Files:**
- Modify: `src/components/code/CodePage.svelte`
- Modify: `tests/code-page.test.ts`

- [ ] **Step 1: Write the failing test**

Append a new `describe` block to `tests/code-page.test.ts`:

```ts
describe('CodePage — explainer popover', () => {
  it('opens the help popover and shows the LSP explainer text', async () => {
    const { getByLabelText, findByRole } = render(CodePage);
    await fireEvent.click(getByLabelText(/How the Code explorer works/i));
    const dialog = await findByRole('dialog');
    expect(dialog.textContent).toMatch(/documentSymbol/);
    expect(dialog.textContent).toMatch(/workspace\/symbol/);
    expect(dialog.textContent).toMatch(/textDocument\/diagnostic/);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- code-page`
Expected: FAIL — `getByLabelText(/How the Code explorer works/i)` finds nothing (no popover yet).

- [ ] **Step 3: Update the script block**

In `src/components/code/CodePage.svelte`, replace the import lines (lines 2-6) so they also import the Popover and the help icon. The new script block top reads:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import FileTree from './FileTree.svelte';
  import FileSymbols from './FileSymbols.svelte';
  import WorkspaceSearch from './WorkspaceSearch.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';
  import Popover from '../common/Popover.svelte';
  import { CircleHelp } from '@lucide/svelte';
```

(Keep the existing `diagFileCount` derived line and the closing `</script>`.)

- [ ] **Step 4: Wrap the layout in a flex column with a toolbar**

Replace the markup block (current lines 14-51, `<div class="layout"> ... </div>`) with:

```svelte
<div class="code-tab">
  <header class="toolbar">
    <span class="title">Code explorer</span>
    <div class="help-slot">
      <Popover
        label="How the Code explorer works"
        icon={CircleHelp}
        title="How the Code explorer works"
      >
        {#snippet children()}
          <dl class="help">
            <dt>File tree</dt>
            <dd>
              Project files &amp; folders from disk (respects project ignores). Hover a row to run
              diagnostics on that file or folder.
            </dd>
            <dt>Symbols (file)</dt>
            <dd>
              Outline of the open file via the LSP <code>textDocument/documentSymbol</code> request.
              Click a symbol to copy its <code>path:line</code>.
            </dd>
            <dt>Search (workspace)</dt>
            <dd>
              Symbol search across the whole project via the LSP <code>workspace/symbol</code>
              request.
            </dd>
            <dt>Diagnostics</dt>
            <dd>
              Errors &amp; warnings via the LSP <code>textDocument/diagnostic</code> request (pull;
              falls back to published/push). Scope it to the project, a file, or a directory.
              Computing is slow and briefly pauses other LSP tools — run it only when needed.
            </dd>
          </dl>
        {/snippet}
      </Popover>
    </div>
  </header>

  <div class="layout">
    <aside class="tree">
      <FileTree />
    </aside>
    <section class="middle">
      <nav class="middle-tabs" aria-label="Code views">
        <button
          type="button"
          class:active={code.middle_pane === 'symbols'}
          onclick={() => code.setMiddlePane('symbols')}
        >
          Symbols (file)
        </button>
        <button
          type="button"
          class:active={code.middle_pane === 'search'}
          onclick={() => code.setMiddlePane('search')}
        >
          Search (workspace)
        </button>
        <button
          type="button"
          class:active={code.middle_pane === 'diagnostics'}
          onclick={() => code.setMiddlePane('diagnostics')}
        >
          Diagnostics (project)
          {#if diagFileCount > 0}<span class="badge">· {diagFileCount}</span>{/if}
        </button>
      </nav>
      {#if code.middle_pane === 'symbols'}
        <FileSymbols />
      {:else if code.middle_pane === 'search'}
        <WorkspaceSearch />
      {:else}
        <DiagnosticsPanel />
      {/if}
    </section>
  </div>
</div>
```

- [ ] **Step 5: Move the fixed height onto the wrapper and add toolbar styles**

In the `<style>` block, replace the existing `.layout` rule:

```css
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: var(--space-2);
    height: calc(100vh - 140px);
  }
```

with:

```css
  .code-tab {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 140px);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-1) var(--space-2);
  }
  .toolbar .title {
    font-weight: 600;
    font-size: 0.9em;
    color: var(--text-secondary);
  }
  .help-slot {
    margin-left: auto;
  }
  .help :global(dt) {
    font-weight: 600;
    color: var(--text-primary);
    margin-top: var(--space-2);
  }
  .help :global(dt):first-child {
    margin-top: 0;
  }
  .help :global(dd) {
    margin: 0;
  }
  .help :global(code) {
    font-family: var(--font-mono);
    font-size: 0.95em;
    color: var(--text-primary);
  }
  .layout {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: var(--space-2);
  }
```

Then update the responsive rule so the wrapper height collapses on narrow screens. Replace:

```css
  @media (max-width: 1000px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto;
      height: auto;
    }
  }
```

with:

```css
  @media (max-width: 1000px) {
    .code-tab {
      height: auto;
    }
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto;
    }
  }
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `npm test -- code-page`
Expected: PASS — the new explainer test plus the three existing CodePage tests.

- [ ] **Step 7: Type-check**

Run: `npm run check`
Expected: 0 errors.

- [ ] **Step 8: Commit**

```bash
git add src/components/code/CodePage.svelte tests/code-page.test.ts
git commit -m "feat(dashboard): Code-tab toolbar with how-it-works explainer popover"
```

---

## Task 5: Full verification + build-output contract

**Files:**
- Regenerate & commit: `../src/serena/resources/dashboard/` (`index.html` + `assets/`)

- [ ] **Step 1: Run the full test suite**

Run: `npm test`
Expected: PASS — entire suite, no regressions.

- [ ] **Step 2: Type-check the whole project**

Run: `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Lint**

Run: `npm run lint`
Expected: clean (no errors).

- [ ] **Step 4: Format**

Run: `npm run format`
Expected: writes any formatting; re-run shows no changes.

- [ ] **Step 5: Build the bundle (regenerates committed assets)**

Run: `npm run build`
Expected: succeeds; `../src/serena/resources/dashboard/index.html` and `../src/serena/resources/dashboard/assets/` are regenerated.

- [ ] **Step 6: Stage ALL changes and commit the regenerated bundle**

Stage everything (a partial stage can leave files prettier-dirty and fail CI's `prettier --check`):

```bash
git add -A
git commit -m "build(dashboard): regenerate bundle for Code-tab icons + explainer"
```

- [ ] **Step 7: Final confirmation**

Run: `git status`
Expected: clean working tree. Confirm `../src/serena/resources/dashboard/` changes are committed.

---

## Self-Review notes (author)

- **Spec coverage:** Folder icons open/closed (Task 2) ✓; file icons by type + special filenames (Task 1, `fileIcons.ts`) ✓; indent guides + spinner loading (Task 2) ✓; `?` toolbar popover with all-pane + diagnostics-caveat explainer naming the LSP methods (Tasks 3–4) ✓; reusable Popover primitive (Task 3) ✓; no backend change ✓; build-output contract (Task 5) ✓. No diagnostic-badge work (correctly excluded).
- **Type consistency:** `getFileIconMeta(name, kind, open)` signature is identical across `fileIcons.ts`, its test, and the `FileTree` call site. `Popover` prop names (`label`, `icon`, `iconSize`, `title`, `align`, `children`) match between the component, its test, and the `CodePage` usage.
- **Placeholder scan:** no TBD/TODO; every code step shows full code; every run step gives an expected result.
