// TypeScript interfaces and types
export interface User {
    id: number;
    name: string;
    email: string;
}

// Traditional TypeScript class (no Svelte reactivity needed)
export class UserManager {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    getUser(id: number): User | undefined {
        return this.users.find((user) => user.id === id);
    }

    getAllUsers(): User[] {
        return [...this.users];
    }
}