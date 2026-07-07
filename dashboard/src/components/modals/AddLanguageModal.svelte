<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Combobox from '../common/Combobox.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { fetchAvailableLanguages, addLanguage } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  let { projectName, onclose }: { projectName: string; onclose: () => void } = $props();
  let options = $state<string[]>([]);
  let selected = $state('');
  const action = createModalAction();
  onMount(() => {
    void (async () => {
      options = (await fetchAvailableLanguages()).languages;
    })();
  });
  function add() {
    if (!selected) return;
    void action.run(() => runMutation(() => addLanguage(selected)), onclose);
  }
</script>

<Modal open={true} title="Add Language" error={action.error} {onclose}>
  <p class="modal-info">
    Adding a language to serena config of project <strong>{projectName}</strong>.
  </p>
  <p class="modal-hint">
    Note that this may download dependencies for the language server and then start it; it may take
    a few seconds before the LS is responsive.
  </p>
  <Combobox {options} value={selected} onselect={(v) => (selected = v)} />
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={action.busy || !selected} onclick={add}
      >{#if action.busy}<Spinner />{:else}Add Language{/if}</Button
    >
  </div>
</Modal>
