<script lang="ts">
  import { onMount } from 'svelte';
  import { logs } from '$lib/stores/logs.svelte';
  import { fetchToolNames } from '$lib/api/endpoints';
  import LogToolbar from './LogToolbar.svelte';
  import LogViewer from './LogViewer.svelte';
  let toolNames = $state<string[]>([]);
  onMount(() => {
    void (async () => {
      toolNames = (await fetchToolNames()).tool_names;
    })();
  });
</script>

<LogToolbar lines={logs.lines} onclear={() => logs.clear()} />
<LogViewer lines={logs.lines} {toolNames} />
