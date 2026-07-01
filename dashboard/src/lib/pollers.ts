export type View = 'overview' | 'logs' | 'stats' | 'code';
export type PollerName = 'config' | 'queued' | 'logs' | 'timeline';

/** Which pollers should be running for a given view. Pure so it is unit-testable. */
export function pollersForView(view: View): PollerName[] {
  switch (view) {
    case 'overview':
      return ['config', 'queued', 'timeline'];
    case 'logs':
      return ['logs'];
    case 'stats':
      return ['config', 'timeline'];
    case 'code':
      return ['config'];
  }
}
