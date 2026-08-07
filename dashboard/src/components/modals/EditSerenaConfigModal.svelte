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
