# Dashboard Parity & Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the functional regressions and the chart bug found when comparing the new Svelte dashboard against the legacy jQuery one, restoring three legacy behaviours (execution cancel + Cancelled panel, Last Execution card, config labels/order) while keeping the redesign otherwise.

**Architecture:** Frontend-only changes under `dashboard/src/`. Cross-cutting fixes flow through three small shared helpers (`runMutation`, `confirmDiscard`, a `Modal` `error` prop) so no error/teardown logic is duplicated. The Flask backend in `src/serena/dashboard.py` is a frozen contract — unchanged. After code lands, `npm run build` regenerates the committed `src/serena/resources/dashboard/` bundle (CI fails on stale output).

**Tech Stack:** Svelte 5 (runes) + TypeScript + Vite; Vitest + @testing-library/svelte; Frappe Charts 1.6.2 (bundled); ESLint + Prettier; `svelte-check`.

**Conventions (verified in repo):**
- Run all commands from `dashboard/`. Single test file: `npx vitest run tests/<file>.test.ts`. Full: `npm test`. Types: `npm run check`. Format: `npm run format`.
- Logic tests import from `../src/lib/...`; component tests use `render` from `@testing-library/svelte`; fetch is stubbed with `vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(...), { status: 200 })))`.
- Endpoint helpers (`endpoints.ts`) **throw `ApiError` on non-2xx** but mutation failures arrive as **HTTP 200 with `{ status: 'error', message }`**. `runMutation` (Task 1) normalizes both.
- CSS uses tokens from `src/styles/tokens.css` (e.g. `--success`, `--log-error`, `--bg-card`, `--border`, `--space-*`, `--radius`, `--font-mono`). Never hardcode hex.

**File map:**
- Create: `dashboard/src/lib/api/mutation.ts`, `dashboard/src/lib/confirmDiscard.ts`, `dashboard/src/lib/title.ts`, `dashboard/src/lib/news.ts`, `dashboard/src/components/overview/CancelledExecutions.svelte`, and matching tests.
- Modify: `Modal.svelte`; modals `AddLanguageModal`, `RemoveLanguageModal`, `DeleteMemoryModal`, `CreateMemoryModal`, `EditMemoryModal`, `EditSerenaConfigModal`, `CancelExecutionModal`, `ModalHost`; stores `executions.svelte.ts`, `modal.svelte.ts`; `App.svelte`; overview `ConfigCard`, `LastExecution`, `ExecutionsQueue`, `OverviewPage`, `NewsSection`; stats `charts.ts`, `ChartPanel.svelte`, `StatsPage.svelte`, `StatsSummary.svelte`; tests `charts.test.ts`.

---

### Task 1: `runMutation` helper

**Files:**
- Create: `dashboard/src/lib/api/mutation.ts`
- Test: `dashboard/tests/mutation.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/mutation.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { runMutation } from '../src/lib/api/mutation';
import { ApiError } from '../src/lib/api/client';

describe('runMutation', () => {
  it('returns ok for a success body', async () => {
    const r = await runMutation(async () => ({ status: 'success' as const }));
    expect(r.ok).toBe(true);
  });

  it('returns the error message when the body reports status:error (HTTP 200 path)', async () => {
    const r = await runMutation(async () => ({ status: 'error' as const, message: 'boom' }));
    expect(r).toEqual({ ok: false, message: 'boom', data: { status: 'error', message: 'boom' } });
  });

  it('catches a thrown ApiError (non-2xx path)', async () => {
    const r = await runMutation(async () => {
      throw new ApiError(500, 'HTTP 500 for /x');
    });
    expect(r.ok).toBe(false);
    expect(r.message).toContain('HTTP 500');
  });

  it('exposes the resolved body as data for callers needing extra fields', async () => {
    const r = await runMutation(async () => ({ status: 'success' as const, was_cancelled: true }));
    expect(r.data).toEqual({ status: 'success', was_cancelled: true });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/mutation.test.ts`
Expected: FAIL — cannot find module `../src/lib/api/mutation`.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/src/lib/api/mutation.ts`:

```ts
import { ApiError } from './client';

export interface MutationResult<T> {
  ok: boolean;
  message?: string;
  data?: T;
}

/**
 * Run a mutation endpoint call and normalize both failure channels:
 * a thrown ApiError (non-2xx) AND a 200-OK body of { status: 'error', message }.
 */
