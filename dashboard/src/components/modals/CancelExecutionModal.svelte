<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import type { QueuedExecution } from '$lib/api/types';
  let { execution, onclose }: { execution: QueuedExecution; onclose: () => void } = $props();
  // Clear the store-level cancel error on dismiss so a failed cancel here doesn't leave a
  // stale message under the (now uncovered) Executions Queue.
  function handleClose() {
    executions.clearCancelError();
    onclose();
  }
</script>

<ConfirmModal onconfirm={() => executions.cancel(execution)} onclose={handleClose}>
  Are you sure? The execution will continue running until timeout, it will simply no longer be in
  the queue. Abandoning a running execution is only advised as a measure for unblocking Serena.
</ConfirmModal>
