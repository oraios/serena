import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import FilterDropdown from '../src/components/common/FilterDropdown.svelte';

const opts = [
  { value: 'read_file', label: 'read_file' },
  { value: 'find_symbol', label: 'find_symbol' },
  { value: 'execute_shell_command', label: 'execute_shell_command' },
];

describe('FilterDropdown', () => {
  it('renders placeholder when value is null', () => {
    const { getByRole } = render(FilterDropdown, {
      options: opts,
      value: null,
      placeholder: 'All tools',
    });
    expect(getByRole('button').textContent).toContain('All tools');
  });

  it('opens on click and lists options', async () => {
    const { getByRole, getAllByRole } = render(FilterDropdown, {
      options: opts,
      value: null,
      placeholder: 'All',
    });
    await fireEvent.click(getByRole('button'));
    const items = getAllByRole('option');
    expect(items.length).toBe(3);
  });

  it('typing filters by substring', async () => {
    const { getByRole, getAllByRole, getByPlaceholderText } = render(FilterDropdown, {
      options: opts,
      value: null,
      placeholder: 'All',
    });
    await fireEvent.click(getByRole('button'));
    const input = getByPlaceholderText(/filter/i);
    await fireEvent.input(input, { target: { value: 'sym' } });
    expect(getAllByRole('option').length).toBe(1);
    expect(getAllByRole('option')[0].textContent).toContain('find_symbol');
  });

  it('Enter selects the highlighted option and fires onChange', async () => {
    let chosen: string | null = null;
    const { getByRole, getByPlaceholderText } = render(FilterDropdown, {
      options: opts,
      value: null,
      placeholder: 'All',
      onChange: (v: string | null) => (chosen = v),
    });
    await fireEvent.click(getByRole('button'));
    const input = getByPlaceholderText(/filter/i);
    await fireEvent.keyDown(input, { key: 'ArrowDown' });
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(chosen).toBe('find_symbol');
  });

  it('clear button (×) fires onChange(null) when a value is set', async () => {
    let chosen: string | null = 'read_file';
    const { getByLabelText } = render(FilterDropdown, {
      options: opts,
      value: 'read_file',
      placeholder: 'All',
      onChange: (v: string | null) => (chosen = v),
    });
    await fireEvent.click(getByLabelText(/clear/i));
    expect(chosen).toBeNull();
  });
});
