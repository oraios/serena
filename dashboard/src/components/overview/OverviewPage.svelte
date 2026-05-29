<script lang="ts">
  import { config } from '$lib/stores/config.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import ConfigCard from './ConfigCard.svelte';
  import ToolUsageBars from './ToolUsageBars.svelte';
  import ListPanel from './ListPanel.svelte';
  import ProjectsPanel from './ProjectsPanel.svelte';
  import Spinner from '../common/Spinner.svelte';
  import ExecutionsQueue from './ExecutionsQueue.svelte';
  import LastExecution from './LastExecution.svelte';
  import CancelledExecutions from './CancelledExecutions.svelte';
  import NewsSection from './NewsSection.svelte';
  import SummaryCards from './SummaryCards.svelte';
  import Timeline from './Timeline.svelte';
  import type { QueuedExecution } from '$lib/api/types';
  import Card from '../common/Card.svelte';
  import BannerCarousel from '../banners/BannerCarousel.svelte';
  let {
    onaddlanguage,
    onremovelanguage,
    oneditconfig,
    onopenmemory,
    oncreatememory,
    ondeletememory,
    oncancelexecution,
  }: {
    onaddlanguage: () => void;
    onremovelanguage: (_l: string) => void;
    oneditconfig: () => void;
    onopenmemory: (_n: string) => void;
    oncreatememory: () => void;
    ondeletememory: (_n: string) => void;
    oncancelexecution: (_ex: QueuedExecution) => void;
  } = $props();
  const d = $derived(config.data);
  // Tool names for the Timeline FilterDropdown: union of the keys of the live
  // tool_stats_summary (config poller, 1s) and any tool names already seen in
  // the timeline ring buffer (catches tools that fired before stats summary updated).
  const toolNames = $derived.by(() => {
    const fromSummary = Object.keys(d?.tool_stats_summary ?? {});
    const fromTimeline = new Set(timeline.records.map((r) => r.tool));
    for (const n of fromSummary) fromTimeline.add(n);
    return [...fromTimeline].sort();
  });
</script>

{#if !d}
  <Spinner />
{:else}
  <SummaryCards totals={d.tool_stats_totals} />
  <Timeline store={timeline} {toolNames} />
  <div class="overview-container">
    <div class="overview-left">
      <NewsSection />
      <Card title="Current Configuration">
        <ConfigCard
          data={d}
          {onaddlanguage}
          {onremovelanguage}
          {oneditconfig}
          {onopenmemory}
          {oncreatememory}
          {ondeletememory}
        />
      </Card>
      <Card title="Tool Usage">
        <ToolUsageBars stats={d.tool_stats_summary} />
      </Card>
      <Card title="Executions Queue">
        <ExecutionsQueue
          items={executions.queued}
          cancelError={executions.cancelError}
          {oncancelexecution}
        />
      </Card>
      {#if executions.cancelled.length}
        <Card title="Cancelled Executions">
          <CancelledExecutions items={executions.cancelled} />
        </Card>
      {/if}
      <Card title="Last Execution">
        <LastExecution execution={executions.last} />
      </Card>
    </div>
    <div class="overview-right">
      <ProjectsPanel projects={d.registered_projects} />
      <ListPanel
        title="Available Tools (Disabled)"
        items={d.available_tools.filter((t) => !t.is_active).map((t) => ({ name: t.name }))}
      />
      <ListPanel
        title="Available Modes"
        items={d.available_modes.map((m) => ({ name: m.name, active: m.is_active }))}
      />
      <ListPanel
        title="Available Contexts"
        items={d.available_contexts.map((c) => ({ name: c.name, active: c.is_active }))}
      />
      <Card>
        <BannerCarousel target="gold" />
      </Card>
    </div>
  </div>
{/if}

<style>
  .overview-container {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 400px;
    gap: var(--space-6);
  }
  @media (max-width: 1000px) {
    .overview-container {
      grid-template-columns: 1fr;
    }
  }
</style>
