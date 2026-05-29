<script lang="ts">
  import type { Component } from 'svelte';

  interface Props {
    icon: Component<{
      size?: number | string;
      strokeWidth?: number | string;
      class?: string;
      role?: string;
      'aria-label'?: string;
      'aria-hidden'?: 'true' | 'false' | boolean;
    }>;
    size?: number;
    strokeWidth?: number;
    label?: string;
    class?: string;
  }

  let { icon: IconCmp, size = 16, strokeWidth = 1.75, label, class: cls = '' }: Props = $props();
</script>

{#if label}
  <IconCmp {size} {strokeWidth} class={cls} role="img" aria-label={label} />
{:else}
  <IconCmp {size} {strokeWidth} class={cls} aria-hidden="true" />
{/if}
