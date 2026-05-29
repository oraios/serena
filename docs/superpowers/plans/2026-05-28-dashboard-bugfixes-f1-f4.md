# Dashboard Bug-fixes F1–F4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four UI defects in the Svelte dashboard found during manual testing — silent editor load-errors (F1), logs not tailing on entry (F2), missing active-tab a11y signal (F3), and a missing modal title (F4).

**Architecture:** Frontend-only changes in `dashboard/`. Reuse existing primitives: the `runMutation` normalizer for the two backend failure channels, the `Modal` component's `error`/`title` props, and the existing scroll math in `LogViewer`. The Flask backend (`src/serena/dashboard.py`) is a frozen contract — untouched. Each fix is one or two files plus its existing Vitest spec. TDD throughout.

**Tech Stack:** Svelte 5 (runes) + TypeScript, Vite, Vitest + @testing-library/svelte (jsdom). Run all commands from `dashboard/`.

**Spec:** `docs/superpowers/specs/2026-05-28-dashboard-bugfixes-f1-f4-design.md`

## File map

- Modify: `dashboard/src/lib/api/types.ts` — add optional `status?`/`message?` to the two GET-load response interfaces (F1).
- Modify: `dashboard/src/components/modals/EditSerenaConfigModal.svelte` — load via `runMutation`, gate Save (F1).
- Modify: `dashboard/src/components/modals/EditMemoryModal.svelte` — load via `runMutation`, gate Save (F1).
- Modify: `dashboard/src/components/logs/LogViewer.svelte` — initial scroll-to-bottom (F2).
- Modify: `dashboard/src/components/shell/Header.svelte` — `aria-current="page"` on active tab (F3).
- Modify: `dashboard/src/components/modals/CreateMemoryModal.svelte` — add `title="Create Memory"` (F4).
- Modify/Create tests: `tests/edit-serena-config-modal.test.ts`, `tests/edit-memory-modal.test.ts`, `tests/log-viewer.test.ts`, `tests/header.test.ts` (new), `tests/create-memory-modal.test.ts`.
- Regenerate (final task): `src/serena/resources/dashboard/` (`index.html` + hashed `assets/`) via `npm run build`.

---

## Task 1: F1 — EditSerenaConfigModal surfaces load errors, blocks Save

**Files:**
- Modify: `dashboard/src/lib/api/types.ts:84-90`
- Modify: `dashboard/src/components/modals/EditSerenaConfigModal.svelte` (whole `<script>` + Save button + Modal `error` prop)
- Test: `dashboard/tests/edit-serena-config-modal.test.ts`

- [ ] **Step 1: Add the two failing tests**

Append these two `it` blocks inside the existing `describe('EditSerenaConfigModal', ...)` in `tests/edit-serena-config-modal.test.ts` (the file already imports `render, fireEvent, screen, waitFor`, `vi`, `stubFetchJson`; add `errBody` to the `./helpers` import):

```ts
  it('shows an error and disables Save when the config fails to load', async () => {
    stubFetchJson(errBody('Serena config file not found'));
    render(EditSerenaConfigModal, { props: { onclose: vi.fn() } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Serena config file not found');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('populates the textarea and enables Save when the config loads', async () => {
    stubFetchJson({ content: 'yaml: 1' });
    render(EditSerenaConfigModal, { props: { onclose: vi.fn() } });
    const textarea = await screen.findByRole('textbox');
    await waitFor(() => {
      if ((textarea as HTMLTextAreaElement).value !== 'yaml: 1') throw new Error('not loaded yet');
    });
    expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled();
  });
```

Update the import line at the top of the file to:

```ts
import { stubFetchJson, errBody } from './helpers';
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- edit-serena-config-modal`
Expected: the "shows an error and disables Save" test FAILS (no `alert` element appears, and Save is not disabled, because the current code swallows the error and leaves Save enabled).

- [ ] **Step 3: Add optional soft-error fields to the response type**

In `dashboard/src/lib/api/types.ts`, change the `ResponseGetSerenaConfig` interface (around line 88) to:

```ts
export interface ResponseGetSerenaConfig {
  content: string;
  status?: string;
  message?: string;
}
```

- [ ] **Step 4: Rewrite EditSerenaConfigModal to load via runMutation and gate Save**

