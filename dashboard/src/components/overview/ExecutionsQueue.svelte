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
          aria-label="Cancel {ex.name}"
          data-testid="cancel-btn"
          onclick={() => oncancelexecution(ex)}>×</button
        >
      </div>
    {/each}
  </div>
{:else}
  <div class="no-stats-message">No queued executions.</div>
{/if}
{#if cancelError}<p class="cancel-error" role="alert">{cancelError}</p>{/if}

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
    color: var(--log-error);
    font-weight: bold;
    line-height: 1;
    padding: 0 2px;
    border-radius: 3px;
  }
  .cancel-btn:hover {
    background: var(--bg-secondary-btn);
  }
  .cancel-error {
    color: var(--log-error);
    margin: var(--space-2) 0 0;
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
