// parts.test.js — TICKET-VSC-2 面板组件 HTML 构建（think 折叠渲染等）
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { escapeHtml, buildThinkBlock, buildToolRow, buildDiffCard, buildLedgerItem, buildSessionItem } = require('../media/parts.js');

test('think 折叠渲染：默认收起（无 open class）+ 含摘要标签', () => {
  const html = buildThinkBlock('第一步思考\n第二步思考');
  assert.ok(html.includes('class="think-box"'), 'think-box 根元素');
  assert.ok(!html.includes('think-box open'), '默认收起（无 open class）');
  assert.ok(html.includes('思考过程'), '折叠标签');
  assert.ok(html.includes('第一步思考\n第二步思考'), '思考内容保留');
});

test('think 折叠渲染：外来内容被 escape（防 XSS）', () => {
  const html = buildThinkBlock('<script>alert(1)</script>"quoted"');
  assert.ok(!html.includes('<script>'), 'script 标签不得直插');
  assert.ok(html.includes('&lt;script&gt;'), '已被转义');
  assert.ok(html.includes('&quot;quoted&quot;'), '引号被转义');
});

test('工具行：start 状态为 run 点 + 显示工具名', () => {
  const html = buildToolRow({ type: 'tool.start', name: 'edit_file', arguments: { file_path: 'src/a.ts' } });
  assert.ok(html.includes('data-name="edit_file"'), '工具名');
  assert.ok(html.includes('tool-dot run'), '运行中点');
  assert.ok(html.includes('src/a.ts'), '参数摘要');
  assert.ok(html.includes('data-done="0"'), '未完成标记');
});

test('工具行：complete 成功为 done 点 + 展开体（inline_diff 优先）', () => {
  const html = buildToolRow({ type: 'tool.complete', name: 'edit_file', inline_diff: '@@ -1 +1 @@', result_text: 'ok' });
  assert.ok(html.includes('tool-dot done'), '完成绿点');
  assert.ok(html.includes('data-done="1"'), '完成标记');
  assert.ok(html.includes('tool-body'), '有展开体');
  assert.ok(html.includes('@@ -1 +1 @@'), 'inline_diff 进展开体');
});

test('工具行：complete 失败为 fail 点 + error 摘要', () => {
  const html = buildToolRow({ type: 'tool.complete', name: 'file_operation', error: 'boom' });
  assert.ok(html.includes('tool-dot fail'), '失败红点');
  assert.ok(html.includes('boom'), 'error 摘要');
});

test('diff 卡：含文件路径 + Accept/Reject 按钮 + data-file', () => {
  const html = buildDiffCard('/abs/path/x.txt', 'edit_file · x.txt');
  assert.ok(html.includes('data-file="/abs/path/x.txt"'), 'data-file 携带路径');
  assert.ok(html.includes('>Accept</button>'), 'Accept 按钮');
  assert.ok(html.includes('>Reject</button>'), 'Reject 按钮');
  assert.ok(html.includes('edit_file · x.txt'), '标题');
});

test('diff 卡：路径 escape（防属性注入）', () => {
  const html = buildDiffCard('/a" onmouseover="x', 't');
  assert.ok(!html.includes('/a" onmouseover='), '引号被转义');
  assert.ok(html.includes('&quot;'), '转义存在');
});

test('台账条目：状态点 class + 标题', () => {
  const html = buildLedgerItem({ id: 'x1', title: '读票', status: 'in_progress' });
  assert.ok(html.includes('lg-dot in_progress'), '状态点');
  assert.ok(html.includes('读票'), '标题');
  const done = buildLedgerItem({ id: 'x2', title: '完成', status: 'done' });
  assert.ok(done.includes('lg-dot done'), 'done 状态');
  const pend = buildLedgerItem({ id: 'x3' });
  assert.ok(pend.includes('lg-dot pending'), '缺省 pending');
});

test('会话条目：active 标记 + id + 消息数', () => {
  const html = buildSessionItem({ id: 's1', title: '会话一', message_count: 5 }, true);
  assert.ok(html.includes('sess-item active'), '激活标记');
  assert.ok(html.includes('data-id="s1"'), 'id');
  assert.ok(html.includes('会话一'), '标题');
  assert.ok(html.includes('5 msgs'), '消息数');
});

test('escapeHtml 全字符集', () => {
  assert.strictEqual(escapeHtml('<>&"\''), '&lt;&gt;&amp;&quot;&#39;');
  assert.strictEqual(escapeHtml(null), '');
  assert.strictEqual(escapeHtml(undefined), '');
});
