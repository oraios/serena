import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';

// Restore stubs/spies after every test so individual files don't each repeat this.
afterEach(() => vi.restoreAllMocks());

// Node 26 exposes an experimental (undefined) localStorage/sessionStorage that shadows
// jsdom's implementations. Vitest's populateGlobal skips keys already present on the
// Node global, so we must manually install jsdom's Storage objects after env setup.
// jsdom.window exists on the global as `jsdom` (injected by vitest's jsdom environment).
const jsdomWindow = (globalThis as unknown as { jsdom?: { window: Window } }).jsdom?.window;
if (jsdomWindow) {
  const lsDesc =
    Object.getOwnPropertyDescriptor(jsdomWindow, '_localStorage') ??
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(jsdomWindow), 'localStorage');
  const ssDesc =
    Object.getOwnPropertyDescriptor(jsdomWindow, '_sessionStorage') ??
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(jsdomWindow), 'sessionStorage');

  if (lsDesc) {
    Object.defineProperty(globalThis, 'localStorage', {
      get: lsDesc.get ? () => lsDesc.get!.call(jsdomWindow) : () => lsDesc.value,
      configurable: true,
    });
  }
  if (ssDesc) {
    Object.defineProperty(globalThis, 'sessionStorage', {
      get: ssDesc.get ? () => ssDesc.get!.call(jsdomWindow) : () => ssDesc.value,
      configurable: true,
    });
  }
}
