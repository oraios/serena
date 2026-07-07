<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { removeLanguage } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { language, onclose }: { language: string; onclose: () => void } = $props();
</script>

<ConfirmModal onconfirm={() => runMutation(() => removeLanguage(language))} {onclose}>
  Remove language <strong>{language}</strong> from configuration?
</ConfirmModal>
