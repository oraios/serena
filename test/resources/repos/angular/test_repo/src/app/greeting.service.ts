import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class GreetingService {
    private readonly defaultName = 'World';

    greet(name?: string): string {
        return `Hello, ${name ?? this.defaultName}!`;
    }
}
