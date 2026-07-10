/**
 * Format a number with thousands separators.
 */
export function formatNumber(value: number): string {
  return value.toLocaleString();
}

/**
 * Format a date to locale string.
 */
export function formatDate(date: Date): string {
  return date.toLocaleDateString();
}
