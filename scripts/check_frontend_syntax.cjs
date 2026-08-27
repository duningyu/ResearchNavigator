#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const ts = require('typescript');

const root = path.resolve(process.argv[2] || 'apps/web');
const extensions = new Set(['.ts', '.tsx']);
const files = [];

function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue;
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(candidate);
    else if (!entry.name.endsWith('.d.ts') && extensions.has(path.extname(entry.name))) files.push(candidate);
  }
}

walk(root);
const failures = [];
for (const file of files.sort()) {
  const source = fs.readFileSync(file, 'utf8');
  const result = ts.transpileModule(source, {
    fileName: file,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      jsx: ts.JsxEmit.ReactJSX,
      strict: true,
    },
  });
  for (const diagnostic of result.diagnostics || []) {
    if (diagnostic.category !== ts.DiagnosticCategory.Error) continue;
    const position = diagnostic.file && diagnostic.start !== undefined
      ? diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start)
      : null;
    failures.push({
      file: path.relative(process.cwd(), file),
      line: position ? position.line + 1 : null,
      column: position ? position.character + 1 : null,
      message: ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'),
    });
  }
}

if (failures.length) {
  console.error(JSON.stringify({ status: 'FAIL', fileCount: files.length, failures }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({
  status: 'PASS',
  fileCount: files.length,
  typescriptVersion: ts.version,
  scope: 'syntax transpile only; not dependency-aware typecheck or production build',
}, null, 2));
