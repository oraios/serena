<script lang="ts">
  import Button from './lib/Button.svelte';
  import { count, currentUser, incrementCount, resetCount, setCurrentUser } from './lib/store.svelte.ts';
  import { UserManager, type User } from './lib/store';
  import { formatName, validateEmail, ApiClient, defaultConfig } from './lib/utils';
  
  interface Props {
    name?: string;    
  }

  let { name = 'World' }: Props = $props();
  
  const userManager = new UserManager();
  const apiClient = new ApiClient(defaultConfig);

  function handleClick() {
    console.log('Hello from App!');
  }

  function handleIncrement() {
    incrementCount();
  }

  function handleReset() {
    resetCount();
  }

  function createTestUser() {
    const testUser: User = {
      id: 1,
      name: 'John Doe',
      email: 'john@example.com'
    };
    
    if (validateEmail(testUser.email)) {
      userManager.addUser(testUser);
      setCurrentUser(testUser);
    }
  }

  async function fetchData() {
    try {
      const data = await apiClient.get('/users');
      console.log('Fetched data:', data);
    } catch (error) {
      console.error('Error fetching data:', error);
    }
  }
</script>

<main>
  <h1>Hello {name}!</h1>
  <Button onclick={handleClick} text="Click me" />
  <Button onclick={handleIncrement} text="Count: {count}" />
  <Button onclick={handleReset} text="Reset" />
  <Button onclick={createTestUser} text="Create User" />
  <Button onclick={fetchData} text="Fetch Data" />
  
  {#if currentUser}
    <p>Current user: {formatName(currentUser.name.split(' ')[0], currentUser.name.split(' ')[1] || '')}</p>
  {/if}
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