export type View = 'overview' | 'logs' | 'stats';
export type PollerName = 'config' | 'queued' | 'last' | 'logs';

/** Which pollers should be running for a given view. Pure so it is unit-testable. */
export function pollersForView(view: View): PollerName[] {
  switch (view) {
    case 'overview':
      return ['config', 'queued', 'last'];
    case 'logs':
      return ['logs'];
    case 'stats':
      return [];
  }
}
