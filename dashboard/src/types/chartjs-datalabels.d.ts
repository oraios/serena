// Type-only side-effect import: pulls in chartjs-plugin-datalabels' module
// augmentation so `options.plugins.datalabels` typechecks across the project.
// Erased at runtime (.d.ts files emit nothing); the runtime import lives in
// ChartPanel.svelte. Replaces the old frappe-charts.d.ts ambient shim.
import 'chartjs-plugin-datalabels';
