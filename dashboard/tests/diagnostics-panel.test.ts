import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import DiagnosticsPanel from '../src/components/code/DiagnosticsPanel.svelte';
import { code } from '../src/lib/stores/code.svelte';
import { stubFetchRoutes } from './helpers';

beforeEach(() => {
  code._setDiagFilesForTest([]);
  // Reset severity filter
  for (const s of ['error', 'warning', 'info', 'hint'] as const) {
    if (code.diag_severity_filter.has(s)) code.toggleDiagSeverity(s);
  }
});

describe('DiagnosticsPanel', () => {
  it('shows persistent slow-warning even when not loading and no data', () => {
    const { getByText } = render(DiagnosticsPanel);
    expect(getByText(/Computing diagnostics is slow/i)).toBeDefined();
  });

  it('renders severity chips with counts and lets the user filter', async () => {
    code._setDiagFilesForTest([
      {
        path: 'a.py',
        diagnostics: [
          { severity: 'error', message: 'boom', line: 0, column: 0 },
          { severity: 'warning', message: 'meh', line: 1, column: 0 },
        ],
      },
    ]);
    const { getByText, queryByText } = render(DiagnosticsPanel);
    // Counts visible
    expect(getByText(/Errors\s*\(1\)/)).toBeDefined();
    expect(getByText(/Warnings\s*\(1\)/)).toBeDefined();
    // Both messages visible initially (filter empty = show all)
    expect(queryByText('boom')).not.toBeNull();
    expect(queryByText('meh')).not.toBeNull();
    // Toggle to only-errors
    await fireEvent.click(getByText(/Errors\s*\(1\)/));
    expect(queryByText('boom')).not.toBeNull();
    expect(queryByText('meh')).toBeNull();
  });

  it('notes when files were skipped because no language server handles their type', async () => {
    stubFetchRoutes({
      '/code/diagnostics_summary': () => ({ files: [], truncated: false, skipped_unsupported: 3 }),
    });
    code.setDiagScope({ kind: 'project', path: null });
    await code.refreshDiagnostics(1000);
    const { getByText } = render(DiagnosticsPanel);
    expect(getByText(/3 files were not analyzed/i)).toBeDefined();
  });

  it('shows no skip note when every file was analyzed', async () => {
    stubFetchRoutes({
      '/code/diagnostics_summary': () => ({ files: [], truncated: false, skipped_unsupported: 0 }),
    });
    code.setDiagScope({ kind: 'project', path: null });
    await code.refreshDiagnostics(1000);
    const { queryByText } = render(DiagnosticsPanel);
    expect(queryByText(/not analyzed/i)).toBeNull();
  });
});

describe('DiagnosticsPanel — scope selector', () => {
  beforeEach(() => {
    code.setDiagScope({ kind: 'project', path: null });
    code.selectPath(null);
  });

  it('disables File/Directory scope when nothing is selected', () => {
    const { getByRole } = render(DiagnosticsPanel);
    expect((getByRole('button', { name: /^File$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((getByRole('button', { name: /^Directory$/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((getByRole('button', { name: /^Project$/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('enables File/Directory once a file is selected and sets scope on click', async () => {
    code.file_symbols['src/a.py'] = [] as never; // avoid a symbols fetch on selectPath
    code.selectPath('src/a.py');
    const { getByRole } = render(DiagnosticsPanel);
    const fileBtn = getByRole('button', { name: /^File$/i }) as HTMLButtonElement;
    expect(fileBtn.disabled).toBe(false);
    await fireEvent.click(fileBtn);
    expect(code.diag_scope).toEqual({ kind: 'file', path: 'src/a.py' });
  });

  it('does not let selection-sync clobber a scope set by runDiagnosticsForPath', async () => {
    // A different file is "selected" in the tree...
    code.file_symbols['other.py'] = [] as never; // avoid a symbols fetch on selectPath
    code.selectPath('other.py');
    // ...stub the diagnostics fetch so runDiagnosticsForPath resolves.
    stubFetchRoutes({
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    render(DiagnosticsPanel);
    // Explicit per-row action targets a DIFFERENT file.
    await code.runDiagnosticsForPath('target.py', 'file');
    await waitFor(() => {
      // The panel effect must NOT have snapped scope back to the selection.
      expect(code.diag_scope).toEqual({ kind: 'file', path: 'target.py' });
    });
  });

  it('disables Directory scope for a top-level file (parent is project root)', () => {
    code.file_symbols['top.py'] = [] as never; // avoid a symbols fetch on selectPath
    code.selectPath('top.py');
    const { getByRole } = render(DiagnosticsPanel);
    expect((getByRole('button', { name: /^File$/i }) as HTMLButtonElement).disabled).toBe(false);
    // parentDir('top.py') === '.', which would be a whole-project scan — disabled.
    expect((getByRole('button', { name: /^Directory$/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it('renders an active tree-set scope as active-and-enabled, never disabled', async () => {
    code.selectPath(null); // nothing selected in the tree
    stubFetchRoutes({
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    const { getByRole } = render(DiagnosticsPanel);
    // Scope set from a file-tree action, without selecting the row.
    await code.runDiagnosticsForPath('lonely.py', 'file');
    await waitFor(() => {
      const fileBtn = getByRole('button', { name: /^File$/i }) as HTMLButtonElement;
      expect(fileBtn.classList.contains('active')).toBe(true);
      expect(fileBtn.disabled).toBe(false); // not the contradictory active+disabled state
    });
  });

  it('flags stale results when the target scope differs from the last refreshed scope', async () => {
    code.file_symbols['a.py'] = [] as never;
    stubFetchRoutes({
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    // Refresh under project scope...
    code.setDiagScope({ kind: 'project', path: null });
    await code.refreshDiagnostics(1000);
    const { queryByText } = render(DiagnosticsPanel);
    // ...then re-target a file without refreshing — results now belong to a
    // different scope than the header advertises.
    code.selectPath('a.py');
    code.setDiagScope({ kind: 'file', path: 'a.py' });
    await waitFor(() => expect(queryByText(/Showing results for the project/i)).not.toBeNull());
  });
});
