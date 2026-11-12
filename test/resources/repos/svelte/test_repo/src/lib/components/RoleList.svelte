<script lang="ts">
	import {
		ROLES,
		roleLabel
	} from '$lib/roles';
</script>

<ul>
	{#each ROLES as role}
		<li title={roleLabel(role)}>{roleLabel(role)}</li>
	{/each}
</ul>
