<script lang="ts">
  import Button from './lib/Button.svelte';
  import { count } from './lib/store.js';
  
  interface Props {
    name?: string;
  }
  
  let { name = 'World' }: Props = $props();
  
  function handleClick() {
    console.log('Hello from App!');
  }
  
  function incrementCount() {
    count.update(n => n + 1);
  }
</script>

<main>
  <h1>Hello {name}!</h1>
  <Button onclick={handleClick} text="Click me" />
  <Button onclick={incrementCount} text="Count: {$count}" />
</main>

<style>
  main {
    text-align: center;
    padding: 1em;
    max-width: 240px;
    margin: 0 auto;
  }
  
  h1 {
    color: #ff3e00;
    text-transform: uppercase;
    font-size: 4em;
    font-weight: 100;
  }
</style>