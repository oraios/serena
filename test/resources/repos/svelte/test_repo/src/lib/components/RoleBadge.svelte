<script lang="ts">
	import type { Role } from '$lib/roles';
	import { roleLabel } from '$lib/roles';

	let { role }: { role: Role } = $props();

	const label = $derived(roleLabel(role));
</script>

<span class="role-badge">{label}</span>
