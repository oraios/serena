import { Injectable } from '@angular/core';
import { Greeter } from './greeter.interface';

@Injectable({ providedIn: 'root' })
export class GreetingService implements Greeter {
    private readonly defaultName = 'World';

    greet(name?: string): string {
        return `Hello, ${name ?? this.defaultName}!`;
    }
}
