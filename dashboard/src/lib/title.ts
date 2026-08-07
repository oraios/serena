export function pageTitle(project: string | null | undefined): string {
  return project ? `${project} – Serena Dashboard` : 'Serena Dashboard';
}
