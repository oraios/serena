<script lang="ts">
  import { modal } from '$lib/stores/modal.svelte';
  import { config } from '$lib/stores/config.svelte';
  import ShutdownModal from './ShutdownModal.svelte';
  import CancelExecutionModal from './CancelExecutionModal.svelte';
  import AddLanguageModal from './AddLanguageModal.svelte';
  import RemoveLanguageModal from './RemoveLanguageModal.svelte';
  import EditMemoryModal from './EditMemoryModal.svelte';
  import CreateMemoryModal from './CreateMemoryModal.svelte';
  import DeleteMemoryModal from './DeleteMemoryModal.svelte';
  import EditSerenaConfigModal from './EditSerenaConfigModal.svelte';
  const projectName = $derived(String(config.data?.active_project?.name ?? ''));
  const m = $derived(modal.active);
  const close = () => modal.close();
</script>

{#if m}
  {#if m.kind === 'shutdown'}<ShutdownModal onclose={close} />
  {:else if m.kind === 'cancelExecution'}<CancelExecutionModal
      execution={m.execution}
      onclose={close}
    />
  {:else if m.kind === 'addLanguage'}<AddLanguageModal {projectName} onclose={close} />
  {:else if m.kind === 'removeLanguage'}<RemoveLanguageModal
      language={m.language}
      onclose={close}
    />
  {:else if m.kind === 'editMemory'}{#key m.name}<EditMemoryModal
        name={m.name}
        onclose={close}
      />{/key}
  {:else if m.kind === 'createMemory'}
    <CreateMemoryModal
      {projectName}
      onclose={close}
      oncreated={(name) => modal.open({ kind: 'editMemory', name })}
    />
  {:else if m.kind === 'deleteMemory'}<DeleteMemoryModal name={m.name} onclose={close} />
  {:else if m.kind === 'editSerenaConfig'}<EditSerenaConfigModal onclose={close} />
  {/if}
{/if}
