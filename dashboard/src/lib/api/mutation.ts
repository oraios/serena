export interface MutationResult<T> {
  ok: boolean;
  message?: string;
  data?: T;
}

/**
 * Run a mutation endpoint call and normalize both failure channels:
 * a thrown ApiError (non-2xx) AND a 200-OK body of { status: 'error', message }.
 */
export async function runMutation<T extends { status?: string; message?: string }>(
  fn: () => Promise<T>,
): Promise<MutationResult<T>> {
  try {
    const data = await fn();
    if (data && data.status === 'error') {
      return { ok: false, message: data.message ?? 'Request failed', data };
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : 'Request failed' };
  }
}
