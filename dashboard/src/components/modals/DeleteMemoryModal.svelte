<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { deleteMemory } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
</script>

<ConfirmModal variant="danger" onconfirm={() => runMutation(() => deleteMemory(name))} {onclose}>
  Delete memory <strong>{name}</strong>?
</ConfirmModal>
