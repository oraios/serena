import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import CodePage from '../src/components/code/CodePage.svelte';
import { code } from '../src/lib/stores/code.svelte';
import { stubFetchRoutes } from './helpers';

beforeEach(() => {
  stubFetchRoutes({
    '/code/list_dir': { entries: [] },
  });
  code.setMiddlePane('symbols');
  code._setDiagFilesForTest([]);
});

describe('CodePage', () => {
  it('renders three tabs and switches the middle pane on click', async () => {
    const { getByRole, container } = render(CodePage);
    const tabSymbols = getByRole('button', { name: /Symbols/i });
    const tabSearch = getByRole('button', { name: /Search/i });
    const tabDiag = getByRole('button', { name: /Diagnostics/i });
    expect(tabSymbols).toBeDefined();
    expect(tabSearch).toBeDefined();
    expect(tabDiag).toBeDefined();

    await fireEvent.click(tabDiag);
    expect(code.middle_pane).toBe('diagnostics');
    expect(container.textContent).toMatch(/Computing diagnostics is slow/i);
  });

  it('does not render a right-edge diagnostics column', () => {
    const { container } = render(CodePage);
    expect(container.querySelector('.diagnostics')).toBeNull();
  });

  it('diagnostics tab badge shows the file count, not the raw diagnostic count', () => {
    code._setDiagFilesForTest([
      {
        path: 'a.py',
        diagnostics: [
          { severity: 'error', message: 'x', line: 0, column: 0 },
          { severity: 'warning', message: 'y', line: 1, column: 0 },
          { severity: 'info', message: 'z', line: 2, column: 0 },
        ],
      },
      { path: 'b.py', diagnostics: [{ severity: 'error', message: 'q', line: 0, column: 0 }] },
    ]);
    const { getByRole } = render(CodePage);
    const tabDiag = getByRole('button', { name: /Diagnostics/i });
    // 2 files, 4 diagnostics → badge must read "· 2" (files), never "· 4".
    expect(tabDiag.textContent).toMatch(/·\s*2\b/);
    expect(tabDiag.textContent).not.toMatch(/·\s*4\b/);
  });
});

describe('CodePage — explainer popover', () => {
  it('opens the help popover and shows the LSP explainer text', async () => {
    const { getByLabelText, findByRole } = render(CodePage);
    await fireEvent.click(getByLabelText(/How the Code explorer works/i));
    const dialog = await findByRole('dialog');
    expect(dialog.textContent).toMatch(/documentSymbol/);
    expect(dialog.textContent).toMatch(/workspace\/symbol/);
    expect(dialog.textContent).toMatch(/textDocument\/diagnostic/);
  });
});
