<script lang="ts">
  import type { ResponseConfigOverview } from '$lib/api/types';
  import Collapsible from '../common/Collapsible.svelte';
  import Button from '../common/Button.svelte';
  let {
    data,
    onaddlanguage,
    onremovelanguage,
    oneditconfig,
    onopenmemory,
    oncreatememory,
    ondeletememory,
  }: {
    data: ResponseConfigOverview;
    onaddlanguage: () => void;
    onremovelanguage: (_lang: string) => void;
    oneditconfig: () => void;
    onopenmemory: (_name: string) => void;
    oncreatememory: () => void;
    ondeletememory: (_name: string) => void;
  } = $props();
</script>

<div class="config-display">
  <div class="config-grid">
    <span class="config-label">Version</span>
    <span class="config-value">{data.serena_version}</span>

    <span class="config-label">Active Project</span>
    <span class="config-value">
      {#if data.active_project?.name && data.active_project?.path}
        <span title="Project configuration in {data.active_project.path}/.serena/project.yml"
          >{data.active_project.name}</span
        >
      {:else}
        {data.active_project?.name ?? 'None'}
      {/if}
    </span>

    <span class="config-label">Languages</span>
    <span class="config-value">
      {#if data.jetbrains_mode}
        Using JetBrains backend
      {:else}
        <span class="languages-cell">
          {#each data.languages as lang (lang)}
            <span class="lang-badge"
              >{lang}
              {#if data.languages.length > 1}
                <button
                  class="lang-remove"
                  aria-label="Remove {lang}"
                  onclick={() => onremovelanguage(lang)}>×</button
                >
              {/if}
            </span>
          {/each}
          {#if data.active_project?.name}
            <Button variant="secondary" onclick={onaddlanguage}>Add Language</Button>
          {/if}
        </span>
      {/if}
    </span>

    <span class="config-label">Context</span>
    <span class="config-value"><span title={data.context.path}>{data.context.name}</span></span>

    <span class="config-label">Active Modes</span>
    <span class="config-value">
      {#if data.modes.length}
        {#each data.modes as m, i (m.name)}<span title={m.path}>{m.name}</span
          >{#if i < data.modes.length - 1},
          {/if}{/each}
      {:else}
        None
      {/if}
    </span>

    <span class="config-label">File Encoding</span>
    <span class="config-value">{data.encoding ?? 'N/A'}</span>
  </div>

  <Collapsible title="Active Tools ({data.active_tools.length})">
    <div class="tools-grid">
      {#each data.active_tools as t (t)}<span class="tool-chip">{t}</span>{/each}
    </div>
  </Collapsible>

  {#if data.available_memories}
    <Collapsible title="Memories ({data.available_memories.length})">
      <div class="memories-container">
        {#each data.available_memories as m (m)}
          <div class="memory-item">
            <button class="memory-name" onclick={() => onopenmemory(m)}>{m}</button>
            <button
              class="memory-remove"
              aria-label="Delete memory {m}"
              title="Delete memory"
              onclick={() => ondeletememory(m)}>×</button
            >
          </div>
        {/each}
        <button class="memory-add-btn" onclick={oncreatememory}>+ Add Memory</button>
      </div>
    </Collapsible>
  {/if}

  <div class="config-footer">
    <a
      class="config-guide-link"
      href="https://oraios.github.io/serena/02-usage/050_configuration.html"
      target="_blank"
      rel="noopener noreferrer">📖 View Configuration Guide</a
    >
    <Button variant="secondary" onclick={oneditconfig}>Edit Global Serena Config</Button>
  </div>
</div>

<style>
  .config-grid {
    display: grid;
    grid-template-columns: 160px 1fr;
    gap: var(--space-2) var(--space-3);
    align-items: baseline;
    margin-bottom: var(--space-4);
  }
  .config-label {
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-muted);
  }
  .config-value {
    color: var(--text-primary);
  }
  /* Breathing room above the Active Tools / Memories collapsibles (scoped to this card). */
  .config-display :global(.collapsible) {
    margin-top: var(--space-4);
  }
  .languages-cell {
    display: inline-flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .lang-badge {
    background: var(--bg-secondary-btn);
    border-radius: var(--radius-sm);
    padding: 2px var(--space-2);
    font-family: var(--font-mono);
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .lang-remove {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--log-error);
    font-weight: bold;
    line-height: 1;
    padding: 0 2px;
    border-radius: 3px;
  }
  .lang-remove:hover {
    background: var(--bg-secondary-btn);
  }
  .tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-2);
  }
  .tool-chip {
    background: var(--bg);
    padding: 6px 10px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .memories-container {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .memory-item {
    position: relative;
    display: inline-flex;
    align-items: center;
    padding: 8px 30px 8px 12px;
    border-radius: 4px;
    background: var(--bg);
    border: 1px solid var(--border);
  }
  .memory-name {
    background: none;
    border: none;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
    padding: 0;
  }
  .memory-remove {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    border-radius: 3px;
    cursor: pointer;
    color: var(--log-error);
    font-size: 14px;
    font-weight: bold;
    line-height: 1;
  }
  .memory-remove:hover {
    background: var(--bg-secondary-btn);
  }
  .memory-add-btn {
    display: inline-flex;
    align-items: center;
    padding: 8px 12px;
    border-radius: 4px;
    border: 1px dashed var(--border-strong);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    font-family: var(--font-sans);
    font-size: 13px;
  }
  .memory-add-btn:hover {
    border-color: var(--accent);
  }
  .config-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-3);
    margin-top: var(--space-4);
    flex-wrap: wrap;
  }
  .config-guide-link {
    color: var(--accent);
    font-weight: 500;
    text-decoration: none;
  }
  .config-guide-link:hover {
    text-decoration: underline;
  }
</style>
