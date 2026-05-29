import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import AddLanguageModal from '../src/components/modals/AddLanguageModal.svelte';
import { stubFetchRoutes, errBody } from './helpers';

describe('AddLanguageModal error handling', () => {
  it('shows the error inline and stays open when add fails', async () => {
    stubFetchRoutes(
      { '/get_available_languages': { languages: ['go'] } },
      errBody('unknown language'),
    );
    const onclose = vi.fn();
    render(AddLanguageModal, { props: { projectName: 'serena', onclose } });
    const input = screen.getByRole('textbox');
    await fireEvent.focus(input);
    await fireEvent.click(await screen.findByText('go'));
    await fireEvent.click(screen.getByRole('button', { name: 'Add Language' }));
    expect(await screen.findByText('unknown language')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
