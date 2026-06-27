import process from 'node:process';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
// Disable CSS preprocessing in test/check environments to avoid Vite 6
// PartialEnvironment errors when a fully resolved config isn't available.
const isTest = process.env.VITEST === 'true' || process.env.NODE_ENV === 'test';
export default { preprocess: vitePreprocess({ style: !isTest }) };
