<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { MutationResult } from '$lib/api/mutation';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { createModalAction } from '$lib/modalAction.svelte';
  let {
    title = '',
    confirmLabel = 'OK',
    variant = 'primary',
    onconfirm,
    onclose,
    children,
  }: {
    title?: string;
    confirmLabel?: string;
    variant?: 'primary' | 'danger';
    onconfirm: () => Promise<MutationResult<unknown>>;
    onclose: () => void;
    children: Snippet;
  } = $props();
  const action = createModalAction();
</script>

<Modal open={true} {title} error={action.error} {onclose}>
  <p class="modal-prompt">{@render children()}</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button {variant} disabled={action.busy} onclick={() => action.run(onconfirm, onclose)}>
      {#if action.busy}<Spinner />{:else}{confirmLabel}{/if}
    </Button>
  </div>
</Modal>
