<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { saveMemory } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { isValidMemoryName } from '$lib/validation';
  let {
    projectName,
    onclose,
    oncreated,
  }: { projectName: string; onclose: () => void; oncreated: (_name: string) => void } = $props();
  let name = $state('');
  const valid = $derived(isValidMemoryName(name));
  const action = createModalAction();
  function create() {
    if (!valid) return;
    void action.run(
      () => runMutation(() => saveMemory(name, '')),
      () => oncreated(name),
    );
  }
</script>

<Modal open={true} title="Create Memory" error={action.error} {onclose}>
  <p class="modal-info">Create a new memory for project <strong>{projectName}</strong>.</p>
  <p class="modal-hint">
    Use underscores instead of spaces (e.g. "api_architecture"). Use "/" for subdirectories (e.g.
    "architecture/api_design"); use the "global/" prefix for cross-project memories.
  </p>
  <input
    class="modal-input"
    aria-label="Memory name"
    placeholder="e.g., project_overview or topic/memory_name"
    bind:value={name}
  />
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={!valid || action.busy} onclick={create}
      >{#if action.busy}<Spinner />{:else}Create{/if}</Button
    >
  </div>
</Modal>
