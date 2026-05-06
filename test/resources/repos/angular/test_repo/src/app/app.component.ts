import { Component, signal } from '@angular/core';
import { GreetingService } from './greeting.service';
import { ItemCardComponent } from './item-card.component';
import { ExclaimPipe } from './exclaim.pipe';

@Component({
    selector: 'app-root',
    standalone: true,
    imports: [ItemCardComponent, ExclaimPipe],
    templateUrl: './app.component.html',
})
export class AppComponent {
    readonly title = signal('Serena Angular Test');
    readonly userName = signal('');
    readonly items = signal<string[]>(['alpha', 'beta', 'gamma']);

    constructor(private readonly greetings: GreetingService) {}

    greeting(): string {
        return this.greetings.greet(this.userName() || undefined);
    }

    setName(name: string): void {
        this.userName.set(name);
    }
}