export async function runMutation<T extends { status?: string; message?: string }>(
  fn: () => Promise<T>,
): Promise<MutationResult<T>> {
  try {
    const data = await fn();
    if (data && data.status === 'error') {
      return { ok: false, message: data.message ?? 'Request failed', data };
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : 'Request failed' };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && npx vitest run tests/mutation.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/api/mutation.ts dashboard/tests/mutation.test.ts
git commit -m "feat(dashboard): runMutation helper normalizing both API error channels"
```

---

### Task 2: `confirmDiscard` helper

**Files:**
- Create: `dashboard/src/lib/confirmDiscard.ts`
- Test: `dashboard/tests/confirmDiscard.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/confirmDiscard.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { confirmDiscard } from '../src/lib/confirmDiscard';

afterEach(() => vi.restoreAllMocks());

describe('confirmDiscard', () => {
  it('returns true without prompting when not dirty', () => {
    const spy = vi.spyOn(window, 'confirm');
    expect(confirmDiscard(false)).toBe(true);
    expect(spy).not.toHaveBeenCalled();
  });

  it('defers to window.confirm when dirty', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    expect(confirmDiscard(true)).toBe(true);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    expect(confirmDiscard(true)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/confirmDiscard.test.ts`
Expected: FAIL — cannot find module `../src/lib/confirmDiscard`.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/src/lib/confirmDiscard.ts`:

```ts
/** Returns true if it's safe to close: not dirty, or the user confirmed discarding. */
export function confirmDiscard(isDirty: boolean): boolean {
  return !isDirty || window.confirm('You have unsaved changes. Discard them?');
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && npx vitest run tests/confirmDiscard.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/confirmDiscard.ts dashboard/tests/confirmDiscard.test.ts
git commit -m "feat(dashboard): confirmDiscard guard for unsaved-changes prompts"
```

---

### Task 3: `Modal` error prop + refactor `AddLanguageModal` onto it

**Files:**
- Modify: `dashboard/src/components/common/Modal.svelte`
- Modify: `dashboard/src/components/modals/AddLanguageModal.svelte`
- Test: `dashboard/tests/add-language-modal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/add-language-modal.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import AddLanguageModal from '../src/components/modals/AddLanguageModal.svelte';

afterEach(() => vi.restoreAllMocks());

function mockFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (String(url).includes('/get_available_languages')) {
        return Promise.resolve(new Response(JSON.stringify({ languages: ['go'] }), { status: 200 }));
      }
      // /add_language fails with a 200-OK error body
      return Promise.resolve(
        new Response(JSON.stringify({ status: 'error', message: 'unknown language' }), {
          status: 200,
        }),
      );
    }),
  );
}

describe('AddLanguageModal error handling', () => {
  it('shows the error inline and stays open when add fails', async () => {
    mockFetch();
    const onclose = vi.fn();
    render(AddLanguageModal, { props: { projectName: 'serena', onclose } });
    // Select an option, then submit.
    await fireEvent.click(await screen.findByText('go'));
    await fireEvent.click(screen.getByRole('button', { name: 'Add Language' }));
    expect(await screen.findByText('unknown language')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

> If the Combobox renders options differently and `findByText('go')` cannot select, set `selected` via the combobox's input: replace the click line with `await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });` then click the matching option. Verify by reading `src/components/common/Combobox.svelte` before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/add-language-modal.test.ts`
Expected: FAIL — the error text isn't rendered via the new shared prop yet (test asserts current behaviour still works; it fails only if wiring changed). If it passes as-is, proceed — the refactor must keep it passing.

- [ ] **Step 3: Add the `error` prop to `Modal.svelte`**

In `dashboard/src/components/common/Modal.svelte`, change the props destructure (currently lines 4-9) to add `error`:

```svelte
  let {
    open = false,
    title = '',
    error = '',
    onclose,
    children,
  }: {
    open?: boolean;
    title?: string;
    error?: string;
    onclose: () => void;
    children: Snippet;
  } = $props();
```

Then render the error block between the title and the children. Replace:

```svelte
      {#if title}<h3>{title}</h3>{/if}
      {@render children()}
```

with:

```svelte
      {#if title}<h3>{title}</h3>{/if}
      {#if error}<p class="modal-error">{error}</p>{/if}
      {@render children()}
```

Add this rule inside the `<style>` block:

```css
  .modal-error {
    color: var(--log-error);
    margin: 0 0 var(--space-3);
  }
```

- [ ] **Step 4: Refactor `AddLanguageModal.svelte` onto the shared prop + `runMutation`**

In `dashboard/src/components/modals/AddLanguageModal.svelte`:

Add the import (after line 7's endpoints import):

```svelte
  import { runMutation } from '$lib/api/mutation';
```

Replace the `add` function (lines 18-29) with:

```svelte
  async function add() {
    if (!selected) return;
    busy = true;
    error = '';
    const res = await runMutation(() => addLanguage(selected));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
```

Pass `error` to `Modal` and remove the inline error markup. Change the opening tag (line 32) to:

```svelte
<Modal open={true} title="Add Language" {error} {onclose}>
```

Delete the inline error line (line 41):

```svelte
  {#if error}<p class="error">{error}</p>{/if}
```

Delete the now-unused `.error` style rule (lines 58-60):

```css
  .error {
    color: var(--log-error);
  }
```

- [ ] **Step 5: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/add-language-modal.test.ts && npm run check`
Expected: test PASS; `svelte-check` reports 0 errors.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/common/Modal.svelte dashboard/src/components/modals/AddLanguageModal.svelte dashboard/tests/add-language-modal.test.ts
git commit -m "feat(dashboard): shared Modal error prop; AddLanguageModal uses runMutation"
```

---

### Task 4: Inline errors for Remove-language, Delete-memory, Create-memory modals

**Files:**
- Modify: `dashboard/src/components/modals/RemoveLanguageModal.svelte`
- Modify: `dashboard/src/components/modals/DeleteMemoryModal.svelte`
- Modify: `dashboard/src/components/modals/CreateMemoryModal.svelte`
- Test: `dashboard/tests/delete-memory-modal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/delete-memory-modal.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import DeleteMemoryModal from '../src/components/modals/DeleteMemoryModal.svelte';

afterEach(() => vi.restoreAllMocks());

describe('DeleteMemoryModal error handling', () => {
  it('shows the error and stays open when delete fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'error', message: 'cannot delete' }), { status: 200 }),
      ),
    );
    const onclose = vi.fn();
    render(DeleteMemoryModal, { props: { name: 'core', onclose } });
    await fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(await screen.findByText('cannot delete')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/delete-memory-modal.test.ts`
Expected: FAIL — `onclose` is called (current modal closes regardless) and "cannot delete" is not rendered.

- [ ] **Step 3: Update `RemoveLanguageModal.svelte`**

Replace the entire `<script>` block (lines 1-10) with:

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { removeLanguage } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { language, onclose }: { language: string; onclose: () => void } = $props();
  let busy = $state(false);
  let error = $state('');
  async function confirm() {
    busy = true;
    error = '';
    const res = await runMutation(() => removeLanguage(language));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
</script>
```

Change the `<Modal>` open tag (line 12) to `<Modal open={true} {error} {onclose}>` and the OK button (line 16) to:

```svelte
    <Button disabled={busy} onclick={confirm}>{#if busy}<Spinner />{:else}OK{/if}</Button>
```

- [ ] **Step 4: Update `DeleteMemoryModal.svelte`**

Replace the `<script>` block (lines 1-10) with:

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { deleteMemory } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  let busy = $state(false);
  let error = $state('');
  async function confirm() {
    busy = true;
    error = '';
    const res = await runMutation(() => deleteMemory(name));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
</script>
```

Change the `<Modal>` open tag (line 12) to `<Modal open={true} {error} {onclose}>` and the OK button (line 16) to:

```svelte
    <Button variant="danger" disabled={busy} onclick={confirm}>{#if busy}<Spinner />{:else}OK{/if}</Button>
```

- [ ] **Step 5: Update `CreateMemoryModal.svelte`**

Add imports after line 5:

```svelte
  import Spinner from '../common/Spinner.svelte';
  import { runMutation } from '$lib/api/mutation';
```

Add state after line 12 (`const valid = ...`):

```svelte
  let busy = $state(false);
  let error = $state('');
```

Replace the `create` function (lines 13-17) with:

```svelte
  async function create() {
    if (!valid) return;
    busy = true;
    error = '';
    const res = await runMutation(() => saveMemory(name, ''));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    oncreated(name);
  }
```

Change the `<Modal>` open tag (line 20) to `<Modal open={true} {error} {onclose}>` and the Create button (line 33) to:

```svelte
    <Button disabled={!valid || busy} onclick={create}>{#if busy}<Spinner />{:else}Create{/if}</Button>
```

- [ ] **Step 6: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/delete-memory-modal.test.ts && npm run check`
Expected: test PASS; 0 type errors.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/modals/RemoveLanguageModal.svelte dashboard/src/components/modals/DeleteMemoryModal.svelte dashboard/src/components/modals/CreateMemoryModal.svelte dashboard/tests/delete-memory-modal.test.ts
git commit -m "feat(dashboard): inline errors for remove-language/delete-memory/create-memory modals"
```

---

### Task 5: `EditMemoryModal` — inline errors + unsaved-changes guard

**Files:**
- Modify: `dashboard/src/components/modals/EditMemoryModal.svelte`
- Test: `dashboard/tests/edit-memory-modal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/edit-memory-modal.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import EditMemoryModal from '../src/components/modals/EditMemoryModal.svelte';

afterEach(() => vi.restoreAllMocks());

describe('EditMemoryModal', () => {
  it('prompts before discarding unsaved edits and aborts close when declined', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: 'orig', memory_name: 'core' }), { status: 200 }),
      ),
    );
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onclose = vi.fn();
    render(EditMemoryModal, { props: { name: 'core', onclose } });
    const textarea = await screen.findByRole('textbox');
    await fireEvent.input(textarea, { target: { value: 'changed' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/edit-memory-modal.test.ts`
Expected: FAIL — no confirm prompt; `onclose` called.

- [ ] **Step 3: Implement guard + errors**

Replace the `<script>` block of `dashboard/src/components/modals/EditMemoryModal.svelte` (lines 1-35) with:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getMemory, saveMemory, renameMemory } from '$lib/api/endpoints';
  import { isValidMemoryName } from '$lib/validation';
  import { runMutation } from '$lib/api/mutation';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  // eslint-disable-next-line svelte/valid-compile
  let currentName = $state(name);
  let content = $state('');
  let initialContent = $state('');
  let busy = $state(false);
  let error = $state('');
  let renaming = $state(false);
  // eslint-disable-next-line svelte/valid-compile
  let renameValue = $state(name);
  const dirty = $derived(content !== initialContent);
  onMount(() => {
    void (async () => {
      // On failure the backend returns {status:'error', message} (HTTP 200) with no `content`;
      // fall back to an empty string so the textarea never binds to `undefined`.
      const loaded = (await getMemory(name)).content ?? '';
      content = loaded;
      initialContent = loaded;
    })();
  });

  function requestClose() {
    if (confirmDiscard(dirty)) onclose();
  }
  async function save() {
    busy = true;
    error = '';
    const res = await runMutation(() => saveMemory(currentName, content));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
  async function applyRename() {
    if (!isValidMemoryName(renameValue) || renameValue === currentName) {
      renaming = false;
      return;
    }
    const res = await runMutation(() => renameMemory(currentName, renameValue));
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    currentName = renameValue;
    renaming = false;
  }
</script>
```

Change the `<Modal>` open tag (line 37) to `<Modal open={true} {error} onclose={requestClose}>` and the Cancel button (line 65) to `<Button variant="secondary" onclick={requestClose}>Cancel</Button>`. Change the Save button (line 66) to:

```svelte
    <Button disabled={busy} onclick={save}>Save</Button>
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/edit-memory-modal.test.ts && npm run check`
Expected: PASS; 0 type errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/modals/EditMemoryModal.svelte dashboard/tests/edit-memory-modal.test.ts
git commit -m "feat(dashboard): EditMemoryModal inline errors + unsaved-changes guard"
```

---

### Task 6: `EditSerenaConfigModal` — inline errors + unsaved-changes guard

**Files:**
- Modify: `dashboard/src/components/modals/EditSerenaConfigModal.svelte`
- Test: `dashboard/tests/edit-serena-config-modal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/edit-serena-config-modal.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import EditSerenaConfigModal from '../src/components/modals/EditSerenaConfigModal.svelte';

afterEach(() => vi.restoreAllMocks());

describe('EditSerenaConfigModal', () => {
  it('prompts before discarding unsaved edits and aborts close when declined', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ content: 'yaml: 1' }), { status: 200 })),
    );
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onclose = vi.fn();
    render(EditSerenaConfigModal, { props: { onclose } });
    const textarea = await screen.findByRole('textbox');
    await fireEvent.input(textarea, { target: { value: 'yaml: 2' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/edit-serena-config-modal.test.ts`
Expected: FAIL — no prompt; `onclose` called.

- [ ] **Step 3: Implement guard + errors**

Replace the `<script>` block of `dashboard/src/components/modals/EditSerenaConfigModal.svelte` (lines 1-18) with:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getSerenaConfig, saveSerenaConfig } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { onclose }: { onclose: () => void } = $props();
  let content = $state('');
  let initialContent = $state('');
  let busy = $state(false);
  let error = $state('');
  const dirty = $derived(content !== initialContent);
  async function load() {
    const loaded = (await getSerenaConfig()).content;
    content = loaded;
    initialContent = loaded;
  }
  onMount(() => {
    void load();
  });
  function requestClose() {
    if (confirmDiscard(dirty)) onclose();
  }
  async function save() {
    busy = true;
    error = '';
    const res = await runMutation(() => saveSerenaConfig(content));
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
</script>
```

Change the `<Modal>` open tag (line 20) to `<Modal open={true} title="Global Serena Configuration" {error} onclose={requestClose}>`. Change the Cancel button (line 26) to `<Button variant="secondary" onclick={requestClose}>Cancel</Button>` and the Save button (line 27) to `<Button disabled={busy} onclick={save}>Save</Button>`.

- [ ] **Step 4: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/edit-serena-config-modal.test.ts && npm run check`
Expected: PASS; 0 type errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/modals/EditSerenaConfigModal.svelte dashboard/tests/edit-serena-config-modal.test.ts
git commit -m "feat(dashboard): EditSerenaConfigModal inline errors + unsaved-changes guard"
```

---

### Task 7: Restore full legacy execution-cancel UX + Cancelled Executions panel

This is one cohesive change across the executions store, the cancel modal, modal state, ModalHost, App handler, OverviewPage, ExecutionsQueue, and a new CancelledExecutions panel. They are coupled by the handler signature (`oncancelexecution` now passes the full `QueuedExecution`), so they change together to keep the build green.

**Files:**
- Modify: `dashboard/src/lib/stores/executions.svelte.ts`
- Modify: `dashboard/src/lib/stores/modal.svelte.ts`
- Modify: `dashboard/src/components/modals/CancelExecutionModal.svelte`
- Modify: `dashboard/src/components/modals/ModalHost.svelte`
- Modify: `dashboard/src/App.svelte`
- Modify: `dashboard/src/components/overview/OverviewPage.svelte`
- Modify: `dashboard/src/components/overview/ExecutionsQueue.svelte`
- Create: `dashboard/src/components/overview/CancelledExecutions.svelte`
- Test: `dashboard/tests/executions-store.test.ts` (extend), `dashboard/tests/executions-queue.test.ts` (new)

- [ ] **Step 1: Write the failing store test (extend existing file)**

Append to `dashboard/tests/executions-store.test.ts` (after the existing `describe` block, before EOF):

```ts
describe('executions store: cancel', () => {
  it('records a cancelled execution on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'success', was_cancelled: true, message: '' }), {
          status: 200,
        }),
      ),
    );
    const store = createExecutionsStore();
    const r = await store.cancel(exec({ task_id: 7, name: 't', is_running: true }));
    expect(r.ok).toBe(true);
    expect(store.cancelled.map((c) => c.task_id)).toEqual([7]);
    expect(store.cancelError).toBe('');
  });

  it('sets cancelError and does not record on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'error', was_cancelled: false, message: 'too late' }), {
          status: 200,
        }),
      ),
    );
    const store = createExecutionsStore();
    const r = await store.cancel(exec({ task_id: 8 }));
    expect(r.ok).toBe(false);
    expect(store.cancelError).toBe('too late');
    expect(store.cancelled).toEqual([]);
  });
});
```

- [ ] **Step 2: Write the failing queue component test**

Create `dashboard/tests/executions-queue.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import ExecutionsQueue from '../src/components/overview/ExecutionsQueue.svelte';
import type { QueuedExecution } from '../src/lib/api/types';

