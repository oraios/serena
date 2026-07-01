import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Header from '../src/components/shell/Header.svelte';
import { stubFetchJson } from './helpers';

describe('Header', () => {
  it('marks the active view tab with aria-current="page"', () => {
    stubFetchJson({}); // BannerCarousel manifest fetch -> empty, no banners
    render(Header, { props: { active: 'logs', onnavigate: vi.fn(), onshutdown: vi.fn() } });
    expect(screen.getByRole('button', { name: 'Logs' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Overview' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: 'Stats' })).not.toHaveAttribute('aria-current');
  });
});
