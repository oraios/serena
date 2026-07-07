export function isValidMemoryName(name: string): boolean {
  return /^[A-Za-z0-9_]+(\/[A-Za-z0-9_]+)*$/.test(name);
}
