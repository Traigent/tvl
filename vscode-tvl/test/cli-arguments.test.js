const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const Module = require("node:module");

const vscodeTvlRoot = path.join(__dirname, "..");
const repoRoot = path.join(vscodeTvlRoot, "..");

const extensionSource = fs.readFileSync(
    path.join(vscodeTvlRoot, "src", "extension.ts"),
    "utf8",
);

test("uses execFile with the document path as a discrete argument", () => {
    assert.match(
        extensionSource,
        /execFileAsync\(cliPath, buildTvlCliArguments\(documentPath\)\)/,
    );
    assert.match(
        extensionSource,
        /return \[documentPath, '--format', 'json'\];/,
    );
    assert.doesNotMatch(extensionSource, /execAsync\(/);
});

const manifest = JSON.parse(
    fs.readFileSync(path.join(vscodeTvlRoot, "package.json"), "utf8"),
);

test("restricts CLI configuration to trusted machine scope", () => {
    assert.equal(
        manifest.contributes.configuration.properties["tvl.cli.path"].scope,
        "machine",
    );
    assert.equal(manifest.capabilities.untrustedWorkspaces.supported, false);
});

test("keeps syntax grammar synced with editor_shared and covers TVL 1.3 constructs", () => {
    const extGrammarRaw = fs.readFileSync(
        path.join(vscodeTvlRoot, "syntaxes", "tvl.tmLanguage.json"),
        "utf8",
    );
    const sharedGrammarRaw = fs.readFileSync(
        path.join(repoRoot, "editor_shared", "vscode", "tvl.tmLanguage.json"),
        "utf8",
    );
    assert.equal(extGrammarRaw, sharedGrammarRaw);

    const grammar = JSON.parse(extGrammarRaw);
    const allRegexes = grammar.patterns
        .map((p) => p.match || "")
        .filter(Boolean);
    const matchesAny = (sample) =>
        allRegexes.some((rx) => new RegExp(rx, "m").test(sample));

    for (const block of ["requirements:", "monitors:", "responses:", "pack:", "tvl_pack:"]) {
        assert.ok(matchesAny(block), `expected grammar to match block ${block}`);
    }
    for (const key of [
        "kind:",
        "unit:",
        "among:",
        "violation:",
        "max_rate:",
        "within_hours:",
        "max_stale_windows:",
        "pattern:",
        "correlate_by:",
        "within_ms:",
        "tumbling_hours:",
        "grace_minutes:",
        "false_alarm_budget:",
        "horizon_days:",
        "min_samples:",
        "max_unresolved_fraction:",
        "threshold_factor:",
        "closure_windows:",
        "closure_max_age_hours:",
        "max_active_obligations:",
        "max_tracked_correlations:",
        "trigger:",
        "do:",
        "approval:",
        "rate_floor:",
        "on_check_error:",
    ]) {
        assert.ok(matchesAny(key), `expected grammar to match key ${key}`);
    }
    for (const token of [
        "rate_bound",
        "zero_tolerance",
        "recovery_time",
        "evidence_liveness",
        "absence",
        "bounded_existence",
        "precedence",
        "bounded_response",
        "protocol",
        "unit_start",
        "unit_end",
        "tool_call",
        "tool_result",
        "model_call",
        "handoff",
        "error",
        "authorization_granted",
        "authorization_revoked",
        "episode_opened",
        "episode_continued",
        "episode_open_for",
        "episode_resolved",
        "episode_withdrawn",
        "recovery_overdue",
        "recovery_cancelled",
        "recovery_recovered",
        "burn_breached",
        "stale",
        "live_again",
        "unit_violation",
        "notify",
        "open_next_step",
        "optimize",
        "rollback",
        "throttle",
        "degrade",
        "suspend",
        "block_action",
        "halt_unit",
        "none",
        "standing",
        "human",
        "clopper_pearson_rational_v2",
        "clopper_pearson_exact_v1",
        "exact_count_v1",
        "backend_v1",
        "tenant_floor",
    ]) {
        assert.ok(matchesAny(token), `expected grammar to match token ${token}`);
    }
});

test("ships all six TVL 1.3 snippets synced with editor_shared", () => {
    const extSnippetsRaw = fs.readFileSync(
        path.join(vscodeTvlRoot, "snippets", "tvl.code-snippets"),
        "utf8",
    );
    const sharedSnippetsRaw = fs.readFileSync(
        path.join(repoRoot, "editor_shared", "vscode", "tvl.code-snippets"),
        "utf8",
    );
    assert.equal(extSnippetsRaw, sharedSnippetsRaw);

    const snippets = JSON.parse(extSnippetsRaw);
    const byPrefix = new Map(
        Object.values(snippets).map((entry) => [entry.prefix, entry.body.join("\n")]),
    );

    for (const prefix of [
        "tvl-rate-bound",
        "tvl-zero-tolerance-guard",
        "tvl-recovery",
        "tvl-promotion-monitor",
        "tvl-responses-ladder",
        "tvl-pack-floor",
    ]) {
        assert.ok(byPrefix.has(prefix), `missing snippet ${prefix}`);
    }

    assert.match(byPrefix.get("tvl-rate-bound"), /kind: rate_bound/);
    assert.match(byPrefix.get("tvl-rate-bound"), /kind: evidence_liveness/);
    assert.match(byPrefix.get("tvl-zero-tolerance-guard"), /kind: zero_tolerance/);
    assert.match(byPrefix.get("tvl-zero-tolerance-guard"), /block_action/);
    assert.match(byPrefix.get("tvl-recovery"), /kind: recovery_time/);
    assert.match(byPrefix.get("tvl-recovery"), /source: episodes/);
    assert.match(byPrefix.get("tvl-promotion-monitor"), /phase: promotion/);
    assert.match(byPrefix.get("tvl-promotion-monitor"), /source: evaluation_set/);
    assert.match(byPrefix.get("tvl-responses-ladder"), /do: rollback/);
    assert.match(byPrefix.get("tvl-responses-ladder"), /do: suspend/);
    assert.match(byPrefix.get("tvl-pack-floor"), /applies_to: tenant_floor/);
});

function loadExtensionWithMockVscode(mockState) {
    const originalLoad = Module._load;
    const diagnosticStore = new Map();
    let registeredContributor = null;

    const vscodeMock = {
        DiagnosticSeverity: {
            Error: 0,
            Warning: 1,
            Information: 2,
            Hint: 3,
        },
        Position: class Position {
            constructor(line, character) {
                this.line = line;
                this.character = character;
            }
        },
        Range: class Range {
            constructor(startLine, startCharacter, endLine, endCharacter) {
                this.start = { line: startLine, character: startCharacter };
                this.end = { line: endLine, character: endCharacter };
            }
        },
        Diagnostic: class Diagnostic {
            constructor(range, message, severity) {
                this.range = range;
                this.message = message;
                this.severity = severity;
            }
        },
        Uri: {
            file: (fsPath) => ({ fsPath, toString: () => `file://${fsPath}` }),
            parse: (raw) => ({
                fsPath: raw.replace(/^file:\/\//, ""),
                toString: () => raw,
            }),
        },
        languages: {
            createDiagnosticCollection: () => ({
                set: (uri, diagnostics) => {
                    diagnosticStore.set(uri.fsPath || uri.toString(), diagnostics);
                },
                delete: (uri) => {
                    diagnosticStore.delete(uri.fsPath || uri.toString());
                },
                dispose: () => {
                    diagnosticStore.clear();
                },
            }),
        },
        commands: {
            registerCommand: (_name, cb) => ({ dispose: () => {}, cb }),
        },
        workspace: {
            textDocuments: mockState.textDocuments || [],
            getConfiguration: () => ({
                get: (key, defaultValue) =>
                    key in (mockState.config || {}) ? mockState.config[key] : defaultValue,
            }),
            onDidSaveTextDocument: () => ({ dispose: () => {} }),
            onDidCloseTextDocument: () => ({ dispose: () => {} }),
        },
        window: {
            activeTextEditor: undefined,
            showInformationMessage: (msg) => {
                mockState.infoMessages.push(msg);
            },
            showWarningMessage: (msg) => {
                mockState.warningMessages.push(msg);
            },
            showErrorMessage: (msg) => {
                mockState.errorMessages.push(msg);
            },
        },
        extensions: {
            getExtension: (id) => {
                if (id !== "redhat.vscode-yaml") {
                    return undefined;
                }
                return {
                    isActive: true,
                    exports: {
                        registerContributor: (scheme, requestSchema, requestSchemaContent) => {
                            registeredContributor = {
                                scheme,
                                requestSchema,
                                requestSchemaContent,
                            };
                        },
                    },
                };
            },
        },
    };

    Module._load = function (request, parent, isMain) {
        if (request === "vscode") {
            return vscodeMock;
        }
        return originalLoad.call(this, request, parent, isMain);
    };

    try {
        const extModulePath = require.resolve("../out/extension.js");
        delete require.cache[extModulePath];
        const ext = require("../out/extension.js");
        return {
            ext,
            vscodeMock,
            diagnosticStore,
            getContributor: () => registeredContributor,
            restore: () => {
                Module._load = originalLoad;
            },
        };
    } catch (err) {
        Module._load = originalLoad;
        throw err;
    }
}

test("associates bundled module and pack schemas via manifest and YAML contributor", async () => {
    const yamlValidation = manifest.contributes.yamlValidation;
    assert.ok(Array.isArray(yamlValidation));
    const packEntry = yamlValidation.find((e) => e.url === "./schemas/tvl-pack.schema.json");
    const moduleEntry = yamlValidation.find((e) => e.url === "./schemas/tvl.schema.json");
    assert.ok(packEntry, "missing tvl-pack.schema.json in yamlValidation");
    assert.ok(moduleEntry, "missing tvl.schema.json in yamlValidation");
    assert.ok(packEntry.fileMatch.includes("*.pack.tvl.yml"));
    assert.ok(moduleEntry.fileMatch.includes("*.tvl.yml"));

    for (const schemaName of ["tvl.schema.json", "tvl-pack.schema.json"]) {
        const bundled = fs.readFileSync(path.join(vscodeTvlRoot, "schemas", schemaName), "utf8");
        const shared = fs.readFileSync(
            path.join(repoRoot, "editor_shared", "vscode", "schemas", schemaName),
            "utf8",
        );
        const canonical = fs.readFileSync(
            path.join(repoRoot, "spec", "grammar", schemaName),
            "utf8",
        );
        assert.equal(bundled, canonical, `${schemaName} in vscode-tvl must match spec/grammar`);
        assert.equal(shared, canonical, `${schemaName} in editor_shared must match spec/grammar`);
    }

    const packDocText = 'tvl_version: "1.3"\npack:\n  module: acme.floors\nrequirements: []\nmonitors: []\n';
    const moduleDocText = 'tvl:\n  module: acme.bot\ntvl_version: "1.3"\n';
    const mockState = {
        config: {},
        infoMessages: [],
        warningMessages: [],
        errorMessages: [],
        textDocuments: [
            {
                uri: { toString: () => "file:///workspace/floors.tvl.yml" },
                fileName: "/workspace/floors.tvl.yml",
                getText: () => packDocText,
            },
            {
                uri: { toString: () => "file:///workspace/agent.tvl.yml" },
                fileName: "/workspace/agent.tvl.yml",
                getText: () => moduleDocText,
            },
        ],
    };

    const { ext, getContributor, restore } = loadExtensionWithMockVscode(mockState);
    try {
        ext.activate({ subscriptions: [], extensionPath: vscodeTvlRoot });
        assert.equal(ext.isTvlPackDocument(packDocText, "/workspace/floors.tvl.yml"), true);
        assert.equal(ext.isTvlPackDocument(moduleDocText, "/workspace/agent.packing.pack.tvl.yml"), true);
        assert.equal(ext.isTvlPackDocument(moduleDocText, "/workspace/agent.tvl.yml"), false);

        const contributor = getContributor();
        assert.ok(contributor, "expected YAML schema contributor to be registered");
        assert.equal(
            contributor.requestSchema("file:///workspace/floors.tvl.yml"),
            "tvl-schema://schemas/tvl-pack.schema.json",
        );
        assert.equal(
            contributor.requestSchema("file:///workspace/org.pack.tvl.yml"),
            "tvl-schema://schemas/tvl-pack.schema.json",
        );
        assert.equal(
            contributor.requestSchema("file:///workspace/agent.tvl.yml"),
            "tvl-schema://schemas/tvl.schema.json",
        );

        const packSchemaContent = JSON.parse(
            contributor.requestSchemaContent("tvl-schema://schemas/tvl-pack.schema.json"),
        );
        assert.equal(packSchemaContent.title, "TVL Pack");
    } finally {
        restore();
    }
});

test("preserves result.issues and field paths when tvl-validate or tvl-lint exits 2", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vscode-tvl-test-"));
    const fakeCliPath = path.join(tmpDir, "fake-tvl-validate");
    const fakeLintCliPath = path.join(tmpDir, "fake-tvl-lint");
    const fakeDocPath = path.join(tmpDir, "broken.tvl.yml");

    const docYaml = [
        "tvl:",
        "  module: examples.broken",
        'tvl_version: "1.3"',
        "requirements:",
        "  - name: bad_req",
        "    kind: rate_bound",
        "    unit: trace",
        "    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }",
        "    max_rate: 1.5",
    ].join("\n");
    fs.writeFileSync(fakeDocPath, docYaml, "utf8");

    const cliPayload = {
        ok: false,
        file: fakeDocPath,
        schema_ok: false,
        issues: [
            {
                code: "runtime_rate_out_of_range",
                path: ["requirements", 0, "max_rate"],
                message: "requirements.0.max_rate: max_rate must be in (0, 1)",
                severity: "error",
            },
            {
                code: "schema_error",
                path: ["tvars"],
                message: "required field is missing",
                severity: "error",
            },
            {
                code: "runtime_liveness_missing",
                path: ["monitors", 0, "name"],
                message: "Primary runtime monitor is not covered by an evidence_liveness requirement",
                severity: "warning",
            },
        ],
    };

    const cliScript = `#!/usr/bin/env node\nprocess.stdout.write(${JSON.stringify(JSON.stringify(cliPayload))});\nprocess.exit(2);\n`;
    fs.writeFileSync(fakeCliPath, cliScript, { mode: 0o755 });
    fs.writeFileSync(fakeLintCliPath, cliScript, { mode: 0o755 });

    const mockState = {
        config: { "cli.path": fakeCliPath },
        infoMessages: [],
        warningMessages: [],
        errorMessages: [],
    };

    const { ext, vscodeMock, diagnosticStore, restore } = loadExtensionWithMockVscode(mockState);
    try {
        ext.activate({ subscriptions: [], extensionPath: vscodeTvlRoot });
        const doc = {
            uri: vscodeMock.Uri.file(fakeDocPath),
            fileName: fakeDocPath,
            getText: () => docYaml,
        };

        await ext.validateDocument(doc);

        assert.equal(mockState.errorMessages.length, 0);
        const diagnostics = diagnosticStore.get(fakeDocPath);
        assert.ok(Array.isArray(diagnostics), "expected diagnostics to be recorded");
        assert.equal(diagnostics.length, 3, "must not drop result.issues when tvl-validate exits 2");

        assert.equal(diagnostics[0].code, "runtime_rate_out_of_range");
        assert.equal(
            diagnostics[0].message,
            "requirements.0.max_rate: max_rate must be in (0, 1)",
        );
        assert.equal(diagnostics[0].range.start.line, 8);
        assert.equal(diagnostics[0].severity, vscodeMock.DiagnosticSeverity.Error);

        assert.equal(diagnostics[1].code, "schema_error");
        assert.equal(diagnostics[1].message, "tvars: required field is missing");

        assert.equal(diagnostics[2].code, "runtime_liveness_missing");
        assert.equal(
            diagnostics[2].message,
            "monitors.0.name: Primary runtime monitor is not covered by an evidence_liveness requirement",
        );
        assert.equal(diagnostics[2].severity, vscodeMock.DiagnosticSeverity.Warning);

        await ext.lintDocument(doc);
        const lintDiagnostics = diagnosticStore.get(fakeDocPath);
        assert.equal(lintDiagnostics.length, 3, "must not drop result.issues when tvl-lint exits 2");
        assert.equal(mockState.warningMessages.length, 1);
    } finally {
        restore();
        fs.rmSync(tmpDir, { recursive: true, force: true });
    }
});

function expandSnippetDefaults(bodyLines) {
    return bodyLines
        .join("\n")
        .replace(/\$\{\d+\|([^,}]+)[^}]*\}/g, "$1")
        .replace(/\$\{\d+:([^}]+)\}/g, "$1");
}

