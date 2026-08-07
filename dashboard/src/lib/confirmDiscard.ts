/** Returns true if it's safe to close: not dirty, or the user confirmed discarding. */
export function confirmDiscard(isDirty: boolean): boolean {
  return !isDirty || window.confirm('You have unsaved changes. Discard them?');
}
