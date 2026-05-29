<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './components/shell/Header.svelte';
  import { theme } from '$lib/stores/theme.svelte';
  import { createPoller } from '$lib/polling';
  import { pollersForView, type View, type PollerName } from '$lib/pollers';
  import type { Poller } from '$lib/polling';
  import { config } from '$lib/stores/config.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import { logs } from '$lib/stores/logs.svelte';
  import { pageTitle } from '$lib/title';
  // View components are added in Phases 3–6; import them as they land.
  import OverviewPage from './components/overview/OverviewPage.svelte';
  import LogsPage from './components/logs/LogsPage.svelte';
  import StatsPage from './components/stats/StatsPage.svelte';
  import ModalHost from './components/modals/ModalHost.svelte';
  import { modal } from '$lib/stores/modal.svelte';

  let view = $state<View>('overview');

  $effect(() => {
    document.title = pageTitle(config.data?.active_project?.name);
  });

  // Swallow + log poll failures so a transient backend error doesn't surface as an
  // unhandled promise rejection. The next tick retries.
  const safe = (p: Promise<void>) => p.catch((e: unknown) => console.debug('poll failed', e));

  const configPoller = createPoller(() => safe(config.poll()), 1000);
  const queuedPoller = createPoller(() => safe(executions.pollQueued()), 1000);
  const lastPoller = createPoller(() => safe(executions.pollLast()), 1000);
  const logsPoller = createPoller(() => safe(logs.poll()), 1000);

  const pollers: Record<PollerName, Poller> = {
    config: configPoller,
    queued: queuedPoller,
    last: lastPoller,
    logs: logsPoller,
  };

  function startPollers(v: View) {
    for (const p of Object.values(pollers)) p.stop();
    for (const name of pollersForView(v)) pollers[name].start();
  }

  function navigate(v: View) {
    view = v;
    startPollers(v);
  }

  onMount(() => {
    theme.init();
    startPollers('overview');
  });
</script>

<div id="frame">
  <Header active={view} onnavigate={navigate} onshutdown={() => modal.open({ kind: 'shutdown' })} />
  <div class="main">
    {#if view === 'overview'}<div class="page-view">
        <OverviewPage
          onaddlanguage={() => modal.open({ kind: 'addLanguage' })}
          onremovelanguage={(language) => modal.open({ kind: 'removeLanguage', language })}
          oneditconfig={() => modal.open({ kind: 'editSerenaConfig' })}
          onopenmemory={(name) => modal.open({ kind: 'editMemory', name })}
          oncreatememory={() => modal.open({ kind: 'createMemory' })}
          ondeletememory={(name) => modal.open({ kind: 'deleteMemory', name })}
          oncancelexecution={(ex) =>
            ex.is_running
              ? modal.open({ kind: 'cancelExecution', execution: ex })
              : void executions.cancel(ex)}
        />
      </div>{/if}
    {#if view === 'logs'}<div class="page-view"><LogsPage /></div>{/if}
    {#if view === 'stats'}<div class="page-view"><StatsPage /></div>{/if}
  </div>
</div>

<ModalHost />

<style>
  .main {
    max-width: var(--max-width);
    margin: 0 auto;
    padding: var(--space-6);
  }
</style>
