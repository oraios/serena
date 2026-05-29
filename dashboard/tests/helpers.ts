import { vi } from 'vitest';
import type { QueuedExecution } from '../src/lib/api/types';

/** Stub global fetch to always resolve with one JSON body (HTTP 200 unless overridden). */
export function stubFetchJson(body: unknown, status = 200) {
  const json = JSON.stringify(body);
  const fn = vi.fn().mockImplementation(() => Promise.resolve(new Response(json, { status })));
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** Static body OR a callable that receives the URL and returns the body. */
export type RouteBody = unknown | ((url: string) => unknown | Promise<unknown>);

/** Stub fetch with substring URL routing; first matching fragment wins, else `fallback`. */
export function stubFetchRoutes(routes: Record<string, RouteBody>, fallback: unknown = {}) {
  const fn = vi.fn(async (url: string) => {
    const hit = Object.entries(routes).find(([frag]) => String(url).includes(frag));
    const body = hit ? hit[1] : fallback;
    const resolved =
      typeof body === 'function' ? await (body as (u: string) => unknown)(String(url)) : body;
    return new Response(JSON.stringify(resolved), { status: 200 });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** The backend's soft-failure channel: HTTP 200 with `{status:'error', message}`. */
export const errBody = (message: string) => ({ status: 'error', message });
/** A success mutation body, optionally with extra fields (e.g. was_cancelled). */
export const okBody = (extra: object = {}) => ({ status: 'success', ...extra });

/** Build a QueuedExecution fixture with sensible defaults. */
export function exec(over: Partial<QueuedExecution> = {}): QueuedExecution {
  return {
    task_id: 1,
    is_running: false,
    name: 'task',
    display_name: 'task',
    finished_successfully: true,
    logged: true,
    started_at: null,
    finished_at: null,
    duration_ms: null,
    error_message: null,
    ...over,
  };
}
