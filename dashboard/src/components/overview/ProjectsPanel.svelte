<script lang="ts">
  import type { ProjectInfo } from '$lib/api/types';
  import Card from '../common/Card.svelte';
  import Collapsible from '../common/Collapsible.svelte';
  let { projects }: { projects: ProjectInfo[] } = $props();
</script>

<Card>
  <Collapsible title="Registered Projects ({projects.length})" open={false}>
    {#if projects.length}
      <ul class="projects">
        {#each projects as p (p.path)}
          <li class="project" class:active={p.is_active}>
            <div class="project-name">{p.name}</div>
            <div class="project-path">{p.path}</div>
          </li>
        {/each}
      </ul>
    {:else}
      <div class="no-stats-message">None.</div>
    {/if}
  </Collapsible>
</Card>

<style>
  .projects {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .project {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background: var(--bg);
    border: 1px solid var(--border);
  }
  .project.active {
    background: var(--accent);
    color: var(--text-on-accent);
    border-color: var(--accent);
  }
  .project-name {
    font-weight: 700;
    font-size: 13px;
    margin-bottom: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .project-path {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .project.active .project-path {
    color: var(--text-on-accent);
    opacity: 0.85;
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
