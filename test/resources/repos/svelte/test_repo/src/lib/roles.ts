export type Role = "admin" | "member";

export const ROLES: Role[] = ["admin", "member"];

export function isRole(value: string): value is Role {
  return (ROLES as string[]).includes(value);
}

export function roleLabel(role: Role): string {
  return role === "admin" ? "Administrator" : "Member";
}
