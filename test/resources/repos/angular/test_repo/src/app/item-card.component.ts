import { Component, Input } from '@angular/core';

@Component({
    selector: 'app-item-card',
    standalone: true,
    template: `
        <li class="item-card" [attr.data-label]="label">
            <strong>{{ label }}</strong>
        </li>
    `,
})
export class ItemCardComponent {
    @Input() label: string = '';

    formatLabel(): string {
        return this.label.trim();
    }
}
