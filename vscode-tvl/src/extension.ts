import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

let diagnosticCollection: vscode.DiagnosticCollection;

export const MODULE_SCHEMA_RELATIVE_PATH = 'schemas/tvl.schema.json';
export const PACK_SCHEMA_RELATIVE_PATH = 'schemas/tvl-pack.schema.json';
export const YAML_SCHEMA_SCHEME = 'tvl-schema';

export interface TvlCliIssue {
    code?: string;
    message?: string;
    description?: string;
    path?: Array<string | number> | string;
    severity?: string;
    line?: number;
}

export interface TvlCliResult {
    ok?: boolean;
    file?: string;
    schema_ok?: boolean;
    document_kind?: string;
    error?: string;
    issues?: TvlCliIssue[];
}

export function activate(context: vscode.ExtensionContext) {
    console.log('TVL extension activated');

    // Create diagnostic collection for validation errors
    diagnosticCollection = vscode.languages.createDiagnosticCollection('tvl');
    context.subscriptions.push(diagnosticCollection);

    // Register dynamic YAML schema contributor when redhat.vscode-yaml is present
    void registerYamlSchemaContributor(context);

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

export function isTvlFileName(fileName: string): boolean {
    const lower = fileName.toLowerCase();
    return lower.endsWith('.tvl.yml') || lower.endsWith('.tvl.yaml');
}

export function isTvlPackFileName(fileName: string): boolean {
    const lower = fileName.toLowerCase();
    return (
        lower.endsWith('.pack.tvl.yml') ||
        lower.endsWith('.pack.tvl.yaml') ||
        lower.endsWith('-pack.tvl.yml') ||
        lower.endsWith('-pack.tvl.yaml')
    );
}

export function isTvlPackContent(content: string): boolean {
    let hasTopLevelPack = false;
    let hasTopLevelTvl = false;
    for (const rawLine of content.split(/\r?\n/)) {
        const trimmed = rawLine.trim();
        if (!trimmed || trimmed.startsWith('#')) {
            continue;
        }
        if (/^pack\s*:/.test(rawLine)) {
            hasTopLevelPack = true;
        } else if (/^tvl\s*:/.test(rawLine)) {
            hasTopLevelTvl = true;
        }
    }
    return hasTopLevelPack && !hasTopLevelTvl;
}

export function isTvlPackDocument(content: string, fileName: string = ''): boolean {
    return isTvlPackFileName(fileName) || isTvlPackContent(content);
}

export function getBundledSchemaPath(
    extensionPath: string,
    fileName: string,
    content?: string,
): string {
    const relativePath = isTvlPackDocument(content ?? '', fileName)
        ? PACK_SCHEMA_RELATIVE_PATH
        : MODULE_SCHEMA_RELATIVE_PATH;
    return path.join(extensionPath, relativePath);
}

async function registerYamlSchemaContributor(context: vscode.ExtensionContext): Promise<void> {
    try {
        const yamlExt = vscode.extensions?.getExtension?.('redhat.vscode-yaml');
        if (!yamlExt) {
            return;
        }
        const yamlApi = yamlExt.isActive ? yamlExt.exports : await yamlExt.activate();
        if (!yamlApi || typeof yamlApi.registerContributor !== 'function') {
            return;
        }

        const extensionPath = context.extensionPath || path.resolve(__dirname, '..');

        yamlApi.registerContributor(
            YAML_SCHEMA_SCHEME,
            (resource: string): string | undefined => {
                let filePath = resource;
                try {
                    filePath = vscode.Uri.parse(resource).fsPath || resource;
                } catch {
                    // Keep raw resource string
                }
                if (!isTvlFileName(filePath)) {
                    return undefined;
                }

                let content = '';
                const openDoc = vscode.workspace.textDocuments?.find(
                    (doc) => doc.uri.toString() === resource || doc.fileName === filePath,
                );
                if (openDoc) {
                    content = openDoc.getText();
                } else if (fs.existsSync(filePath)) {
                    try {
                        content = fs.readFileSync(filePath, 'utf8');
                    } catch {
                        content = '';
                    }
                }

                const schemaRel = isTvlPackDocument(content, filePath)
                    ? PACK_SCHEMA_RELATIVE_PATH
                    : MODULE_SCHEMA_RELATIVE_PATH;
                return `${YAML_SCHEMA_SCHEME}://${schemaRel}`;
            },
            (schemaUri: string): string | undefined => {
                const prefix = `${YAML_SCHEMA_SCHEME}://`;
                if (!schemaUri.startsWith(prefix)) {
                    return undefined;
                }
                const relativePath = schemaUri.slice(prefix.length);
                if (
                    relativePath !== MODULE_SCHEMA_RELATIVE_PATH &&
                    relativePath !== PACK_SCHEMA_RELATIVE_PATH
                ) {
                    return undefined;
                }
                const fullPath = path.join(extensionPath, relativePath);
                try {
                    return fs.readFileSync(fullPath, 'utf8');
                } catch {
                    return undefined;
                }
            },
        );
    } catch {
        // YAML extension integration is optional
    }
}

function isTvlFile(document: vscode.TextDocument): boolean {
    return isTvlFileName(document.fileName);
}

export function formatIssueFieldPath(pathValue: unknown): string {
    if (Array.isArray(pathValue)) {
        return pathValue.length > 0 ? pathValue.map((part) => String(part)).join('.') : '<root>';
    }
    if (typeof pathValue === 'string') {
        const trimmed = pathValue.trim();
        return trimmed.length > 0 ? trimmed : '<root>';
    }
    return '';
}

export function formatIssueMessage(
    issue: TvlCliIssue,
    fallbackMessage: string = 'Validation error',
): string {
    const baseMessage = issue.message || issue.description || fallbackMessage;
    const fieldPath = formatIssueFieldPath(issue.path);
    if (!fieldPath) {
        return baseMessage;
    }
    if (baseMessage.startsWith(`${fieldPath}:`)) {
        return baseMessage;
    }
    return `${fieldPath}: ${baseMessage}`;
}

function escapeRegExp(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function resolveIssueLine(issue: TvlCliIssue, documentText?: string): number {
    if (typeof issue.line === 'number' && Number.isFinite(issue.line) && issue.line >= 1) {
        return Math.floor(issue.line) - 1;
    }
    if (typeof documentText !== 'string' || !Array.isArray(issue.path) || issue.path.length === 0) {
        return 0;
    }

    const lines = documentText.split(/\r?\n/);
    let currentLine = 0;
    let matchedLine = 0;

    for (const segment of issue.path) {
        if (typeof segment === 'number') {
            let listStartIndent: number | undefined;
            let seenItems = 0;
            let foundItemLine = -1;
            for (let i = currentLine; i < lines.length; i++) {
                const raw = lines[i];
                const trimmed = raw.trim();
                if (!trimmed || trimmed.startsWith('#')) {
                    continue;
                }
                const indent = raw.search(/\S/);
                if (i > currentLine && listStartIndent !== undefined && indent < listStartIndent) {
                    break;
                }
                // trimStart() instead of a /^(\s*)-\s*(.*)$/ match: the regex backtracks
                // polynomially on long runs of whitespace (CodeQL js/polynomial-redos).
                const afterIndent = raw.trimStart();
                if (afterIndent.startsWith('-')) {
                    const itemIndent = raw.length - afterIndent.length;
                    if (listStartIndent === undefined) {
                        listStartIndent = itemIndent;
                    }
                    if (itemIndent === listStartIndent) {
                        if (seenItems === segment) {
                            foundItemLine = i;
                            break;
                        }
                        seenItems++;
                    }
                }
            }
            if (foundItemLine !== -1) {
                currentLine = foundItemLine;
                matchedLine = foundItemLine;
            }
        } else {
            const key = String(segment);
            const keyPattern = new RegExp(`(?:^\\s*(?:-\\s*)?|[{,]\\s*)${escapeRegExp(key)}\\s*:`);
            let foundKeyLine = -1;
            for (let i = currentLine; i < lines.length; i++) {
                const raw = lines[i];
                const trimmed = raw.trim();
                if (!trimmed || trimmed.startsWith('#')) {
                    continue;
                }
                if (keyPattern.test(raw)) {
                    foundKeyLine = i;
                    break;
                }
            }
            if (foundKeyLine !== -1) {
                currentLine = foundKeyLine;
                matchedLine = foundKeyLine;
            }
        }
    }

    return matchedLine;
}

export function createDiagnosticsFromResult(
    result: TvlCliResult,
    source: 'tvl-validate' | 'tvl-lint',
    defaultSeverity: string = 'error',
    documentText?: string,
): vscode.Diagnostic[] {
    const diagnostics: vscode.Diagnostic[] = [];

    if (result.error) {
        const diagnostic = new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 0),
            result.error,
            vscode.DiagnosticSeverity.Error,
        );
        diagnostic.source = source;
        diagnostics.push(diagnostic);
    }

    if (Array.isArray(result.issues)) {
        const fallbackMessage = source === 'tvl-lint' ? 'Lint warning' : 'Validation error';
        for (const issue of result.issues) {
            const line = resolveIssueLine(issue, documentText);
            const diagnostic = new vscode.Diagnostic(
                new vscode.Range(line, 0, line, 1000),
                formatIssueMessage(issue, fallbackMessage),
                getSeverity(issue.severity || defaultSeverity),
            );
            diagnostic.source = source;
            if (issue.code) {
                diagnostic.code = issue.code;
            }
            diagnostics.push(diagnostic);
        }
    }

    return diagnostics;
}

