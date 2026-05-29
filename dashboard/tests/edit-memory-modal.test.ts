import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/svelte';
import EditMemoryModal from '../src/components/modals/EditMemoryModal.svelte';
import { stubFetchJson } from './helpers';

describe('EditMemoryModal', () => {
  it('prompts before discarding unsaved edits and aborts close when declined', async () => {
    stubFetchJson({ content: 'orig', memory_name: 'core' });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onclose = vi.fn();
    render(EditMemoryModal, { props: { name: 'core', onclose } });
    // Wait for the async onMount fetch to complete so the textarea has the loaded
    // content ('orig') before we simulate editing. findByRole returns as soon as
    // the element exists, but the value is only set after the fetch resolves.
    const textarea = await screen.findByRole('textbox');
    await waitFor(() => {
      if ((textarea as HTMLTextAreaElement).value !== 'orig') throw new Error('not loaded yet');
    });
    await fireEvent.input(textarea, { target: { value: 'changed' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
  });
});
