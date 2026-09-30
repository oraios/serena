import { Component } from '@angular/core';

// Inline-template diagnostics fixture.
//
// ``{{ missingField }}`` is only an error to something that type-checks the template
// *inside* the .ts file: plain tsserver sees a template literal and reports nothing.
// The companion typescript-language-server flags it because @angular/language-service
// is loaded into it as a tsserver plugin — which is what makes the companion a safe
// sole source of published .ts diagnostics. If the plugin ever stops loading, this is
// the fixture that fails.
@Component({
    selector: 'app-inline-template-sample',
    standalone: true,
    template: `<span>{{ missingField }}</span>`,
})
export class InlineTemplateSampleComponent {
    readonly label: string = 'present';
}