function parseErrorStdoutJson(error: any): TvlCliResult | undefined {
    if (typeof error?.stdout !== 'string' || error.stdout.trim().length === 0) {
        return undefined;
    }
    try {
        return JSON.parse(error.stdout);
    } catch {
        return undefined;
    }
}

export async function validateDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('tvl');
    const cliPath = config.get<string>('cli.path', 'tvl-validate');

    let result: TvlCliResult;
    try {
        const { stdout } = await runTvlCli(cliPath, document.fileName);
        result = JSON.parse(stdout);
    } catch (error: any) {
        const parsed = parseErrorStdoutJson(error);
        if (!parsed) {
            vscode.window.showErrorMessage(`TVL validation failed: ${error.message || error}`);
            return;
        }
        result = parsed;
    }

    const documentText = typeof document.getText === 'function' ? document.getText() : undefined;
    const diagnostics =
        !result.ok || (Array.isArray(result.issues) && result.issues.length > 0)
            ? createDiagnosticsFromResult(result, 'tvl-validate', 'error', documentText)
            : [];

    diagnosticCollection.set(document.uri, diagnostics);

    if (result.ok && diagnostics.length === 0) {
        vscode.window.showInformationMessage('TVL validation passed');
    }
}

export function resolveLintCliPath(validatePath: string, configuredPath: string = ''): string {
    const explicitPath = configuredPath.trim();
    if (explicitPath) {
        return explicitPath;
    }
    const paths = validatePath.includes('\\') ? path.win32 : path.posix;
    const match = /^tvl-validate(\.exe)?$/.exec(paths.basename(validatePath));
    if (!match) {
        throw new Error('Set tvl.lint.path when tvl.cli.path uses a custom executable name');
    }
    return paths.join(paths.dirname(validatePath), `tvl-lint${match[1] ?? ''}`);
}

