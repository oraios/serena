<script lang="ts">
  interface Props {
    text?: string;
    disabled?: boolean;
    onclick?: () => void;
  }
  
  let { text = 'Button', disabled = false, onclick }: Props = $props();
  
  function handleClick() {
    onclick?.();
  }
</script>

<button {disabled} onclick={handleClick}>
  {text}
</button>

<style>
  button {
    background-color: #ff3e00;
    color: white;
    border: none;
    padding: 0.5em 1em;
    border-radius: 4px;
    cursor: pointer;
  }
  
  button:hover {
    background-color: #ff5722;
  }
  
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>