import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/svelte';
import EditSerenaConfigModal from '../src/components/modals/EditSerenaConfigModal.svelte';
import { stubFetchJson, errBody } from './helpers';

describe('EditSerenaConfigModal', () => {
  it('prompts before discarding unsaved edits and aborts close when declined', async () => {
    stubFetchJson({ content: 'yaml: 1' });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onclose = vi.fn();
    render(EditSerenaConfigModal, { props: { onclose } });
    const textarea = await screen.findByRole('textbox');
    // Wait for the async onMount fetch to complete so the textarea has the loaded
    // content ('yaml: 1') before we simulate editing.
    await waitFor(() => {
      if ((textarea as HTMLTextAreaElement).value !== 'yaml: 1') throw new Error('not loaded yet');
    });
    await fireEvent.input(textarea, { target: { value: 'yaml: 2' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onclose).not.toHaveBeenCalled();
  });

  it('shows an error and disables Save when the config fails to load', async () => {
    stubFetchJson(errBody('Serena config file not found'));
    render(EditSerenaConfigModal, { props: { onclose: vi.fn() } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Serena config file not found');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('populates the textarea and enables Save when the config loads', async () => {
    stubFetchJson({ content: 'yaml: 1' });
    render(EditSerenaConfigModal, { props: { onclose: vi.fn() } });
    const textarea = await screen.findByRole('textbox');
    await waitFor(() => {
      if ((textarea as HTMLTextAreaElement).value !== 'yaml: 1') throw new Error('not loaded yet');
    });
    expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled();
  });
});
