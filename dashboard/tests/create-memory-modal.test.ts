import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import CreateMemoryModal from '../src/components/modals/CreateMemoryModal.svelte';
import { stubFetchJson, errBody } from './helpers';

describe('CreateMemoryModal', () => {
  it('disables Create until the name is valid', async () => {
    stubFetchJson(errBody('nope'));
    render(CreateMemoryModal, {
      props: { projectName: 'serena', onclose: vi.fn(), oncreated: vi.fn() },
    });
    const create = screen.getByRole('button', { name: 'Create' });
    expect(create).toBeDisabled();
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'valid_name' } });
    expect(create).not.toBeDisabled();
  });

  it('shows the error inline and does not signal creation when save fails', async () => {
    stubFetchJson(errBody('already exists'));
    const oncreated = vi.fn();
    render(CreateMemoryModal, { props: { projectName: 'serena', onclose: vi.fn(), oncreated } });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'dup' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('already exists')).toBeInTheDocument();
    expect(oncreated).not.toHaveBeenCalled();
  });

  it('renders a "Create Memory" title heading', () => {
    stubFetchJson(errBody('nope'));
    render(CreateMemoryModal, {
      props: { projectName: 'serena', onclose: vi.fn(), oncreated: vi.fn() },
    });
    expect(screen.getByRole('heading', { name: 'Create Memory' })).toBeInTheDocument();
  });
});
