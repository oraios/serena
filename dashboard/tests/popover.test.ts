import { describe, it, expect } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { CircleHelp } from '@lucide/svelte';
import Popover from '../src/components/common/Popover.svelte';

const content = createRawSnippet(() => ({ render: () => `<p>Help body</p>` }));

function renderPopover() {
  return render(Popover, {
    label: 'How it works',
    icon: CircleHelp,
    title: 'How it works',
    children: content,
  });
}

describe('Popover', () => {
  it('is closed initially and opens on trigger click', async () => {
    const { getByLabelText, queryByRole, findByRole } = renderPopover();
    expect(queryByRole('dialog')).toBeNull();
    await fireEvent.click(getByLabelText('How it works'));
    expect(await findByRole('dialog')).toBeTruthy();
  });

  it('closes on Escape', async () => {
    const { getByLabelText, findByRole, queryByRole } = renderPopover();
    await fireEvent.click(getByLabelText('How it works'));
    await findByRole('dialog');
    await fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(queryByRole('dialog')).toBeNull());
  });

  it('closes on outside click', async () => {
    const { getByLabelText, findByRole, queryByRole } = renderPopover();
    await fireEvent.click(getByLabelText('How it works'));
    await findByRole('dialog');
    await fireEvent.click(document.body);
    await waitFor(() => expect(queryByRole('dialog')).toBeNull());
  });
});
