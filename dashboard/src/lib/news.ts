/** Sort news entries by YYYYMMDD id, newest first (matches the legacy dashboard). */
export function sortNewsEntries(news: Record<string, string>): Array<[string, string]> {
  return Object.entries(news).sort((a, b) => b[0].localeCompare(a[0]));
}
