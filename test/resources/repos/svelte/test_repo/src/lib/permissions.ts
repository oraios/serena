import type { Role } from "$lib/roles";

export function canEdit(role: Role): boolean {
  return role === "admin";
}
