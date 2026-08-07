export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status} for ${res.url}`);
  return (await res.json()) as T;
}

export async function getJson<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path));
}

export async function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    }),
  );
}

export async function putJson<T = unknown>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { method: 'PUT' }));
}
