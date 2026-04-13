import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
    console.log('TVL extension activated');

    // Create diagnostic collection for validation errors
    diagnosticCollection = vscode.languages.createDiagnosticCollection('tvl');
    context.subscriptions.push(diagnosticCollection);

    // Register validate command
    const validateCmd = vscode.commands.registerCommand('tvl.validate', async () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && isTvlFile(editor.document)) {
            await validateDocument(editor.document);
        } else {
            vscode.window.showWarningMessage('No TVL file is open');
        }
    });
    context.subscriptions.push(validateCmd);

    // Register lint command
    const lintCmd = vscode.commands.registerCommand('tvl.lint', async () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && isTvlFile(editor.document)) {
            await lintDocument(editor.document);
        } else {
            vscode.window.showWarningMessage('No TVL file is open');
        }
    });
    context.subscriptions.push(lintCmd);

    // Validate on save if enabled
    const onSaveDisposable = vscode.workspace.onDidSaveTextDocument(async (document) => {
        const config = vscode.workspace.getConfiguration('tvl');
        if (config.get('validation.enable') && config.get('validation.onSave') && isTvlFile(document)) {
            await validateDocument(document);
        }
    });
    context.subscriptions.push(onSaveDisposable);

    // Clear diagnostics when document is closed
    const onCloseDisposable = vscode.workspace.onDidCloseTextDocument((document) => {
        diagnosticCollection.delete(document.uri);
    });
    context.subscriptions.push(onCloseDisposable);
}

function isTvlFile(document: vscode.TextDocument): boolean {
    return document.fileName.endsWith('.tvl.yml') || document.fileName.endsWith('.tvl.yaml');
}

async function validateDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('tvl');
    const cliPath = config.get<string>('cli.path', 'tvl-validate');

    try {
        const { stdout } = await execAsync(`${cliPath} "${document.fileName}" --format json`);
        const result = JSON.parse(stdout);

        const diagnostics: vscode.Diagnostic[] = [];

        if (!result.ok) {
            if (result.error) {
                // General error
                const diagnostic = new vscode.Diagnostic(
                    new vscode.Range(0, 0, 0, 0),
                    result.error,
                    vscode.DiagnosticSeverity.Error
                );
                diagnostic.source = 'tvl-validate';
                diagnostics.push(diagnostic);
            }

            if (result.issues) {
                for (const issue of result.issues) {
                    const line = (issue.line || 1) - 1;
                    const diagnostic = new vscode.Diagnostic(
                        new vscode.Range(line, 0, line, 1000),
                        issue.message || issue.description || 'Validation error',
                        getSeverity(issue.severity || 'error')
                    );
                    diagnostic.source = 'tvl-validate';
                    if (issue.code) {
                        diagnostic.code = issue.code;
                    }
                    diagnostics.push(diagnostic);
                }
            }
        }

        diagnosticCollection.set(document.uri, diagnostics);

        if (result.ok) {
            vscode.window.showInformationMessage('TVL validation passed');
        }
    } catch (error: any) {
        // Try to parse JSON error output
        if (error.stdout) {
            try {
                const result = JSON.parse(error.stdout);
                const diagnostics: vscode.Diagnostic[] = [];

                if (result.error) {
                    const diagnostic = new vscode.Diagnostic(
                        new vscode.Range(0, 0, 0, 0),
                        result.error,
                        vscode.DiagnosticSeverity.Error
                    );
                    diagnostic.source = 'tvl-validate';
                    diagnostics.push(diagnostic);
                }

                diagnosticCollection.set(document.uri, diagnostics);
                return;
            } catch {
                // Not JSON, fall through
            }
        }

        vscode.window.showErrorMessage(`TVL validation failed: ${error.message || error}`);
    }
}

async function lintDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('tvl');
    const cliPath = config.get<string>('cli.path', 'tvl-validate').replace('validate', 'lint');

    try {
        const { stdout } = await execAsync(`${cliPath} "${document.fileName}" --format json`);
        const result = JSON.parse(stdout);

        const diagnostics: vscode.Diagnostic[] = [];

        if (result.issues && result.issues.length > 0) {
            for (const issue of result.issues) {
                const line = (issue.line || 1) - 1;
                const diagnostic = new vscode.Diagnostic(
                    new vscode.Range(line, 0, line, 1000),
                    issue.message || issue.description || 'Lint warning',
                    getSeverity(issue.severity || 'warning')
                );
                diagnostic.source = 'tvl-lint';
                if (issue.code) {
                    diagnostic.code = issue.code;
                }
                diagnostics.push(diagnostic);
            }
        }

        diagnosticCollection.set(document.uri, diagnostics);

        if (result.ok && (!result.issues || result.issues.length === 0)) {
            vscode.window.showInformationMessage('TVL lint passed - no issues found');
        } else if (result.issues) {
            vscode.window.showWarningMessage(`TVL lint found ${result.issues.length} issue(s)`);
        }
    } catch (error: any) {
        vscode.window.showErrorMessage(`TVL lint failed: ${error.message || error}`);
    }
}

function getSeverity(severity: string): vscode.DiagnosticSeverity {
    switch (severity.toLowerCase()) {
        case 'error':
            return vscode.DiagnosticSeverity.Error;
        case 'warning':
            return vscode.DiagnosticSeverity.Warning;
        case 'info':
        case 'information':
            return vscode.DiagnosticSeverity.Information;
        case 'hint':
            return vscode.DiagnosticSeverity.Hint;
        default:
            return vscode.DiagnosticSeverity.Error;
    }
}

export function deactivate() {
    if (diagnosticCollection) {
        diagnosticCollection.dispose();
    }
}
