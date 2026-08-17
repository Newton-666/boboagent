// contextPack.test.js — selection context bundle (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const {
  buildContextBlock, buildUserMessage, extractDiagnostics, DEFAULT_QUESTION,
} = require('../out/contextPack.js');

const baseCtx = {
  filePath: 'src/util.ts',
  languageId: 'typescript',
  selectedText: 'const x = 1;',
  startLine: 12,
  endLine: 12,
  diagnostics: [{ severity: 'error', message: 'x is declared but never used', line: 12 }],
  workspaceRoot: '/ws',
};

test('buildContextBlock contains file/lines/lang/snippet/diagnostics', () => {
  const b = buildContextBlock(baseCtx);
  assert.ok(b.includes('File: src/util.ts (typescript)'));
  assert.ok(b.includes('Lines: 12-12'));
  assert.ok(b.includes('Project root: /ws'));
  assert.ok(b.includes('```typescript'));
  assert.ok(b.includes('const x = 1;'));
  assert.ok(b.includes('[error] line 12: x is declared but never used'));
});

test('buildUserMessage appends the default question', () => {
  const m = buildUserMessage(baseCtx);
  assert.ok(m.includes(DEFAULT_QUESTION));
  assert.ok(m.indexOf(DEFAULT_QUESTION) > m.indexOf('```')); // question after snippet
});

test('buildUserMessage uses a custom question', () => {
  const m = buildUserMessage(baseCtx, '为什么用 const 而不是 let？');
  assert.ok(m.includes('为什么用 const 而不是 let？'));
});

test('extractDiagnostics keeps only error/warning, 1-based lines', () => {
  const out = extractDiagnostics([
    { severity: 0, message: 'e1', range: { start: { line: 0 } } },
    { severity: 1, message: 'w1', range: { start: { line: 5 } } },
    { severity: 2, message: 'info-skip', range: { start: { line: 9 } } },
    { severity: 3, message: 'hint-skip', range: { start: { line: 9 } } },
  ]);
  assert.strictEqual(out.length, 2);
  assert.deepStrictEqual(out[0], { severity: 'error', message: 'e1', line: 1 });
  assert.deepStrictEqual(out[1], { severity: 'warning', message: 'w1', line: 6 });
});

test('empty selection context still yields a valid block', () => {
  const b = buildContextBlock({ filePath: 'a.py', languageId: 'python', selectedText: '', startLine: 1, endLine: 1, diagnostics: [] });
  assert.ok(b.includes('File: a.py (python)'));
  assert.ok(b.includes('```python'));
  assert.ok(!b.includes('Diagnostics:'));
});
