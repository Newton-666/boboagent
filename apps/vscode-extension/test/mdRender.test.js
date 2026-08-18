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

// ── 票 VSC-2D：裸 HTML 文本化（对齐桌面端 esc 行为，验收标准 2 五项）──
test('VSC-2D 裸 HTML 文本化：div 标签转义为文本，无真实 DOM 元素', () => {
  const out = mdRender('HTML = """<div class="card"></div>"""');
  assert.ok(out.includes('&lt;div class="card"&gt;'), '开始标签文本化');
  assert.ok(out.includes('&lt;/div&gt;'), '结束标签文本化');
  assert.ok(!out.includes('<div class="card">'), '不得存在真实 div 元素');
  assert.ok(!/<div\b/.test(out), '输出不得含任何真实 div 标签');
  assert.ok(out.includes('&quot;&quot;&quot;'), '三引号保持（&quot; 未双转义）');
});

test('VSC-2D style 属性不生效：整段以文本输出，无元素化', () => {
  const out = mdRender('<div class="card-label" style="color:#999">Epoch</div>');
  assert.ok(out.includes('&lt;div'), '标签文本化');
  assert.ok(!out.includes('<div'), '无真实 div 元素');
  assert.ok(out.includes('color:#999'), '样式内容仅作文本保留（不生效）');
  assert.ok(!/<[a-z]+[^>]*style=/.test(out), '不得有带 style 属性的真实元素');
  assert.ok(out.includes('Epoch'), '内容不丢');
});

test('VSC-2D 代码块内 HTML 不受影响（走 hljs 高亮）', () => {
  const out = mdRender('```html\n<div class="card">ok</div>\n```');
  assert.ok(out.includes('<pre><code class="language-html">'), '代码块正常渲染');
  assert.ok(out.includes('<span class="hljs-tag">'), 'hljs 高亮 span 保留');
  assert.ok(out.includes('&lt;'), '代码内标签以转义文本显示（hljs 已转义）');
});

test('VSC-2D 正常 markdown 不回归', () => {
  const out = mdRender('这是**加粗**和`行内代码`，以及 [链接](https://x.com)');
  assert.ok(out.includes('<strong>加粗</strong>'), '加粗正常');
  assert.ok(out.includes('<code>行内代码</code>'), '行内代码正常');
  assert.ok(out.includes('<a href="https://x.com">链接</a>'), '链接正常');
});

test('VSC-2D 三引号 Python 字符串整体可读（owner 实弹场景）', () => {
  const out = mdRender('HTML = """...<div class="card">Epoch</div>..."""');
  assert.ok(out.includes('HTML = &quot;&quot;&quot;'), '前缀与三引号保留');
  assert.ok(out.includes('&lt;div class="card"&gt;Epoch&lt;/div&gt;'), 'HTML 片段以文本整体可读');
  assert.ok(!/<div\b/.test(out), '无真实元素');
});
