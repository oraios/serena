<script lang="ts">
  import Icon from '../common/Icon.svelte';
  import { Copy, Check } from '@lucide/svelte';
  let { lines, onclear }: { lines: string[]; onclear: () => void } = $props();
  let copied = $state(false);
  const disabled = $derived(lines.length === 0);

  async function copy() {
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      copied = true;
      setTimeout(() => (copied = false), 1000);
    } catch {
      // clipboard may be unavailable (insecure context / denied permission); fail quietly
    }
  }
  function save() {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'serena-logs.txt';
    a.click();
    // Defer the revoke so the download stream is opened first on slower engines.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
</script>

<div class="log-action-buttons">
  <button class="log-action-btn" {disabled} onclick={copy} title="Copy logs"
    ><Icon icon={copied ? Check : Copy} size={12} /> {copied ? 'copied' : 'copy logs'}</button
  >
  <button class="log-action-btn" {disabled} onclick={save} title="Save logs to file"
    >save logs</button
  >
  <button class="log-action-btn danger" {disabled} onclick={onclear} title="Clear logs"
    >clear logs</button
  >
</div>

<style>
  .log-action-buttons {
    display: flex;
    gap: var(--space-2);
    justify-content: flex-end;
    margin-bottom: var(--space-2);
  }
  .log-action-btn {
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-3);
    cursor: pointer;
    color: var(--text-primary);
  }
  .log-action-btn:disabled {
    color: var(--btn-disabled);
    cursor: not-allowed;
  }
  .danger:not(:disabled) {
    color: var(--log-error);
  }
</style>
