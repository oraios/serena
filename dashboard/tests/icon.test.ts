import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Icon from '../src/components/common/Icon.svelte';
import { Search } from '@lucide/svelte';

describe('Icon', () => {
  it('renders the given lucide component', () => {
    const { container } = render(Icon, { props: { icon: Search, label: 'Search' } });
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('aria-label')).toBe('Search');
    expect(svg?.getAttribute('role')).toBe('img');
  });

  it('defaults to aria-hidden when no label is given', () => {
    const { container } = render(Icon, { props: { icon: Search } });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    expect(svg?.getAttribute('aria-label')).toBeNull();
  });

  it('passes size and strokeWidth to the lucide component', () => {
    const { container } = render(Icon, {
      props: { icon: Search, size: 24, strokeWidth: 2.25 },
    });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('24');
    expect(svg?.getAttribute('stroke-width')).toBe('2.25');
  });
});
