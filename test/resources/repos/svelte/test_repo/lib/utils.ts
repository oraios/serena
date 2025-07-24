// Utility functions for the Svelte application

export function formatName(firstName: string, lastName: string): string {
    return `${firstName} ${lastName}`.trim();
}

export function validateEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// Configuration type
export interface ApiConfig {
    baseUrl: string;
    timeout: number;
    headers: Record<string, string>;
}

export const defaultConfig: ApiConfig = {
    baseUrl: 'https://api.example.com',
    timeout: 5000,
    headers: {
        'Content-Type': 'application/json'
    }
};

// Simple API client class
export class ApiClient {
    constructor(private config: ApiConfig) {}

    async get(endpoint: string): Promise<any> {
        const url = `${this.config.baseUrl}${endpoint}`;
        const response = await fetch(url, {
            method: 'GET',
            headers: this.config.headers
        });
        return response.json();
    }

    async post(endpoint: string, data: any): Promise<any> {
        const url = `${this.config.baseUrl}${endpoint}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: this.config.headers,
            body: JSON.stringify(data)
        });
        return response.json();
    }
}