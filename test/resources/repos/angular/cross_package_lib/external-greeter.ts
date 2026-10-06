// A package OUTSIDE the Angular app, wired up in tests via additional_workspace_folders.
// It implements the app's Greeter interface, so references to that interface only reach
// this file if the language server actually loaded this folder's project.
import { Greeter } from '../test_repo/src/app/greeter.interface';

export class ExternalGreeter implements Greeter {
    greet(name?: string): string {
        return `Salut, ${name ?? 'monde'}!`;
    }
}
