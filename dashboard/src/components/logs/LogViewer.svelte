<script lang="ts">
  import { detectLevel, highlightTools } from '$lib/format';
  let { lines, toolNames }: { lines: string[]; toolNames: string[] } = $props();
  let el = $state<HTMLDivElement | null>(null);

  $effect(() => {
    void lines.length; // re-run when new lines arrive
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom)
      queueMicrotask(() => {
        if (el) el.scrollTop = el.scrollHeight;
      });
  });
</script>

<div bind:this={el} class="log-container">
  {#each lines as line, i (i)}
    <!-- eslint-disable-next-line svelte/no-at-html-tags -- highlightTools escapes all text before injecting spans -->
    <div class="log-line {detectLevel(line)}">{@html highlightTools(line, toolNames)}</div>
  {/each}
</div>

<style>
  .log-container {
    height: calc(100vh - 220px);
    overflow: auto;
    font-family: var(--font-mono);
    font-size: 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
    box-shadow: var(--shadow);
  }
  .log-line {
    white-space: pre-wrap;
  }
  .debug {
    color: var(--log-debug);
  }
  .info {
    color: var(--log-info);
  }
  .warning {
    color: var(--log-warning);
  }
  .error {
    color: var(--log-error);
  }
  :global(.log-line .tool-name) {
    background-color: var(--tool-highlight);
    color: var(--tool-highlight-text);
    font-weight: 700;
  }
</style>
