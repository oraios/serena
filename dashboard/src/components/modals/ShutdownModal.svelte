<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { shutdown } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { onclose }: { onclose: () => void } = $props();
  async function confirm() {
    const res = await runMutation(() => shutdown());
    // Only schedule the tab close if the server actually accepted the shutdown.
    if (res.ok) setTimeout(() => window.close(), 1000);
    return res;
  }
</script>

<ConfirmModal
  title="Shutdown Server"
  confirmLabel="Shutdown"
  variant="danger"
  onconfirm={confirm}
  {onclose}
>
  Shut down the Serena server?
</ConfirmModal>
