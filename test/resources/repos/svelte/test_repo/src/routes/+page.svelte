<script lang="ts">
	import Counter from '$lib/Counter.svelte';
	import { formatNumber, calculateSum } from '$lib/utils';

	let value1 = 100;
	let value2 = 200;
	$: total = calculateSum(value1, value2);
	$: formattedTotal = formatNumber(total);
</script>

<svelte:head>
	<title>Home</title>
	<meta name="description" content="Svelte demo app" />
</svelte:head>

<section>
	<h1>Welcome to SvelteKit</h1>

	<Counter />

	<div>
		<p>Value 1: {value1}</p>
		<p>Value 2: {value2}</p>
		<p>Total: {formattedTotal}</p>
	</div>
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 2rem;
	}

	h1 {
		width: 100%;
		text-align: center;
	}
</style>