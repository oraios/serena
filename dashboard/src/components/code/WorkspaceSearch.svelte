<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '../common/Icon.svelte';
  import { Search } from '@lucide/svelte';

  let value = $state(code.search_query);
  let timer: ReturnType<typeof setTimeout> | null = null;

  function onInput(e: Event) {
    value = (e.target as HTMLInputElement).value;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      void code.search(value);
    }, 250);
  }

  function selectMatch(path: string) {
    code.selectPath(path, { switchMiddleTo: 'symbols' });
  }
</script>

<div class="root">
  <label class="input-wrap">
    <Icon icon={Search} size={14} />
    <input type="search" placeholder="Search workspace symbols…" {value} oninput={onInput} />
  </label>
  {#if code.search_error}
    <div class="error-banner">
      <strong>Search failed.</strong>
      <span class="msg">{code.search_error}</span>
    </div>
  {/if}
  {#if code.search_loading}
    <div class="status">Searching…</div>
  {:else if value.trim().length >= 2 && code.search_results.length === 0 && !code.search_error}
    <div class="status">No matches.</div>
  {/if}
  {#if code.search_results.length > 0}
    <ul class="results">
      {#each code.search_results as m (m.path + ':' + m.name + ':' + m.range.start.line)}
        <li>
          <button type="button" onclick={() => selectMatch(m.path)} class="match">
            <span class="kind">{m.kind}</span>
            <span class="name">{m.name}</span>
            <span class="path">{m.path}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .root {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: var(--space-2);
  }
  .input-wrap {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2);
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-secondary);
  }
  .input-wrap:focus-within {
    border-color: var(--accent);
    color: var(--text-primary);
  }
  .input-wrap input {
    flex: 1;
    background: transparent;
    border: 0;
    outline: none;
    color: var(--text-primary);
    font-family: inherit;
  }
  .status {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
  .error-banner {
    margin-top: var(--space-2);
    background: var(--bg);
    border: 1px solid var(--log-error);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--log-error);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .error-banner .msg {
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .results {
    list-style: none;
    margin: var(--space-2) 0 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
  }
  .match {
    width: 100%;
    text-align: left;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border);
    padding: var(--space-1) var(--space-2);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.85em;
    cursor: pointer;
    display: grid;
    grid-template-columns: 80px 1fr auto;
    gap: var(--space-2);
  }
  .match:hover {
    background: var(--bg);
  }
  .kind {
    color: var(--text-secondary);
  }
  .path {
    color: var(--text-secondary);
  }
</style>
