import { rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const dir = fileURLToPath(new URL('../../src/serena/resources/dashboard/assets', import.meta.url));
rmSync(dir, { recursive: true, force: true });
