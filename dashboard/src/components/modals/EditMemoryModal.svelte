<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getMemory, saveMemory, renameMemory } from '$lib/api/endpoints';
  import { isValidMemoryName } from '$lib/validation';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  // `{#key m.name}` in ModalHost remounts this component per memory, so initializing from
  // the prop here is correct: a different memory mounts a fresh instance.
  // `untrack` reads the prop value without creating a reactive dependency, which avoids the
  // Svelte state_referenced_locally compile warning while preserving the correct semantics.
  let currentName = $state(untrack(() => name));
  let content = $state('');
  let initialContent = $state('');
  let loaded = $state(false);
  let loadError = $state('');
  let renaming = $state(false);
  let renameValue = $state(untrack(() => name));
  const dirty = $derived(content !== initialContent);
  const action = createModalAction();
  const renameAction = createModalAction();
  async function load() {
    const res = await runMutation(() => getMemory(name));
    if (!res.ok) {
      loadError = res.message ?? 'Failed to load memory.';
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
    void action.run(() => runMutation(() => saveMemory(currentName, content)), onclose);
  }
  function applyRename() {
    if (!isValidMemoryName(renameValue) || renameValue === currentName) {
      renaming = false;
      return;
    }
    void renameAction.run(
      () => runMutation(() => renameMemory(currentName, renameValue)),
      () => {
        currentName = renameValue;
        renaming = false;
      },
    );
  }
</script>

<Modal open={true} error={loadError || action.error || renameAction.error} onclose={requestClose}>
  <h3 class="modal-title-with-meta">
    Memory:
    {#if renaming}
      <input
        class="memory-rename-input"
        aria-label="New memory name"
        bind:value={renameValue}
        onkeydown={(e) => e.key === 'Enter' && applyRename()}
      />
      <button
        class="rename-confirm"
        type="button"
        title="Confirm rename"
        aria-label="Confirm rename"
        disabled={renameAction.busy}
        onclick={applyRename}>✓</button
      >
    {:else}
      <span class="memory-name-display">{currentName}</span>
      <button
        class="rename-trigger"
        type="button"
        title="Rename memory"
        aria-label="Rename memory"
        onclick={() => {
          renaming = true;
          renameValue = currentName;
        }}>✎</button
      >
    {/if}
  </h3>
  <textarea
    class="memory-editor modal-textarea"
    aria-label="Memory content"
    rows="20"
    bind:value={content}
  ></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={requestClose}>Cancel</Button>
    <Button disabled={!loaded || action.busy} onclick={save}>Save</Button>
  </div>
</Modal>

<style>
  .memory-rename-input {
    font-family: var(--font-mono);
    font-size: 14px;
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-card);
    color: var(--text-primary);
  }
  .memory-name-display {
    font-family: var(--font-mono);
  }
  .rename-trigger {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
  }
</style>
