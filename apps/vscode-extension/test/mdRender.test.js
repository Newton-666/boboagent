// mdRender.test.js — TICKET-VSC-1C markdown 渲染管线快照断言
// 管线：marked.parse（gfm + hljs 高亮）→ DOMPurify.sanitize（Node 测试路径为轻量净化兜底）
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { mdRender } = require('../media/md-render.js');

test('代码块渲染为 pre>code + hljs 高亮 span', () => {
  const out = mdRender('```python\nprint("hi")\n```');
  assert.ok(out.includes('<pre><code class="language-python">'), '应含语言类 pre>code');
  assert.ok(out.includes('<span class="hljs-'), '代码应被 highlight.js 着色');
  assert.ok(!out.includes('```'), '围栏不应残留');
});

test('表格渲染为 table/th/td 结构', () => {
  const out = mdRender('| a | b |\n|---|---|\n| 1 | 2 |');
  assert.ok(out.includes('<table>'), '应含 <table>');
  assert.ok(out.includes('<th>a</th>'), '表头 a');
  assert.ok(out.includes('<th>b</th>'), '表头 b');
  assert.ok(out.includes('<td>1</td>'), '单元格 1');
  assert.ok(out.includes('<td>2</td>'), '单元格 2');
});

test('加粗与行内代码', () => {
  const out = mdRender('这是**加粗**和`行内代码`');
  assert.ok(out.includes('<strong>加粗</strong>'), '应渲染 <strong>');
  assert.ok(out.includes('<code>行内代码</code>'), '应渲染行内 <code>');
});

test('半截代码块容错渲染（流式不 throw）', () => {
  const out = mdRender('开始\n```python\nprint(1)');
  assert.ok(out.includes('<pre><code'), '半截围栏也应容错渲染为 pre>code');
  assert.ok(out.includes('print'), '代码内容不丢（hljs 高亮后带 span）');
  assert.ok(out.includes('1'), '代码内容不丢');
});

test('XSS 剥离：script/iframe/事件属性被清除', () => {
  const out = mdRender('正常文本\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>');
  assert.ok(!out.includes('<script'), 'script 标签必须剥离');
  assert.ok(!out.includes('onerror'), '事件属性必须剥离');
  assert.ok(out.includes('正常文本'), '正文不丢');
});

test('空输入不 throw，返回空字符串', () => {
  assert.strictEqual(mdRender(null), '');
  assert.strictEqual(mdRender(''), '');
});
