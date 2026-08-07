import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import DeleteMemoryModal from '../src/components/modals/DeleteMemoryModal.svelte';
import { stubFetchJson, errBody } from './helpers';

describe('DeleteMemoryModal error handling', () => {
  it('shows the error and stays open when delete fails', async () => {
    stubFetchJson(errBody('cannot delete'));
    const onclose = vi.fn();
    render(DeleteMemoryModal, { props: { name: 'core', onclose } });
    await fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(await screen.findByText('cannot delete')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
