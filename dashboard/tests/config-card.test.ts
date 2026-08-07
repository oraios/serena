import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ConfigCard from '../src/components/overview/ConfigCard.svelte';
import type { ResponseConfigOverview } from '../src/lib/api/types';

function makeConfig(over: Partial<ResponseConfigOverview> = {}): ResponseConfigOverview {
  return {
    active_project: { name: 'serena', language: 'Python', path: '/x' },
    context: { name: 'claude-code', description: '', path: '/ctx' },
    modes: [{ name: 'editing', path: '/m1' }],
    active_tools: ['find_symbol'],
    tool_stats_summary: {},
    registered_projects: [],
    available_tools: [],
    available_modes: [],
    available_contexts: [],
    available_memories: [],
    jetbrains_mode: false,
    languages: ['python'],
    encoding: 'utf-8',
    current_client: 'claude',
    serena_version: '1.5.4',
    newer_serena_version: null,
    ...over,
  };
}

const cbs = {
  onaddlanguage: vi.fn(),
  onremovelanguage: vi.fn(),
  oneditconfig: vi.fn(),
  onopenmemory: vi.fn(),
  oncreatememory: vi.fn(),
  ondeletememory: vi.fn(),
};

describe('ConfigCard', () => {
  it('does not render a Client field', () => {
    render(ConfigCard, { props: { data: makeConfig(), ...cbs } });
    expect(screen.queryByText('Client')).toBeNull();
  });

  it('shows the JetBrains backend notice and hides Add Language in jetbrains mode', () => {
    render(ConfigCard, { props: { data: makeConfig({ jetbrains_mode: true }), ...cbs } });
    expect(screen.getByText('Using JetBrains backend')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Language' })).toBeNull();
  });

  it('shows Add Language when not in jetbrains mode', () => {
    render(ConfigCard, { props: { data: makeConfig(), ...cbs } });
    expect(screen.getByRole('button', { name: 'Add Language' })).toBeInTheDocument();
  });

  it('hides the newer-version badge when the backend reports none', () => {
    render(ConfigCard, { props: { data: makeConfig(), ...cbs } });
    expect(screen.queryByText(/newer version available/)).toBeNull();
  });

  it('links to the releases page when a newer version is available', () => {
    render(ConfigCard, { props: { data: makeConfig({ newer_serena_version: '1.6.2' }), ...cbs } });
    const link = screen.getByRole('link', { name: /newer version available: 1\.6\.2/ });
    expect(link).toHaveAttribute('href', 'https://github.com/oraios/serena/releases');
  });
});