function exec(over: Partial<QueuedExecution>): QueuedExecution {
  return { task_id: 1, is_running: false, name: 'task', finished_successfully: true, logged: true, ...over };
}

describe('ExecutionsQueue', () => {
  it('renders a cancel button for a queued (non-running) item and emits the execution', async () => {
    const item = exec({ task_id: 9, is_running: false, name: 'queued-task' });
    const oncancelexecution = vi.fn();
    render(ExecutionsQueue, { props: { items: [item], cancelError: '', oncancelexecution } });
    await fireEvent.click(screen.getByTestId('cancel-btn'));
    expect(oncancelexecution).toHaveBeenCalledWith(item);
  });

  it('shows the cancel error when set', () => {
    render(ExecutionsQueue, {
      props: { items: [exec({})], cancelError: 'too late', oncancelexecution: vi.fn() },
    });
    expect(screen.getByText('too late')).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `cd dashboard && npx vitest run tests/executions-store.test.ts tests/executions-queue.test.ts`
Expected: FAIL — `store.cancel` signature/`cancelled`/`cancelError` missing; queue renders no cancel button for non-running items.

- [ ] **Step 4: Update the executions store**

Replace the entire `dashboard/src/lib/stores/executions.svelte.ts` with:

```ts
import { fetchQueuedExecutions, fetchLastExecution, cancelExecution } from '$lib/api/endpoints';
import { runMutation } from '$lib/api/mutation';
import type { QueuedExecution } from '$lib/api/types';

export function createExecutionsStore() {
  let queued = $state<QueuedExecution[]>([]);
  let last = $state<QueuedExecution | null>(null);
  // Client-side list of cancelled/abandoned tasks for the Cancelled Executions panel
  // (legacy behaviour: there is no backend endpoint for this).
  let cancelled = $state<QueuedExecution[]>([]);
  let cancelError = $state('');

  return {
    get queued() {
      return queued;
    },
    get last() {
      return last;
    },
    get cancelled() {
      return cancelled;
    },
    get cancelError() {
      return cancelError;
    },
    async pollQueued() {
      queued = (await fetchQueuedExecutions()).queued_executions;
    },
    async pollLast() {
      // Only surface user-facing (logged) executions. The backend runs internal tasks
      // (e.g. _get_config_overview every second) with logged=False; without this filter
      // the "Last Execution" panel would almost always show an internal task. Matches legacy.
      const latest = (await fetchLastExecution()).last_execution;
      last = latest && latest.logged ? latest : null;
    },
    async cancel(execution: QueuedExecution) {
      cancelError = '';
      const res = await runMutation(() => cancelExecution(execution.task_id));
      if (!res.ok) {
        cancelError = res.message ?? 'Failed to cancel execution';
        return res;
      }
      cancelled = [...cancelled, execution];
      return res;
    },
  };
}

export const executions = createExecutionsStore();
```

- [ ] **Step 5: Update the modal store state type**

In `dashboard/src/lib/stores/modal.svelte.ts`, add the import at the top and change the `cancelExecution` variant:

```ts
import type { QueuedExecution } from '$lib/api/types';

export type ModalState =
  | { kind: 'shutdown' }
  | { kind: 'cancelExecution'; execution: QueuedExecution }
  | { kind: 'addLanguage' }
  | { kind: 'removeLanguage'; language: string }
  | { kind: 'editMemory'; name: string }
  | { kind: 'deleteMemory'; name: string }
  | { kind: 'createMemory' }
  | { kind: 'editSerenaConfig' };
```

(The `createModalStore`/`modal` export below is unchanged.)

- [ ] **Step 6: Update `CancelExecutionModal.svelte`**

Replace the whole file with:

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import type { QueuedExecution } from '$lib/api/types';
  let { execution, onclose }: { execution: QueuedExecution; onclose: () => void } = $props();
  let busy = $state(false);
  let error = $state('');
  async function confirm() {
    busy = true;
    error = '';
    const res = await executions.cancel(execution);
    busy = false;
    if (!res.ok) {
      error = res.message ?? 'Failed';
      return;
    }
    onclose();
  }
</script>

<Modal open={true} {error} {onclose}>
  <p class="modal-prompt">
    Are you sure? The execution will continue running until timeout, it will simply no longer be in
    the queue. Abandoning a running execution is only advised as a measure for unblocking Serena.
  </p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={busy} onclick={confirm}>{#if busy}<Spinner />{:else}OK{/if}</Button>
  </div>
</Modal>

<style>
  .modal-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: flex-end;
    margin-top: var(--space-4);
  }
</style>
```

- [ ] **Step 7: Update `ModalHost.svelte`**

Change the `cancelExecution` branch (line 19) from `taskId={m.taskId}` to `execution={m.execution}`:

```svelte
  {:else if m.kind === 'cancelExecution'}<CancelExecutionModal
      execution={m.execution}
      onclose={close}
    />
```

- [ ] **Step 8: Update `App.svelte` handler (branch running vs queued)**

In `dashboard/src/App.svelte`, change the `oncancelexecution` prop passed to `OverviewPage` (line 65) to:

```svelte
          oncancelexecution={(ex) =>
            ex.is_running
              ? modal.open({ kind: 'cancelExecution', execution: ex })
              : void executions.cancel(ex)}
```

(`executions` and `modal` are already imported in `App.svelte`.)

- [ ] **Step 9: Update `ExecutionsQueue.svelte` (cancel for all items + cancelError)**

Replace the whole file with:

```svelte
<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  import Spinner from '../common/Spinner.svelte';
  let {
    items,
    cancelError = '',
    oncancelexecution,
  }: {
    items: QueuedExecution[];
    cancelError?: string;
    oncancelexecution: (_ex: QueuedExecution) => void;
  } = $props();

  const visible = $derived(items.filter((ex) => ex.logged));
</script>

{#if visible.length}
  <div class="executions">
    {#each visible as ex (ex.task_id)}
      <div class="execution-item" class:running={ex.is_running}>
        {#if ex.is_running}<Spinner />{/if}
        <span class="execution-name">{ex.name}</span>
        <button
          class="cancel-btn"
          aria-label="Cancel"
          data-testid="cancel-btn"
          onclick={() => oncancelexecution(ex)}>×</button
        >
      </div>
    {/each}
  </div>
{:else}
  <div class="no-stats-message">No queued executions.</div>
{/if}
{#if cancelError}<p class="cancel-error">{cancelError}</p>{/if}

<style>
  .execution-item {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: var(--space-1) var(--space-3);
    margin: 2px;
  }
  .execution-item.running {
    border-color: var(--accent);
  }
  .execution-name {
    font-family: var(--font-mono);
    font-size: 12px;
  }
  .cancel-btn {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-muted);
  }
  .cancel-error {
    color: var(--log-error);
    margin: var(--space-2) 0 0;
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
```

- [ ] **Step 10: Create `CancelledExecutions.svelte`**

Create `dashboard/src/components/overview/CancelledExecutions.svelte`:

```svelte
<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  let { items }: { items: QueuedExecution[] } = $props();
</script>

<div class="cancelled-list">
  {#each items as ex (ex.task_id)}
    <div class="cancelled-item" class:abandoned={ex.is_running}>
      <span class="icon">{ex.is_running ? '!' : '✕'}</span>
      <span class="name">{ex.name}</span>
      <span class="meta">{ex.is_running ? 'abandoned · ' : ''}#{ex.task_id}</span>
    </div>
  {/each}
</div>

<style>
  .cancelled-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) 0;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
  }
  .icon {
    display: inline-flex;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--bg-secondary-btn);
    color: var(--log-error);
    font-size: 10px;
  }
  .cancelled-item.abandoned .icon {
    color: var(--log-warning);
  }
  .meta {
    margin-left: auto;
    color: var(--text-muted);
  }
</style>
```

- [ ] **Step 11: Wire OverviewPage (cancelError + Cancelled panel + prop type)**

In `dashboard/src/components/overview/OverviewPage.svelte`:

Add the import after line 10 (`import LastExecution ...`):

```svelte
  import CancelledExecutions from './CancelledExecutions.svelte';
  import type { QueuedExecution } from '$lib/api/types';
```

Change the `oncancelexecution` prop type (line 29) from `(_id: number) => void` to `(_ex: QueuedExecution) => void`.

Replace the Executions Queue card (lines 54-56) with:

```svelte
      <Card title="Executions Queue">
        <ExecutionsQueue
          items={executions.queued}
          cancelError={executions.cancelError}
          {oncancelexecution}
        />
      </Card>
      {#if executions.cancelled.length}
        <Card title="Cancelled Executions">
          <CancelledExecutions items={executions.cancelled} />
        </Card>
      {/if}
```

- [ ] **Step 12: Run tests + typecheck**

Run: `cd dashboard && npx vitest run tests/executions-store.test.ts tests/executions-queue.test.ts && npm run check`
Expected: all PASS; 0 type errors.

- [ ] **Step 13: Commit**

```bash
git add dashboard/src/lib/stores/executions.svelte.ts dashboard/src/lib/stores/modal.svelte.ts dashboard/src/components/modals/CancelExecutionModal.svelte dashboard/src/components/modals/ModalHost.svelte dashboard/src/App.svelte dashboard/src/components/overview/OverviewPage.svelte dashboard/src/components/overview/ExecutionsQueue.svelte dashboard/src/components/overview/CancelledExecutions.svelte dashboard/tests/executions-store.test.ts dashboard/tests/executions-queue.test.ts
git commit -m "feat(dashboard): restore legacy execution cancel + Cancelled Executions panel"
```

---

### Task 8: `charts.ts` — replace grouped bar with single-series builder

**Files:**
- Modify: `dashboard/src/lib/charts.ts`
- Modify: `dashboard/tests/charts.test.ts`

- [ ] **Step 1: Update the failing test first**

Replace the whole `dashboard/tests/charts.test.ts` with:

```ts
import { describe, it, expect } from 'vitest';
import { toPieData, toSingleSeriesBar } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
  b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
};

describe('charts data', () => {
  it('builds pie data for a chosen metric, sorted descending', () => {
    const pie = toPieData(stats, 'num_times_called');
    expect(pie.labels).toEqual(['b', 'a']);
    expect(pie.datasets[0].values).toEqual([8, 2]);
  });
  it('builds a single-series bar for one token metric, sorted descending', () => {
    const bar = toSingleSeriesBar(stats, 'output_tokens', 'Output Tokens');
    expect(bar.labels).toEqual(['b', 'a']);
    expect(bar.datasets).toHaveLength(1);
    expect(bar.datasets[0].name).toBe('Output Tokens');
    expect(bar.datasets[0].values).toEqual([20, 5]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/charts.test.ts`
Expected: FAIL — `toSingleSeriesBar` is not exported.

- [ ] **Step 3: Update `charts.ts`**

In `dashboard/src/lib/charts.ts`, replace `toGroupedBarData` (lines 20-29) with:

```ts
export function toSingleSeriesBar(
  stats: ToolStats,
  key: 'input_tokens' | 'output_tokens',
  name: string,
): FrappeData {
  const entries = sortedEntries(stats, key);
  return {
    labels: entries.map(([n]) => n),
    datasets: [{ name, values: entries.map(([, s]) => s[key]) }],
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && npx vitest run tests/charts.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/charts.ts dashboard/tests/charts.test.ts
git commit -m "feat(dashboard): single-series bar builder; drop grouped token bar"
```

---

### Task 9: `ChartPanel` — value labels + fix `removeChild` teardown error

**Files:**
- Modify: `dashboard/src/components/stats/ChartPanel.svelte`

- [ ] **Step 1: Add `valuesOverPoints` prop and guarded teardown**

Replace the `<script>` block of `dashboard/src/components/stats/ChartPanel.svelte` (lines 1-35) with:

```svelte
<script lang="ts">
  import { Chart } from 'frappe-charts';
  import type { FrappeData } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  let {
    title,
    data,
    type,
    valuesOverPoints = false,
  }: {
    title: string;
    data: FrappeData;
    type: 'pie' | 'percentage' | 'bar';
    valuesOverPoints?: boolean;
  } = $props();
  let el = $state<HTMLDivElement | null>(null);

  function accent(): string {
    return (
      getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#eaa45d'
    );
  }

  $effect(() => {
    void theme.current;
    void data; // re-render on theme or data change
    if (!el) return;
    el.innerHTML = '';
    const chart = new Chart(el, {
      title,
      data,
      type,
      height: type === 'bar' ? 240 : 220,
      colors: [accent(), '#6aa3d8', '#7fb77e', '#d88c8c', '#b39ddb', '#e0a458'],
      valuesOverPoints: valuesOverPoints ? 1 : 0,
    });
    return () => {
      // Frappe's destroy() can throw "removeChild ... not a child" when Svelte has already
      // torn down the container node; swallow that specific teardown race.
      try {
        chart.destroy();
      } catch {
        /* frappe removeChild race on teardown */
      }
    };
  });
</script>
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard && npm run check`
Expected: 0 type errors. (The `valuesOverPoints` option is accepted by the local ambient `frappe-charts` declaration at `src/types/frappe-charts.d.ts`; if `svelte-check` flags an unknown property, add `valuesOverPoints?: number;` to the `ChartArgs`/options interface in that declaration file in this step.)

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/stats/ChartPanel.svelte
git commit -m "fix(dashboard): guard chart teardown; support on-bar value labels"
```

---

### Task 10: `StatsPage` — three pies + two single-series bar charts

**Files:**
- Modify: `dashboard/src/components/stats/StatsPage.svelte`

- [ ] **Step 1: Update imports and chart markup**

In `dashboard/src/components/stats/StatsPage.svelte`, change the charts import (line 4):

```svelte
  import { toPieData, toSingleSeriesBar } from '$lib/charts';
```

Replace the `{#if hasStats}` chart block (lines 19-30) with:

```svelte
{#if hasStats}
  <StatsSummary stats={stats.stats} />
  <div class="estimator-name">Token estimator: {stats.estimator}</div>
  <div class="charts-grid">
    <ChartPanel title="Tool Calls" type="pie" data={toPieData(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" type="pie" data={toPieData(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" type="pie" data={toPieData(stats.stats, 'output_tokens')} />
  </div>
  <div class="charts-bars">
    <ChartPanel
      title="Input Tokens (by tool)"
      type="bar"
      valuesOverPoints
      data={toSingleSeriesBar(stats.stats, 'input_tokens', 'Input Tokens')}
    />
    <ChartPanel
      title="Output Tokens (by tool)"
      type="bar"
      valuesOverPoints
      data={toSingleSeriesBar(stats.stats, 'output_tokens', 'Output Tokens')}
    />
  </div>
{:else}
  <div class="no-stats-message">No tool stats collected yet.</div>
{/if}
```

Replace the `.charts-container` style rules (lines 38-46) with:

```css
  .charts-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  .charts-bars {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  @media (max-width: 1000px) {
    .charts-grid {
      grid-template-columns: 1fr;
    }
  }
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard && npm run check`
Expected: 0 type errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/stats/StatsPage.svelte
git commit -m "feat(dashboard): split token bar into readable per-series charts"
```

---

### Task 11: `StatsSummary` — add Total Tokens row

**Files:**
- Modify: `dashboard/src/components/stats/StatsSummary.svelte`
- Test: `dashboard/tests/stats-summary.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/stats-summary.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StatsSummary from '../src/components/stats/StatsSummary.svelte';

describe('StatsSummary', () => {
  it('shows a Total tokens row equal to input + output', () => {
    render(StatsSummary, {
      props: {
        stats: {
          a: { num_times_called: 1, input_tokens: 10, output_tokens: 5 },
          b: { num_times_called: 2, input_tokens: 40, output_tokens: 20 },
        },
      },
    });
    expect(screen.getByText('Total tokens')).toBeInTheDocument();
    expect(screen.getByTestId('total-tokens')).toHaveTextContent('75');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/stats-summary.test.ts`
Expected: FAIL — no "Total tokens" row / `total-tokens` testid.

- [ ] **Step 3: Add the row**

In `dashboard/src/components/stats/StatsSummary.svelte`, replace the `<tbody>` (lines 17-21) with:

```svelte
  <tbody>
    <tr><td>Total calls</td><td>{totals.calls}</td></tr>
    <tr><td>Total input tokens</td><td>{totals.input}</td></tr>
    <tr><td>Total output tokens</td><td>{totals.output}</td></tr>
    <tr><td>Total tokens</td><td data-testid="total-tokens">{totals.input + totals.output}</td></tr>
  </tbody>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && npx vitest run tests/stats-summary.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/stats/StatsSummary.svelte dashboard/tests/stats-summary.test.ts
git commit -m "feat(dashboard): restore Total Tokens stats summary row"
```

---

### Task 12: `ConfigCard` — restore legacy labels/order, remove Client, tooltips, JetBrains mode

**Files:**
- Modify: `dashboard/src/components/overview/ConfigCard.svelte`
- Test: `dashboard/tests/config-card.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/config-card.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ConfigCard from '../src/components/overview/ConfigCard.svelte';
import type { ResponseConfigOverview } from '../src/lib/api/types';

function makeConfig(over: Partial<ResponseConfigOverview> = {}): ResponseConfigOverview {
  return {
    active_project: { name: 'serena', language: 'Python', path: '/x' },
    context: { name: 'claude-code', description: '', path: '/ctx' },
    modes: [{ name: 'editing', path: '/m1' }],
    active_tools: ['find_symbol'],
    tool_stats_summary: {},
    registered_projects: [],
    available_tools: [],
    available_modes: [],
    available_contexts: [],
    available_memories: [],
    jetbrains_mode: false,
    languages: ['python'],
    encoding: 'utf-8',
    current_client: 'claude',
    serena_version: '1.5.4',
    ...over,
  };
}

const cbs = {
  onaddlanguage: vi.fn(),
  onremovelanguage: vi.fn(),
  oneditconfig: vi.fn(),
  onopenmemory: vi.fn(),
  oncreatememory: vi.fn(),
  ondeletememory: vi.fn(),
};

describe('ConfigCard', () => {
  it('does not render a Client field', () => {
    render(ConfigCard, { props: { data: makeConfig(), ...cbs } });
    expect(screen.queryByText('Client')).toBeNull();
  });

  it('shows the JetBrains backend notice and hides Add Language in jetbrains mode', () => {
    render(ConfigCard, { props: { data: makeConfig({ jetbrains_mode: true }), ...cbs } });
    expect(screen.getByText('Using JetBrains backend')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Language' })).toBeNull();
  });

  it('shows Add Language when not in jetbrains mode', () => {
    render(ConfigCard, { props: { data: makeConfig(), ...cbs } });
    expect(screen.getByRole('button', { name: 'Add Language' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/config-card.test.ts`
Expected: FAIL — "Client" still rendered; no "Using JetBrains backend".

- [ ] **Step 3: Rewrite the config markup**

In `dashboard/src/components/overview/ConfigCard.svelte`, replace the `<div class="config-display">` block down to the end of the languages `config-row` (lines 24-53) with the restored legacy order (Version → Active Project → Languages inline → Context → Active Modes → File Encoding), tooltips, JetBrains handling, and no Client field:

```svelte
<div class="config-display">
  <div class="config-grid">
    <span class="config-label">Version</span>
    <span class="config-value">{data.serena_version}</span>

    <span class="config-label">Active Project</span>
    <span class="config-value">
      {#if data.active_project?.name && data.active_project?.path}
        <span title="Project configuration in {data.active_project.path}/.serena/project.yml"
          >{data.active_project.name}</span
        >
      {:else}
        {data.active_project?.name ?? 'None'}
      {/if}
    </span>

    <span class="config-label">Languages</span>
    <span class="config-value">
      {#if data.jetbrains_mode}
        Using JetBrains backend
      {:else}
        <span class="languages-cell">
          {#each data.languages as lang (lang)}
            <span class="lang-badge"
              >{lang}
              {#if data.languages.length > 1}
                <button
                  class="lang-remove"
                  aria-label="Remove {lang}"
                  onclick={() => onremovelanguage(lang)}>×</button
                >
              {/if}
            </span>
          {/each}
          {#if data.active_project?.name}
            <Button variant="secondary" onclick={onaddlanguage}>+ Add Language</Button>
          {/if}
        </span>
      {/if}
    </span>

    <span class="config-label">Context</span>
    <span class="config-value"><span title={data.context.path}>{data.context.name}</span></span>

    <span class="config-label">Active Modes</span>
    <span class="config-value">
      {#if data.modes.length}
        {#each data.modes as m, i (m.name)}<span title={m.path}>{m.name}</span
          >{#if i < data.modes.length - 1}, {/if}{/each}
      {:else}
        None
      {/if}
    </span>

    <span class="config-label">File Encoding</span>
    <span class="config-value">{data.encoding ?? 'N/A'}</span>
  </div>
```

(The `Collapsible` Active Tools / Memories blocks and the `config-footer` below this remain unchanged.)

In the `<style>` block, delete the now-unused `.config-row` rule (lines 113-119) and add a `.languages-cell` rule next to `.lang-badge`:

```css
  .languages-cell {
    display: inline-flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/config-card.test.ts && npm run check`
Expected: PASS (3 tests); 0 type errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/overview/ConfigCard.svelte dashboard/tests/config-card.test.ts
git commit -m "feat(dashboard): restore legacy config labels/order, tooltips, JetBrains mode; drop Client"
```

---

### Task 13: `LastExecution` — restore boxed status card with `#task_id`

**Files:**
- Modify: `dashboard/src/components/overview/LastExecution.svelte`
- Test: `dashboard/tests/last-execution.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/last-execution.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import LastExecution from '../src/components/overview/LastExecution.svelte';
import type { QueuedExecution } from '../src/lib/api/types';

function exec(over: Partial<QueuedExecution>): QueuedExecution {
  return { task_id: 5, is_running: false, name: 'init', finished_successfully: true, logged: true, ...over };
}

describe('LastExecution', () => {
  it('renders the status word, name, and #task_id for a success', () => {
    render(LastExecution, { props: { execution: exec({ task_id: 5, finished_successfully: true }) } });
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    expect(screen.getByText('init')).toBeInTheDocument();
    expect(screen.getByText('#5')).toBeInTheDocument();
  });

  it('renders Failed for an unsuccessful, non-running execution', () => {
    render(LastExecution, {
      props: { execution: exec({ finished_successfully: false, is_running: false }) },
    });
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/last-execution.test.ts`
Expected: FAIL — current component renders "✓ success", no "#5".

- [ ] **Step 3: Rewrite the component**

Replace the whole `dashboard/src/components/overview/LastExecution.svelte` with:

```svelte
<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  let { execution }: { execution: QueuedExecution | null } = $props();
  const statusWord = $derived(
    !execution
      ? ''
      : execution.is_running
        ? 'Running'
        : execution.finished_successfully
          ? 'Succeeded'
          : 'Failed',
  );
  const icon = $derived(
    !execution ? '' : execution.is_running ? '…' : execution.finished_successfully ? '✓' : '✗',
  );
</script>

{#if execution}
  <div
    class="last-exec"
    class:ok={execution.finished_successfully && !execution.is_running}
    class:fail={!execution.finished_successfully && !execution.is_running}
    class:running={execution.is_running}
  >
    <span class="icon">{icon}</span>
    <div class="body">
      <span class="status">{statusWord}</span>
      <span class="execution-name">{execution.name}</span>
    </div>
    <span class="meta">#{execution.task_id}</span>
  </div>
{:else}
  <div class="no-stats-message">None yet.</div>
{/if}

<style>
  .last-exec {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .last-exec.ok {
    border-color: var(--success);
    background: color-mix(in srgb, var(--success) 8%, transparent);
  }
  .last-exec.fail {
    border-color: var(--log-error);
    background: color-mix(in srgb, var(--log-error) 8%, transparent);
  }
  .icon {
    display: inline-flex;
    width: 22px;
    height: 22px;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 12px;
  }
  .ok .icon {
    background: color-mix(in srgb, var(--success) 20%, transparent);
    color: var(--success);
  }
  .fail .icon {
    background: color-mix(in srgb, var(--log-error) 20%, transparent);
    color: var(--log-error);
  }
  .body {
    display: flex;
    flex-direction: column;
  }
  .status {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
  }
  .execution-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
  }
  .meta {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && npx vitest run tests/last-execution.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/overview/LastExecution.svelte dashboard/tests/last-execution.test.ts
git commit -m "feat(dashboard): restore boxed Last Execution card with status word and #task_id"
```

---

### Task 14: Dynamic `document.title`

**Files:**
- Create: `dashboard/src/lib/title.ts`
- Test: `dashboard/tests/title.test.ts`
- Modify: `dashboard/src/App.svelte`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/title.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { pageTitle } from '../src/lib/title';

describe('pageTitle', () => {
  it('includes the active project when present', () => {
    expect(pageTitle('serena')).toBe('serena – Serena Dashboard');
  });
  it('falls back to the bare title when there is no project', () => {
    expect(pageTitle(null)).toBe('Serena Dashboard');
    expect(pageTitle(undefined)).toBe('Serena Dashboard');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/title.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement helper**

Create `dashboard/src/lib/title.ts`:

```ts
export function pageTitle(project: string | null | undefined): string {
  return project ? `${project} – Serena Dashboard` : 'Serena Dashboard';
}
```

- [ ] **Step 4: Use it in `App.svelte`**

In `dashboard/src/App.svelte`, add the import after line 14 (`import { modal } ...`):

```svelte
  import { pageTitle } from '$lib/title';
```

Add this effect inside `<script>` just after the `view` state declaration (after line 17):

```svelte
  $effect(() => {
    document.title = pageTitle(config.data?.active_project?.name);
  });
```

- [ ] **Step 5: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/title.test.ts && npm run check`
Expected: PASS; 0 type errors.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/title.ts dashboard/tests/title.test.ts dashboard/src/App.svelte
git commit -m "feat(dashboard): set dynamic document.title from active project"
```

---

### Task 15: News newest-first sort

**Files:**
- Create: `dashboard/src/lib/news.ts`
- Test: `dashboard/tests/news.test.ts`
- Modify: `dashboard/src/components/overview/NewsSection.svelte`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/news.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { sortNewsEntries } from '../src/lib/news';

describe('sortNewsEntries', () => {
  it('orders YYYYMMDD ids newest-first', () => {
    const out = sortNewsEntries({ '20260101': 'a', '20260527': 'b', '20260315': 'c' });
    expect(out.map(([id]) => id)).toEqual(['20260527', '20260315', '20260101']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npx vitest run tests/news.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement helper**

Create `dashboard/src/lib/news.ts`:

```ts
/** Sort news entries by YYYYMMDD id, newest first (matches the legacy dashboard). */
export function sortNewsEntries(news: Record<string, string>): Array<[string, string]> {
  return Object.entries(news).sort((a, b) => b[0].localeCompare(a[0]));
}
```

- [ ] **Step 4: Use it in `NewsSection.svelte`**

In `dashboard/src/components/overview/NewsSection.svelte`, add the import after line 3:

```svelte
  import { sortNewsEntries } from '$lib/news';
```

Change the `load` function body (line 6) from:

```svelte
    items = Object.entries((await fetchUnreadNews()).news);
```

to:

```svelte
    items = sortNewsEntries((await fetchUnreadNews()).news);
```

- [ ] **Step 5: Run test + typecheck**

Run: `cd dashboard && npx vitest run tests/news.test.ts && npm run check`
Expected: PASS; 0 type errors.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/news.ts dashboard/tests/news.test.ts dashboard/src/components/overview/NewsSection.svelte
git commit -m "feat(dashboard): sort What's New entries newest-first"
```

---

### Task 16: Final verification + build the committed bundle

**Files:**
- Modify: `src/serena/resources/dashboard/index.html` + `src/serena/resources/dashboard/assets/*` (regenerated by the build)

- [ ] **Step 1: Format, lint, type-check, full test run**

Run:
```bash
cd dashboard
npm run format
npm run lint
npm run check
npm test
```
Expected: prettier writes/clean, ESLint 0 errors, `svelte-check` 0 errors, all Vitest suites PASS.

- [ ] **Step 2: Build the production bundle into the Python resource dir**

Run:
```bash
cd dashboard && npm run build
```
Expected: Vite writes a fresh hashed `assets/index-*.js` + `assets/index-*.css` and `index.html` into `../src/serena/resources/dashboard/` (the `prebuild` clean removes the old hashed bundle first).

- [ ] **Step 3: Manual smoke (optional but recommended)**

With a Serena MCP server running (dashboard enabled), open `http://127.0.0.1:24282/dashboard/` and verify: config card shows legacy labels/order with no Client; Last Execution is a boxed status card with `#id`; queued executions show a cancel ✕; Advanced Stats shows two readable per-series bar charts with no `removeChild` console errors. (See `dashboard-parity-review/DISCREPANCIES.md` for the before/after reference.)

- [ ] **Step 4: Commit the regenerated bundle**

```bash
git add dashboard/ src/serena/resources/dashboard/
git commit -m "build(dashboard): rebuild committed bundle after parity fixes"
```

Expected: `git status` clean afterward; CI's staleness gate (`git diff --exit-code` over `src/serena/resources/dashboard/`) will pass.

---

## Self-Review

**Spec coverage** (each spec section → task):
- §3.1 `runMutation` → Task 1. §3.2 Modal error prop → Task 3 (+ consumed in 4,5,6,7). §3.3 `confirmDiscard` → Task 2 (+ used in 5,6).
- §4 Stats: two single-series bars → Tasks 8,10; value labels + `removeChild` fix → Task 9; Total Tokens → Task 11.
- §5.1 ConfigCard (labels/order/Client/tooltips/JetBrains) → Task 12. §5.2 LastExecution → Task 13. §5.3 Executions + Cancelled panel → Task 7.
- §6 document.title → Task 14; news sort → Task 15. §2 in-scope rows 1–11 all mapped. Build/commit gate → Task 16.
- Modals needing inline errors (§2 #3): AddLanguage (Task 3), Remove/Delete/Create (Task 4), EditMemory (Task 5), EditSerenaConfig (Task 6), CancelExecution (Task 7). ✓ All covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the assertions. The one conditional note (Combobox selection in Task 3, ambient type in Task 9) gives an explicit fallback action, not a placeholder.

**Type consistency:** `runMutation` returns `{ ok, message?, data? }` and is used consistently (Tasks 3–7). `store.cancel(execution: QueuedExecution)` matches the modal-state `cancelExecution: { execution }`, `ModalHost` `execution={m.execution}`, App handler `(ex) => … executions.cancel(ex)`, and `oncancelexecution: (_ex: QueuedExecution) => void` threaded through OverviewPage → ExecutionsQueue. `toSingleSeriesBar(stats, key, name)` signature matches its StatsPage call sites and the charts test. `pageTitle`/`sortNewsEntries` signatures match their tests and call sites.
</content>
