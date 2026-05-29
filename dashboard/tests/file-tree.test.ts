import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import { stubFetchRoutes } from './helpers';
import FileTree from '../src/components/code/FileTree.svelte';
import { code } from '../src/lib/stores/code.svelte';

beforeEach(() => {
  // Reset the singleton store between tests.
  code.selectPath(null);
  code.setDiagScope({ kind: 'project', path: null });
  code.setMiddlePane('symbols');
  // Wipe any stale per-path dir state so the tree actually re-loads.
  for (const k of Object.keys(code.dir_children)) delete code.dir_children[k];
});

describe('FileTree — run diagnostics action', () => {
  it('runs file-scoped diagnostics from a file row without selecting it', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({ entries: [{ name: 'a.py', kind: 'file' }] }),
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    const btn = await findByLabelText(/Run diagnostics on a\.py/i);
    await fireEvent.click(btn);
    await waitFor(() => expect(code.diag_scope).toEqual({ kind: 'file', path: 'a.py' }));
    expect(code.middle_pane).toBe('diagnostics');
    // Clicking the action must NOT select the file row.
    expect(code.selected_path).toBeNull();
  });

  it('runs directory-scoped diagnostics from a dir row', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({ entries: [{ name: 'src', kind: 'dir' }] }),
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    const btn = await findByLabelText(/Run diagnostics on src/i);
    await fireEvent.click(btn);
    await waitFor(() => expect(code.diag_scope).toEqual({ kind: 'directory', path: 'src' }));
  });
});

describe('FileTree — icons & loading', () => {
  it('renders a type icon for files and a folder icon for directories', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({
        entries: [
          { name: 'main.ts', kind: 'file' },
          { name: 'src', kind: 'dir' },
        ],
      }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    // 'main.ts' -> Code icon (label 'Code'); 'src' -> closed folder (label 'Folder').
    expect(await findByLabelText('Code')).toBeTruthy();
    expect(await findByLabelText('Folder')).toBeTruthy();
  });

  it('shows a spinner while a directory is still loading', async () => {
    stubFetchRoutes({
      // Never resolves -> dir_children stays undefined -> loading row stays.
      '/code/list_dir': () => new Promise<never>(() => {}),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    // Spinner renders aria-label="Loading".
    expect(await findByLabelText('Loading')).toBeTruthy();
  });
});