export async function lintDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('tvl');
    let cliPath: string;
    try {
        cliPath = resolveLintCliPath(
            config.get<string>('cli.path', 'tvl-validate'),
            config.get<string>('lint.path', ''),
        );
    } catch (error: any) {
        // No lint ran, so any squiggles still in the gutter are from an earlier
        // run and no longer describe a check that happened.
        diagnosticCollection.delete(document.uri);
        vscode.window.showErrorMessage(`TVL lint configuration error: ${error.message || error}`);
        return;
    }

    let result: TvlCliResult;
    try {
        const { stdout } = await runTvlCli(cliPath, document.fileName);
        result = JSON.parse(stdout);
    } catch (error: any) {
        const parsed = parseErrorStdoutJson(error);
        if (!parsed) {
            vscode.window.showErrorMessage(`TVL lint failed: ${error.message || error}`);
            return;
        }
        result = parsed;
    }

    const documentText = typeof document.getText === 'function' ? document.getText() : undefined;
    const diagnostics = createDiagnosticsFromResult(result, 'tvl-lint', 'warning', documentText);

    diagnosticCollection.set(document.uri, diagnostics);

    if (result.ok && (!result.issues || result.issues.length === 0)) {
        vscode.window.showInformationMessage('TVL lint passed - no issues found');
    } else if (result.issues && result.issues.length > 0) {
        vscode.window.showWarningMessage(`TVL lint found ${result.issues.length} issue(s)`);
    }
}

export function buildTvlCliArguments(documentPath: string): string[] {
    return [documentPath, '--format', 'json'];
}

async function runTvlCli(cliPath: string, documentPath: string): Promise<{ stdout: string }> {
    return execFileAsync(cliPath, buildTvlCliArguments(documentPath));
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
