const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const extensionSource = fs.readFileSync(
    path.join(__dirname, "..", "src", "extension.ts"),
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
