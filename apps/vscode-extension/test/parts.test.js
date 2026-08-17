// parts.test.js — TICKET-VSC-2 面板组件 HTML 构建（think 折叠渲染等）
// 票 VSC-2B：工具聚合卡 / 审批卡 / 串行闸门 / 停止钮切换单测（验收标准 1）。
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const {
  escapeHtml, buildThinkBlock, buildToolAggCard, buildToolItem, buildApprovalCard,
  buildDiffBlock, toolSummary, buildLedgerItem, buildSessionItem,
  APPROVAL_CHOICES, createApprovalGate, runningView,
} = require('../media/parts.js');

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

// ── 票 VSC-2B：工具聚合卡 ──
test('聚合卡：默认折叠（body display:none）+ "N 个工具调用"标题占位', () => {
  const html = buildToolAggCard();
  assert.ok(html.includes('class="tool-agg"'), '聚合卡根元素');
  assert.ok(html.includes('tool-agg-body" style="display:none"'), '默认折叠');
  assert.ok(html.includes('个工具调用'), '标题文案');
});

test('工具卡：start 状态为 run 点 + 图标 + 摘要（桌面端 addTool 结构）', () => {
  const html = buildToolItem({ type: 'tool.start', name: 'edit_file', arguments: { file_path: 'src/a.ts' } });
  assert.ok(html.includes('data-name="edit_file"'), '工具名');
  assert.ok(html.includes('tool-dot run'), '运行中点');
  assert.ok(html.includes('src/a.ts'), '参数摘要');
  assert.ok(html.includes('tool-result'), '结果容器（点击展开）');
});

test('工具卡：complete 成功为 done 点 + toolSummary（路径 +N/-M）', () => {
  const html = buildToolItem({ type: 'tool.complete', name: 'edit_file', inline_diff: '@@ -1 +1 @@\n-old\n+new', result_text: 'ok', arguments: { file_path: 'src/a.ts' } });
  assert.ok(html.includes('tool-dot done'), '完成绿点');
  assert.ok(html.includes('+1/-1'), 'diff 统计进摘要');
  assert.ok(html.includes('tool-body'), '有展开体');
});

test('工具卡：complete 失败为 fail 点 + error 摘要', () => {
  const html = buildToolItem({ type: 'tool.complete', name: 'file_operation', error: 'boom' });
  assert.ok(html.includes('tool-dot fail'), '失败红点');
  assert.ok(html.includes('boom'), 'error 摘要');
});

test('toolSummary：无 diff 时只给路径；无路径给空串', () => {
  assert.strictEqual(toolSummary({ file_path: 'x.ts' }, ''), 'x.ts');
  assert.strictEqual(toolSummary({ path: 'y.ts' }, '@@ -1 +1 @@\n-a\n+b'), 'y.ts +1/-1');
  assert.strictEqual(toolSummary({}, ''), '');
});

test('diff 只读块：@@ 头 / +绿 / -红 / 上下文灰分类（桌面端 diffBlock 对齐）', () => {
  const html = buildDiffBlock('@@ -1,2 +1,2 @@\n-old line\n+new line\nctx');
  assert.ok(html.includes('class="df"'), '@@ 文件头');
  assert.ok(html.includes('class="dl add"'), '+ 行绿');
  assert.ok(html.includes('class="dl del"'), '- 行红');
  assert.ok(html.includes('class="dl ctx"'), '上下文灰');
});

// ── 票 VSC-2B：审批卡（执行前无 diff；Accept/Reject 按钮）──
test('审批卡：tool_name + arguments 摘要 + Accept/Reject（无 diff 区）', () => {
  const html = buildApprovalCard({ tool_name: 'edit_file', arguments: { file_path: 'a.txt', content: 'x' } });
  assert.ok(html.includes('edit_file'), '工具名');
  assert.ok(html.includes('file_path: a.txt'), '参数摘要');
  assert.ok(html.includes('>Accept</button>'), 'Accept 按钮');
  assert.ok(html.includes('>Reject</button>'), 'Reject 按钮');
  assert.ok(!html.includes('diff-block'), '执行前无 diff 展示');
});

test('审批卡：参数内容 escape（防 XSS）', () => {
  const html = buildApprovalCard({ tool_name: 'file_operation', arguments: { file_path: '/a" onmouseover="x' } });
  assert.ok(!html.includes('/a" onmouseover='), '引号被转义');
  assert.ok(html.includes('&quot;'), '转义存在');
});

test('审批 choice 映射：Accept→allow / Reject→deny（验收标准 1）', () => {
  assert.strictEqual(APPROVAL_CHOICES.accept, 'allow');
  assert.strictEqual(APPROVAL_CHOICES.reject, 'deny');
});

// ── 票 VSC-2B：审批卡串行闸门状态机（验收标准 1）──
test('串行闸门：同刻只一张卡——第二个 open 自动关旧卡（防双弹）', () => {
  const gate = createApprovalGate();
  let closedIds = [];
  const id1 = gate.open((id) => closedIds.push(id));
  assert.strictEqual(gate.hasOpen, true, '第一张卡在');
  assert.strictEqual(gate.current.id, id1);
  const id2 = gate.open((id) => closedIds.push(id));
  assert.strictEqual(gate.hasOpen, true);
  assert.strictEqual(gate.current.id, id2, '当前是第二张');
  assert.deepStrictEqual(closedIds, [id1], '旧卡已被关（只关一次）');
  assert.strictEqual(closedIds.length, 1, '不得重复触发 onClose');
});

test('串行闸门：close 清空 + onClose 触发一次；timeout 置灰标记', () => {
  const gate = createApprovalGate();
  let closed = 0;
  gate.open(() => closed++);
  gate.close();
  assert.strictEqual(gate.hasOpen, false, '已清空');
  assert.strictEqual(closed, 1);
  assert.strictEqual(gate.timeout(), null, '无卡时 timeout 返回 null');
  gate.open(() => {});
  const tid = gate.timeout();
  assert.ok(tid !== null, '有卡时 timeout 返回 id');
  assert.strictEqual(gate.current.timedOut, true, '置灰标记');
});

// ── 票 VSC-2B：停止按钮 Send⇄Stop 切换（验收标准 1）──
test('停止钮切换：running=true 隐藏 Send 显示 Stop；false 反之', () => {
  const busy = runningView(true);
  assert.strictEqual(busy.send, 'none', 'Send 隐藏');
  assert.strictEqual(busy.stop, 'show', 'Stop 显示');
  const idle = runningView(false);
  assert.strictEqual(idle.send, '', 'Send 恢复');
  assert.strictEqual(idle.stop, '', 'Stop 隐藏');
});

// ── VSC-2D 既有：台账/会话 ──
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
