export function formatNumber(num: number): string {
    return new Intl.NumberFormat('en-US').format(num);
}

export function calculateSum(a: number, b: number): number {
    return a + b;
}

export interface User {
    id: number;
    name: string;
    email: string;
}

export class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    getUser(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }

    getAllUsers(): User[] {
        return [...this.users];
    }
}