test("all 6 expanded snippets validate cleanly with tvl-validate and tvl-lint", async (t) => {
    const tvlValidateBin = path.join(repoRoot, ".venv", "bin", "tvl-validate");
    if (!fs.existsSync(tvlValidateBin)) {
        t.skip("tvl-validate not installed in .venv");
        return;
    }

    const snippets = JSON.parse(
        fs.readFileSync(path.join(vscodeTvlRoot, "snippets", "tvl.code-snippets"), "utf8"),
    );
    const byPrefix = new Map(
        Object.values(snippets).map((entry) => [entry.prefix, expandSnippetDefaults(entry.body)]),
    );

    const moduleHeader = [
        "tvl:",
        "  module: examples.snippets.test",
        'tvl_version: "1.3"',
        "environment:",
        '  snapshot_id: "2026-10-16T00:00:00Z"',
        "evaluation_set:",
        "  dataset: snippet_eval",
        "tvars:",
        "  - name: model",
        "    type: enum[str]",
        "    domain: [m_small, m_large]",
        "objectives:",
        "  - name: quality",
        "    direction: maximize",
        "promotion_policy:",
        "  dominance: epsilon_pareto",
        "  alpha: 0.05",
        "  min_effect:",
        "    quality: 0.02",
    ].join("\n");

    const rateBoundBody = byPrefix.get("tvl-rate-bound");
    const zeroToleranceBody = byPrefix.get("tvl-zero-tolerance-guard");
    const recoveryBody = byPrefix.get("tvl-recovery");
    const promotionMonitorBody = byPrefix.get("tvl-promotion-monitor");
    const ladderBody = byPrefix.get("tvl-responses-ladder");
    const packFloorBody = byPrefix.get("tvl-pack-floor");

    const [recReqPart, recMonPart] = recoveryBody.split("# Add under monitors:\n");
    const [rateReqPart, rateMonPart] = rateBoundBody.split("\nmonitors:\n");

    const documents = [
        { name: "rate-bound.tvl.yml", content: `${moduleHeader}\n\n${rateBoundBody}\n` },
        { name: "zero-tolerance.tvl.yml", content: `${moduleHeader}\n\n${zeroToleranceBody}\n` },
        {
            name: "recovery-and-ladder.tvl.yml",
            content: `${moduleHeader}\n\n${rateReqPart}\n${recReqPart}\nmonitors:\n${rateMonPart}\n${recMonPart}\n${promotionMonitorBody}\n\n${ladderBody}\n`,
        },
        { name: "floor.pack.tvl.yml", content: `${packFloorBody}\n` },
    ];

    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vscode-tvl-snippets-"));
    const mockState = {
        config: { "cli.path": tvlValidateBin },
        infoMessages: [],
        warningMessages: [],
        errorMessages: [],
    };

    const { ext, vscodeMock, diagnosticStore, restore } = loadExtensionWithMockVscode(mockState);
    try {
        ext.activate({ subscriptions: [], extensionPath: vscodeTvlRoot });
        for (const docSpec of documents) {
            const filePath = path.join(tmpDir, docSpec.name);
            fs.writeFileSync(filePath, docSpec.content, "utf8");
            const doc = {
                uri: vscodeMock.Uri.file(filePath),
                fileName: filePath,
                getText: () => docSpec.content,
            };
            await ext.validateDocument(doc);
            assert.deepEqual(
                diagnosticStore.get(filePath),
                [],
                `expected 0 validation diagnostics for ${docSpec.name}`,
            );
            await ext.lintDocument(doc);
            assert.deepEqual(
                diagnosticStore.get(filePath),
                [],
                `expected 0 lint diagnostics for ${docSpec.name}`,
            );
        }
    } finally {
        restore();
        fs.rmSync(tmpDir, { recursive: true, force: true });
    }
});

test("resolveIssueLine locates list items and stays linear on long whitespace runs", () => {
    const mockState = {
        config: {},
        infoMessages: [],
        warningMessages: [],
        errorMessages: [],
        textDocuments: [],
    };
    const { ext, restore } = loadExtensionWithMockVscode(mockState);
    try {
        const text = "tvars:\n  - name: a\n  - name: b\n";
        assert.equal(ext.resolveIssueLine({ path: ["tvars", 1] }, text), 2);
        assert.equal(ext.resolveIssueLine({ path: ["tvars", 0] }, text), 1);

        // A '-' preceded by a huge run of spaces (and a long line of spaces with no '-')
        // must resolve promptly rather than backtrack.
        const padded = "tvars:\n" + " ".repeat(200000) + "- name: a\n" + " ".repeat(200000) + "x\n";
        const started = Date.now();
        assert.equal(ext.resolveIssueLine({ path: ["tvars", 0] }, padded), 1);
        assert.ok(Date.now() - started < 2000, "list-item scan must not backtrack");
    } finally {
        restore();
    }
});
