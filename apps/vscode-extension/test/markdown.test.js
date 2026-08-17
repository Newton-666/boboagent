// markdown.test.js — safe renderer + thinking strip (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { escapeHtml, splitThinking, renderMarkdown, highlightCode } = require('../out/markdown.js');

test('escapeHtml neutralises script injection', () => {
  const out = escapeHtml('<script>alert(1)</script>');
  assert.ok(!out.includes('<script>'));
  assert.ok(out.includes('&lt;script&gt;'));
});

test('splitThinking strips the thinking block like index.html F1-2', () => {
  const s = '正文第一句\n── 💭 思考过程 ──\n我先分析一下\n── 思考结束 ──';
  const r = splitThinking(s);
  assert.strictEqual(r.body, '正文第一句');
  assert.strictEqual(r.thinking, '我先分析一下');
});

test('splitThinking passthrough when no thinking block', () => {
  const r = splitThinking('普通回答');
  assert.strictEqual(r.body, '普通回答');
  assert.strictEqual(r.thinking, '');
});

test('renderMarkdown emits fenced code with highlighting', () => {
  const html = renderMarkdown('```python\ndef f():\n    return 1\n```');
  assert.ok(html.includes('<pre><code>'));
  assert.ok(html.includes('tok-kw')); // def highlighted
  assert.ok(!html.includes('```'));
});

test('renderMarkdown never leaks raw HTML from input', () => {
  const html = renderMarkdown('<img src=x onerror=alert(1)>');
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
});

test('renderMarkdown handles headings, lists, bold, inline code', () => {
  const html = renderMarkdown('# Title\n\n- item **bold**\n\n`code` here');
  assert.ok(html.includes('<h1>Title</h1>'));
  assert.ok(html.includes('<li>item <strong>bold</strong></li>'));
  assert.ok(html.includes('<code>code</code>'));
});

test('renderMarkdown only allows http(s) links', () => {
  const html = renderMarkdown('[x](javascript:alert(1))');
  assert.ok(!html.includes('<a'), 'javascript: link must not become a link');
  const safe = renderMarkdown('[bobo](https://example.com)');
  assert.ok(safe.includes('https://example.com'));
});
