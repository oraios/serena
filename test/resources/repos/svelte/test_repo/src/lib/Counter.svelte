<script lang="ts">
	let count: number = 0;

	export function increment() {
		count += 1;
	}

	export function decrement() {
		count -= 1;
	}

	export function reset() {
		count = 0;
	}
</script>

<div class="counter">
	<button on:click={decrement} aria-label="Decrease the counter by one">
		-
	</button>
	<div class="counter-viewport">
		<div class="counter-digits">
			<strong>{count}</strong>
		</div>
	</div>
	<button on:click={increment} aria-label="Increase the counter by one">
		+
	</button>
</div>

<style>
	.counter {
		display: flex;
		border-top: 1px solid rgba(0, 0, 0, 0.1);
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
		margin: 1rem 0;
	}

	.counter button {
		width: 2em;
		padding: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 0;
		background-color: transparent;
		font-size: 2rem;
	}

	.counter button:hover {
		background-color: var(--color-bg-1);
	}

	.counter-viewport {
		width: 8em;
		height: 4em;
		overflow: hidden;
		text-align: center;
		position: relative;
	}

	.counter-digits {
		position: absolute;
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2rem;
	}
</style>