Replace the entire contents of `dashboard/src/components/modals/EditSerenaConfigModal.svelte` with:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getSerenaConfig, saveSerenaConfig } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { onclose }: { onclose: () => void } = $props();
  let content = $state('');
  let initialContent = $state('');
  let loaded = $state(false);
  let loadError = $state('');
  const dirty = $derived(content !== initialContent);
  const action = createModalAction();
  async function load() {
    const res = await runMutation(() => getSerenaConfig());
    if (!res.ok) {
      loadError = res.message ?? 'Failed to load configuration.';
      return;
    }
    const loadedContent = res.data?.content ?? '';
    content = loadedContent;
    initialContent = loadedContent;
    loaded = true;
  }
  onMount(() => {
    void load();
  });
  function requestClose() {
    if (confirmDiscard(dirty)) onclose();
  }
  function save() {
    void action.run(() => runMutation(() => saveSerenaConfig(content)), onclose);
  }
</script>

<Modal
  open={true}
  title="Global Serena Configuration"
  error={loadError || action.error}
  onclose={requestClose}
>
  <p class="modal-hint">
    Note: Changes to the configuration only take effect after Serena is restarted.
  </p>
  <textarea class="modal-textarea" aria-label="Configuration" rows="20" bind:value={content}
  ></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={requestClose}>Cancel</Button>
    <Button disabled={!loaded || action.busy} onclick={save}>Save</Button>
  </div>
</Modal>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm test -- edit-serena-config-modal`
Expected: all three tests in the file PASS (the new two plus the existing dirty-discard test, which still loads via the success-shaped stub).

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/api/types.ts dashboard/src/components/modals/EditSerenaConfigModal.svelte dashboard/tests/edit-serena-config-modal.test.ts
git commit -m "fix(dashboard): surface config-editor load errors; block Save until loaded (F1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: F1 — EditMemoryModal surfaces load errors, blocks Save

**Files:**
- Modify: `dashboard/src/lib/api/types.ts:84-87`
- Modify: `dashboard/src/components/modals/EditMemoryModal.svelte` (onMount load + Modal `error` prop + Save button)
- Test: `dashboard/tests/edit-memory-modal.test.ts`

- [ ] **Step 1: Add the failing test**

Append this `it` block inside the existing `describe('EditMemoryModal', ...)` in `tests/edit-memory-modal.test.ts`, and add `errBody` to the `./helpers` import (`import { stubFetchJson, errBody } from './helpers';`):

```ts
  it('shows an error and disables Save when the memory fails to load', async () => {
    stubFetchJson(errBody('memory not found'));
    render(EditMemoryModal, { props: { name: 'core', onclose: vi.fn() } });
    expect(await screen.findByRole('alert')).toHaveTextContent('memory not found');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- edit-memory-modal`
Expected: the new test FAILS — current code does `(await getMemory(name)).content ?? ''`, showing no alert and leaving Save enabled.

- [ ] **Step 3: Add optional soft-error fields to ResponseGetMemory**

In `dashboard/src/lib/api/types.ts`, change the `ResponseGetMemory` interface (around line 84) to:

```ts
export interface ResponseGetMemory {
  content: string;
  memory_name: string;
  status?: string;
  message?: string;
}
```

- [ ] **Step 4: Update EditMemoryModal load + Save gating**

In `dashboard/src/components/modals/EditMemoryModal.svelte`:

(a) Add two state declarations immediately after the `let initialContent = $state('');` line (currently line 17):

```ts
  let loaded = $state(false);
  let loadError = $state('');
```

(b) Replace the existing `onMount(() => { ... });` block (currently lines 23-31) with:

```ts
  onMount(() => {
    void (async () => {
      const res = await runMutation(() => getMemory(name));
      if (!res.ok) {
        loadError = res.message ?? 'Failed to load memory.';
        return;
      }
      const loadedContent = res.data?.content ?? '';
      content = loadedContent;
      initialContent = loadedContent;
      loaded = true;
    })();
  });
```

(c) Change the `<Modal>` opening tag's `error` prop (currently `error={action.error || renameAction.error}`) to include the load error:

```svelte
<Modal open={true} error={loadError || action.error || renameAction.error} onclose={requestClose}>
```

(d) Change the Save `<Button>` (currently `<Button disabled={action.busy} onclick={save}>Save</Button>`) to:

```svelte
    <Button disabled={!loaded || action.busy} onclick={save}>Save</Button>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- edit-memory-modal`
Expected: all tests in the file PASS (the new load-error test plus the existing dirty-discard test, which loads via the success-shaped stub and so sets `loaded = true`).

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/api/types.ts dashboard/src/components/modals/EditMemoryModal.svelte dashboard/tests/edit-memory-modal.test.ts
git commit -m "fix(dashboard): surface memory-editor load errors; block Save until loaded (F1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: F2 — LogViewer tails the newest line on first load

**Files:**
- Modify: `dashboard/src/components/logs/LogViewer.svelte:6-14` (the `$effect`)
- Test: `dashboard/tests/log-viewer.test.ts`

- [ ] **Step 1: Add the failing tests**

Append these two `it` blocks inside the existing `describe('LogViewer', ...)` in `tests/log-viewer.test.ts`. jsdom has no layout engine, so the tests install fake `scrollHeight`/`clientHeight` and a `scrollTop` spy on the container before flushing the deferred microtask:

```ts
  it('scrolls to the bottom on the first non-empty render', async () => {
    const { container } = render(LogViewer, {
      props: { lines: ['INFO a', 'INFO b'], toolNames: [] },
    });
    const el = container.querySelector('.log-container') as HTMLElement;
    let scrollTopValue = 0;
    Object.defineProperty(el, 'scrollHeight', { configurable: true, value: 500 });
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 100 });
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => scrollTopValue,
      set: (v) => {
        scrollTopValue = v;
      },
    });
    // Let the effect's queued microtask run now that the metrics are in place.
    await new Promise((r) => setTimeout(r, 0));
    expect(scrollTopValue).toBe(500);
  });

  it('does not force-scroll when the user has scrolled up', async () => {
    const { container, rerender } = render(LogViewer, {
      props: { lines: ['INFO a'], toolNames: [] },
    });
    const el = container.querySelector('.log-container') as HTMLElement;
    let scrollTopValue = 0;
    Object.defineProperty(el, 'scrollHeight', { configurable: true, value: 500 });
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 100 });
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => scrollTopValue,
      set: (v) => {
        scrollTopValue = v;
      },
    });
    await new Promise((r) => setTimeout(r, 0)); // initial scroll fires once
    scrollTopValue = 0; // simulate the user scrolling back to the top
    await rerender({ lines: ['INFO a', 'INFO b', 'INFO c'], toolNames: [] });
    await new Promise((r) => setTimeout(r, 0));
    expect(scrollTopValue).toBe(0); // sticky logic must NOT yank to the bottom
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- log-viewer`
Expected: "scrolls to the bottom on the first non-empty render" FAILS — the current effect computes `atBottom` from the (defined) metrics: `500 - 0 - 100 = 400`, which is not `< 40`, so it never scrolls and `scrollTopValue` stays `0`.

- [ ] **Step 3: Add the one-shot initial scroll to the effect**

Replace the `<script>` block of `dashboard/src/components/logs/LogViewer.svelte` (lines 1-15) with:

```svelte
<script lang="ts">
  import { detectLevel, highlightTools } from '$lib/format';
  let { lines, toolNames }: { lines: string[]; toolNames: string[] } = $props();
  let el = $state<HTMLDivElement | null>(null);
  // Tracks whether we've performed the unconditional first scroll-to-bottom yet.
  // Per-instance: re-entering the Logs view remounts this component, so we tail
  // the newest line again on each entry.
  let didInitialScroll = false;

  $effect(() => {
    void lines.length; // re-run when new lines arrive
    if (!el || lines.length === 0) return;
    if (!didInitialScroll) {
      // Initial load: jump to the newest line unconditionally (legacy parity).
      didInitialScroll = true;
      queueMicrotask(() => {
        if (el) el.scrollTop = el.scrollHeight;
      });
      return;
    }
    // Subsequent updates: only stay pinned if the user is already at the bottom.
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom)
      queueMicrotask(() => {
        if (el) el.scrollTop = el.scrollHeight;
      });
  });
