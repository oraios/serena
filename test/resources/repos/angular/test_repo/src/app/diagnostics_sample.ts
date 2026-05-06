import { Component } from '@angular/core';

// Two diagnostic sources in one fixture:
//   * the type error on ``count`` is reported by tsserver via the Angular plugin
//     when diagnosing this .ts file directly.
//   * the ``undefinedSignal()`` reference in diagnostics_sample.html is reported
//     by ngserver when diagnosing the template attached via ``templateUrl``.
@Component({
    selector: 'app-diagnostics-sample',
    standalone: true,
    templateUrl: './diagnostics_sample.html',
})
export class DiagnosticsSampleComponent {
    readonly count: number = 'not-a-number';
}
