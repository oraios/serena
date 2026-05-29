<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  let { execution }: { execution: QueuedExecution | null } = $props();
  const statusWord = $derived(
    !execution
      ? ''
      : execution.is_running
        ? 'Running'
        : execution.finished_successfully
          ? 'Succeeded'
          : 'Failed',
  );
  const icon = $derived(
    !execution ? '' : execution.is_running ? '…' : execution.finished_successfully ? '✓' : '✗',
  );
</script>

{#if execution}
  <div
    class="last-exec"
    class:ok={execution.finished_successfully && !execution.is_running}
    class:fail={!execution.finished_successfully && !execution.is_running}
    class:running={execution.is_running}
  >
    <span class="icon" aria-hidden="true">{icon}</span>
    <div class="body">
      <span class="status">{statusWord}</span>
      <span class="execution-name">{execution.name}</span>
    </div>
    <span class="meta">#{execution.task_id}</span>
  </div>
{:else}
  <div class="no-stats-message">None yet.</div>
{/if}

<style>
  .last-exec {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .last-exec.ok {
    border-color: var(--success);
    background: color-mix(in srgb, var(--success) 8%, transparent);
  }
  .last-exec.fail {
    border-color: var(--log-error);
    background: color-mix(in srgb, var(--log-error) 8%, transparent);
  }
  .icon {
    display: inline-flex;
    width: 22px;
    height: 22px;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 12px;
  }
  .ok .icon {
    background: color-mix(in srgb, var(--success) 20%, transparent);
    color: var(--success);
  }
  .fail .icon {
    background: color-mix(in srgb, var(--log-error) 20%, transparent);
    color: var(--log-error);
  }
  .body {
    display: flex;
    flex-direction: column;
  }
  .status {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
  }
  .execution-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
  }
  .meta {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
