<script lang="ts">
  import type { Snippet } from 'svelte';
  let { title = '', children }: { title?: string; children: Snippet } = $props();
</script>

<section class="card">
  {#if title}<h2 class="card-title">{title}</h2>{/if}
  {@render children()}
</section>

<style>
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    padding: var(--space-6);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    margin-bottom: var(--space-4);
  }
  .card-title {
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-muted);
    margin: 0 0 var(--space-4) 0;
  }
</style>
