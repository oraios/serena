<script setup lang="ts">
import Child from './Child.vue'
const label = 'hello'
</script>

<template>
  <Child :label="label" />
</template>
