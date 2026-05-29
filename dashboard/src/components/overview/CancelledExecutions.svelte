<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  let { items }: { items: QueuedExecution[] } = $props();
</script>

<div class="cancelled-list">
  {#each items as ex (ex.task_id)}
    <div class="cancelled-item" class:abandoned={ex.is_running}>
      <span class="icon" aria-hidden="true">{ex.is_running ? '!' : '✕'}</span>
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
