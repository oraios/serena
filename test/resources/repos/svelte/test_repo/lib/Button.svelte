<script lang="ts">
  import { formatName } from './utils';
  import type { User } from './store';

  interface Props {
    text: string;
    onclick?: () => void;
    disabled?: boolean;
    user?: User;
  }

  let { text, onclick, disabled = false, user }: Props = $props();

  function handleClick() {
    if (onclick) {
      onclick();
    }
    console.log('Button clicked');
  }

  function getDisplayText(): string {
    if (user) {
      return `${text} - ${formatName(user.name.split(' ')[0], user.name.split(' ')[1] || '')}`;
    }
    return text;
  }
</script>

<button {disabled} onclick={handleClick} class={disabled ? 'disabled' : ''}>
  {getDisplayText()}
</button>

<style>
  button {
    background-color: #ff3e00;
    color: white;
    border: none;
    padding: 0.5em 1em;
    border-radius: 4px;
    cursor: pointer;
    font-size: 1em;
  }
  
  button:hover:not(.disabled) {
    background-color: #ff1e00;
  }
  
  button.disabled {
    background-color: #ccc;
    cursor: not-allowed;
  }
</style>