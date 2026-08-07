import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import Combobox from '../src/components/common/Combobox.svelte';

describe('Combobox', () => {
  it('filters options by typed text', async () => {
    const { getByRole, queryByText, getByText } = render(Combobox, {
      props: { options: ['python', 'typescript', 'rust'], value: '', onselect: () => {} },
    });
    await fireEvent.input(getByRole('textbox'), { target: { value: 'ty' } });
    expect(getByText('typescript')).toBeInTheDocument();
    expect(queryByText('rust')).toBeNull();
  });
});