</script>
```

Leave the markup (the `<div bind:this={el} class="log-container">…`) and the `<style>` block below it unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- log-viewer`
Expected: all three tests in the file PASS (the render test, the new initial-scroll test, and the new sticky test).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/logs/LogViewer.svelte dashboard/tests/log-viewer.test.ts
git commit -m "fix(dashboard): logs viewer tails newest line on first load (F2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: F3 — Active view tab exposes aria-current="page"

**Files:**
- Modify: `dashboard/src/components/shell/Header.svelte:29-46` (the three tab buttons)
- Test: `dashboard/tests/header.test.ts` (new)

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/header.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Header from '../src/components/shell/Header.svelte';
import { stubFetchJson } from './helpers';

describe('Header', () => {
  it('marks the active view tab with aria-current="page"', () => {
    stubFetchJson({}); // BannerCarousel manifest fetch -> empty, no banners
    render(Header, { props: { active: 'logs', onnavigate: vi.fn(), onshutdown: vi.fn() } });
    expect(screen.getByRole('button', { name: 'Logs' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Overview' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: 'Stats' })).not.toHaveAttribute('aria-current');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- header`
Expected: FAILS — the Logs button has no `aria-current` attribute yet.

- [ ] **Step 3: Add aria-current to each tab button**

In `dashboard/src/components/shell/Header.svelte`, add an `aria-current` attribute to each of the three tab buttons. The Overview button (lines 29-34) becomes:

```svelte
      <button
        type="button"
        class="header-tab"
        class:active={active === 'overview'}
        aria-current={active === 'overview' ? 'page' : undefined}
        onclick={() => onnavigate('overview')}>Overview</button
      >
```

The Logs button becomes:

```svelte
      <button
        type="button"
        class="header-tab"
        class:active={active === 'logs'}
        aria-current={active === 'logs' ? 'page' : undefined}
        onclick={() => onnavigate('logs')}>Logs</button
      >
```

The Stats button becomes:

```svelte
      <button
        type="button"
        class="header-tab"
        class:active={active === 'stats'}
        aria-current={active === 'stats' ? 'page' : undefined}
        onclick={() => onnavigate('stats')}>Stats</button
      >
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- header`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/shell/Header.svelte dashboard/tests/header.test.ts
git commit -m "fix(dashboard): mark active view tab with aria-current=page (F3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: F4 — Create Memory modal has a title heading

**Files:**
- Modify: `dashboard/src/components/modals/CreateMemoryModal.svelte:26`
- Test: `dashboard/tests/create-memory-modal.test.ts`

- [ ] **Step 1: Write the failing test**

Append this `it` block inside the existing `describe('CreateMemoryModal', ...)` in `tests/create-memory-modal.test.ts`:

```ts
  it('renders a "Create Memory" title heading', () => {
    stubFetchJson(errBody('nope'));
    render(CreateMemoryModal, {
      props: { projectName: 'serena', onclose: vi.fn(), oncreated: vi.fn() },
    });
    expect(screen.getByRole('heading', { name: 'Create Memory' })).toBeInTheDocument();
  });
```

(The file already imports `stubFetchJson, errBody`, `vi`, `render`, `screen`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- create-memory-modal`
Expected: FAILS — the modal currently renders no heading, so no element with role `heading` and name "Create Memory" exists.

- [ ] **Step 3: Add the title prop**

In `dashboard/src/components/modals/CreateMemoryModal.svelte`, change the `<Modal>` opening tag (line 26) from:

```svelte
<Modal open={true} error={action.error} {onclose}>
```

to:

```svelte
<Modal open={true} title="Create Memory" error={action.error} {onclose}>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- create-memory-modal`
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/modals/CreateMemoryModal.svelte dashboard/tests/create-memory-modal.test.ts
git commit -m "fix(dashboard): add title heading to Create Memory modal (F4)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Type-check, format, rebuild artifact, commit build output

**Files:**
- Regenerate: `src/serena/resources/dashboard/index.html` + `src/serena/resources/dashboard/assets/*`

- [ ] **Step 1: Type-check**

Run: `npm run check`
Expected: `0 ERRORS`. (Up to 2 pre-existing `state_referenced_locally` WARNINGS in `Collapsible.svelte`/`Combobox.svelte` are acceptable — they are documented in `dashboard/CLAUDE.md`.) If new errors appear, fix them before continuing.

- [ ] **Step 2: Run the full test suite**

Run: `npm test`
Expected: all test files pass (the prior 71 tests plus the ~6 new assertions added in Tasks 1–5).

- [ ] **Step 3: Format**

Run: `npm run format`
Expected: prettier rewrites any unformatted files. Re-run `npm test` if it touched source to confirm still green.

- [ ] **Step 4: Rebuild the shipped artifact**

Run: `npm run build`
Expected: build succeeds; `../src/serena/resources/dashboard/index.html` and hashed `assets/` are regenerated (`prebuild` clears `assets/` first).

- [ ] **Step 5: Stage ALL changes and commit**

A partial stage can leave files prettier-dirty and fail CI's `prettier --check`, so stage everything:

```bash
git add -A
git commit -m "build(dashboard): regenerate built assets for F1–F4 fixes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Final verification**

Run: `git status --porcelain`
Expected: clean (no unstaged/untracked changes under `dashboard/` or `src/serena/resources/dashboard/`). This satisfies the CI-enforced build-output contract.

---

## Self-review notes

- **Spec coverage:** F1 → Tasks 1 & 2 (both editors, types.ts, Save gating, error surfacing); F2 → Task 3; F3 → Task 4; F4 → Task 5; build-output contract (spec §5) → Task 6. All spec sections covered.
- **Type consistency:** `loaded`/`loadError` state names, `res.ok`/`res.message`/`res.data?.content` (from `MutationResult<T>` in `mutation.ts`), and the `ResponseGetSerenaConfig`/`ResponseGetMemory` field additions are used consistently across Tasks 1–2. `runMutation`'s generic constraint `T extends { status?: string; message?: string }` is satisfied by the type additions in Steps 1.3 / 2.3.
- **No placeholders:** every code step shows complete, copy-pasteable content; every run step has an exact command and expected result.
