import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import FileSymbols from '../src/components/code/FileSymbols.svelte';
import { code } from '../src/lib/stores/code.svelte';
import type { FileSymbol } from '../src/lib/api/types';

function sym(name: string, kind: string, line: number, children: FileSymbol[] = []): FileSymbol {
  return {
    name,
    kind,
    range: {
      start: { line, character: 0 },
      end: { line, character: 0 },
    },
    children,
  };
}

beforeEach(() => {
  // Reset the singleton store between tests.
  code.selectPath(null);
  // Wipe any stale per-path state.
  for (const k of Object.keys(code.file_symbols)) delete code.file_symbols[k];
});

describe('FileSymbols', () => {
  it('shows the empty hint when no file is selected', () => {
    const { getByText } = render(FileSymbols);
    expect(getByText(/Select a file/i)).toBeDefined();
  });

  it('renders breadcrumb, counts, and rows with kind icons', () => {
    code.file_symbols['src/foo/bar.py'] = [
      sym('Alpha', 'Class', 5, [sym('foo', 'Method', 10)]),
      sym('fn', 'Function', 20),
    ];
    code.selectPath('src/foo/bar.py');
    code.expandAllSymbols('src/foo/bar.py');
    const { container, getByText, getAllByText } = render(FileSymbols);
    // Breadcrumb shows path parts. 'src' and 'bar.py' are unique.
    expect(getByText('src')).toBeDefined();
    expect(getByText('bar.py')).toBeDefined();
    // 'foo' appears twice (breadcrumb segment + symbol name) — assert at least
    // one occurrence resolves; assert presence in the breadcrumb specifically.
    expect(getAllByText('foo').length).toBeGreaterThanOrEqual(2);
    const nav = container.querySelector('nav[aria-label="File path"]') as HTMLElement;
    expect(nav.textContent).toContain('foo');
    // Counts row mentions kinds in KIND_ORDER
    expect(container.textContent).toMatch(/1 class/);
    expect(container.textContent).toMatch(/1 method/);
    expect(container.textContent).toMatch(/1 function/);
    // Rows include each symbol name (Alpha + fn are unambiguous; foo verified above).
    expect(getByText('Alpha')).toBeDefined();
    expect(getByText('fn')).toBeDefined();
  });

  it('filter input prunes non-matching rows', async () => {
    code.file_symbols['a.py'] = [
      sym('Alpha', 'Class', 0, [sym('foo', 'Method', 1), sym('bar', 'Method', 2)]),
    ];
    code.selectPath('a.py');
    const { getByPlaceholderText, queryByText } = render(FileSymbols);
    const input = getByPlaceholderText(/Filter symbols/i);
    await fireEvent.input(input, { target: { value: 'foo' } });
    // Filtering is debounced (100ms) and force-expands matching branches, so wait
    // for the match to appear — asserting on the positive condition also covers
    // the debounce (waiting only for 'bar' to vanish passes trivially while the
    // parent is collapsed, before the filter has applied).
    await waitFor(() => {
      expect(queryByText('foo')).not.toBeNull();
      expect(queryByText('bar')).toBeNull();
    });
    expect(queryByText('Alpha')).not.toBeNull();
  });

  it('click on line:col copies path:line to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    code.file_symbols['x.py'] = [sym('foo', 'Function', 27)];
    code.selectPath('x.py');
    const { getByText } = render(FileSymbols);
    const loc = getByText('28:1'); // backend lines are 0-based, UI shows +1
    await fireEvent.click(loc);
    expect(writeText).toHaveBeenCalledWith('x.py:28');
  });

  it('expand-all and collapse-all buttons toggle the parent state', async () => {
    code.file_symbols['x.py'] = [sym('Alpha', 'Class', 0, [sym('foo', 'Method', 1)])];
    code.selectPath('x.py');
    const { getByLabelText, queryByText } = render(FileSymbols);
    expect(queryByText('foo')).toBeNull();
    await fireEvent.click(getByLabelText(/Expand all/i));
    await waitFor(() => expect(queryByText('foo')).not.toBeNull());
    await fireEvent.click(getByLabelText(/Collapse all/i));
    await waitFor(() => expect(queryByText('foo')).toBeNull());
  });

  it('sticky parent contract: depth-0 parents are marked and the bar offset is exposed', async () => {
    // Guards the sticky-header fix: parent rows must carry `has-children depth-0`
    // (the sticky CSS target) and the root must expose `--bar-h` so the pinned row
    // offsets BELOW the header bar instead of hiding behind it.
    code.file_symbols['s.py'] = [sym('Alpha', 'Class', 0, [sym('foo', 'Method', 1)])];
    code.selectPath('s.py');
    const { container, getByLabelText } = render(FileSymbols);
    await fireEvent.click(getByLabelText(/Expand all/i));
    const parent = [...container.querySelectorAll('.row.has-children')].find((r) =>
      r.textContent?.includes('Alpha'),
    );
    expect(parent).toBeDefined();
    expect(parent?.classList.contains('depth-0')).toBe(true);
    expect(container.querySelector('.root')?.getAttribute('style') ?? '').toMatch(/--bar-h/);
  });
});
