<script lang="ts">
	import { isRole } from '$lib/roles';

	let { value }: { value: string } = $props();
</script>

{#if isRole(value)}
	<p>valid role</p>
{/if}
