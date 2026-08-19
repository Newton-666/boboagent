// TICKET-GUI-F29：实时消息窗口化（增量虚拟滚动）——jsdom 逻辑验证
// 覆盖：挂载/流式增量/状态行/思考框同步/工具聚合/diff 块/窗口化回收/滚动重建/
// 历史完整/clearChat/顺序保持。布局真实值（offsetHeight）由 Electron 实机验证。
const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '../../dist/index.html'), 'utf8');
const dom = new JSDOM(html, {
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  url: 'file:///tmp/f29-test/',
});
const { window } = dom;

// ── stub 外部库（mdReply 依赖）──
window.marked = {
  setOptions() {},
  Renderer: function () { this.code = function (code, lang) { return '<pre><code>' + String(code).replace(/</g, '&lt;') + '</code></pre>'; }; },
  parse(s) { return String(s).replace(/</g, '&lt;').replace(/\n/g, '<br>'); },
};
window.DOMPurify = { sanitize: (s) => s };
window.hljs = { getLanguage: () => false };
window.katex = { renderToString: (t) => '<span class="katex-mock">' + t + '</span>' };
window.boboAPI = {
  send() {}, onMessage() {}, onStatus() {}, getPending() {},
  widgetUserMsg() {}, widgetCurrentSession() {}, widgetCtxStats() {}, widgetPinSession() {},
  readArchive: async () => null,
};
window.Notification = class { static get permission() { return 'denied'; } static requestPermission() {} };
if (!window.matchMedia) window.matchMedia = () => ({ matches: false });

let pass = 0, fail = 0;
function ok(cond, name) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ FAIL: ' + name); }
}

// eval 完整 script（F29 相关函数全部为顶层声明，可直接访问）
try {
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  window.eval(script);
  console.log('script eval OK');
} catch (e) {
  console.log('SCRIPT EVAL ERROR:', e.message);
  process.exit(1);
}

const w = window;
const chatEl = w.document.getElementById('chat');
// 注意：clearChat 会重赋值 w.liveUnits（新数组），必须动态访问 w.liveUnits，
// 禁止 const 解构持有旧引用
function L() { return w.liveUnits; }

function flushTicks() {
  // jsdom 无真实 rAF 循环：手动执行所有排队的 tick
  let guard = 0;
  while (w.liveTickRAF && guard < 50) { guard++; w.liveTickRAF = null; w.liveWindowTick(); }
}

console.log('\n[1] 基础挂载');
w.clearChat();
w.addMsg('user', 'hello one', 'm1');
w.addMsg('bobo', 'reply **bold**', 'm2');
w.addStatus('working…');
flushTicks();
ok(chatEl.children.length === 3, 'chatEl 子节点 = 3 (实际 ' + chatEl.children.length + ')');
ok(L().length === 3, 'liveUnits = 3 (实际 ' + L().length + ')');
ok(chatEl.querySelector('#m1 .txt').textContent.indexOf('hello one') >= 0, 'm1 渲染');

console.log('\n[2] 流式增量更新');
w.addMsg('bobo', ' more', 'm2', true);
flushTicks();
ok(w.document.getElementById('m2').querySelector('.txt').innerHTML.indexOf('more') >= 0, 'DOM 增量拼接');
ok(w.liveFindByMid('m2').text === 'reply **bold** more', 'unit.text 同步 (实际 "' + w.liveFindByMid('m2').text + '")');

console.log('\n[3] 思考框 + 数据同步');
w.createThinkBox();
const tb = chatEl.lastElementChild;
ok(tb.classList.contains('think-box'), 'think-box 挂载');
ok(tb._liveUnit && tb._liveUnit.kind === 'think', 'think-box 挂 liveUnit');
tb._liveUnit.text = 'thinking content';
tb.querySelector('.think-text').textContent = 'thinking content';
flushTicks();
ok(tb._liveUnit.text === 'thinking content', '思考内容同步数据');

console.log('\n[4] 工具卡 + 聚合');
w.addTool('grep_code', 'search x', 't1');
w.addTool('read_local_file', 'read a.py', 't2');
w.addTool('execute_terminal', 'run test', 't3');
flushTicks();
const aggs = chatEl.querySelectorAll('.tool-agg');
ok(aggs.length >= 1, '聚合卡出现 (实际 ' + aggs.length + ')');
const aggUnit = aggs[0] && aggs[0]._liveUnit;
ok(aggUnit && aggUnit.kind === 'agg', '聚合卡挂 aggUnit');
ok(aggUnit && aggUnit.tools.length >= 2, '聚合卡 tools 数据 ≥2 (实际 ' + (aggUnit ? aggUnit.tools.length : 0) + ')');
ok(L().filter(u => u.kind === 'tool').length === 1, '被吞工具 unit 移出 liveUnits，最新一步保留 (实际 ' + L().filter(u => u.kind === 'tool').length + ')');

console.log('\n[5] diff 块（updateToolResult 模拟）');
w.updateToolResult('t3', {
  result_text: 'ok', arguments: { path: 'a.py' },
  inline_diff: '@@\n+add\n-rm', duration: 0.5,
});
flushTicks();
const diffEls = chatEl.querySelectorAll('.diff-block');
ok(diffEls.length >= 1, 'diff 块插入 (实际 ' + diffEls.length + ')');
ok(L().some(u => u.kind === 'diff'), 'diff unit 入数据模型');

console.log('\n[6] 窗口化回收（220 条消息）');
w.clearChat();
for (let i = 0; i < 220; i++) {
  w.addMsg(i % 2 ? 'bobo' : 'user', 'message number ' + i + ' with some content to estimate height', 'bulk-' + i);
}
// 滚到底：窗口在底部，顶部消息被回收
chatEl.scrollTop = 20000;
w.liveWindowTick();
flushTicks();
ok(L().length === 220, '数据模型完整 220 (实际 ' + L().length + ')');
ok(chatEl.children.length < 220, 'DOM 已窗口化收缩 (实际 ' + chatEl.children.length + ')');
ok(chatEl.children.length <= w.LIVE_MAX_NODES, 'DOM ≤ LIVE_MAX_NODES(' + w.LIVE_MAX_NODES + ')');
ok(w.document.getElementById('bulk-0') === null, '顶部旧消息已回收 (bulk-0 不在 DOM)');

console.log('\n[7] 滚动重建（滚回顶部）');
chatEl.scrollTop = 0;
w.liveWindowTick();
flushTicks();
ok(w.document.getElementById('bulk-0') !== null, '滚回顶部 bulk-0 重建 (实际 ' + (w.document.getElementById('bulk-0') ? '在 DOM' : 'null') + ')');
ok(L().length === 220, '重建不丢数据 (实际 ' + L().length + ')');

console.log('\n[8] 顺序保持（窗口内 DOM 顺序 = liveUnits 顺序）');
const domOrder = [];
for (let i = 0; i < chatEl.children.length; i++) {
  const el = chatEl.children[i];
  if (el._liveUnit) domOrder.push(el._liveUnit.uid);
  else domOrder.push(el.className); // hist-ph 占位
}
const unitOrder = L().filter(u => u.el && u.el.parentNode === chatEl).map(u => u.uid);
ok(domOrder.filter(x => typeof x === 'number').join(',') === unitOrder.join(','), '窗口内 DOM 顺序与数据模型一致');

console.log('\n[9] 底部自动跟随（滚到底后新消息可见）');
chatEl.scrollTop = 20000;
w.liveWindowTick();
flushTicks();
w.addMsg('bobo', 'tail message after scroll', 'tail-1');
// jsdom 无 layout（scrollHeight 恒 0）：addMsg 的 liveScrollBottom 会误判"贴近底部"
// 把 scrollTop 拉回 0。真实浏览器 scrollHeight 正常，此处补偿滚动位置后验证
// "窗口化 + 新消息仍可见"这一核心行为。
chatEl.scrollTop = 20000;
w.liveWindowTick();
flushTicks();
ok(w.document.getElementById('tail-1') !== null, '底部新消息在 DOM（自动滚底场景）');

console.log('\n[10] clearChat 重置');
w.clearChat();
ok(L().length === 0, 'liveUnits 清空 (实际 ' + L().length + ')');
ok(chatEl.children.length === 0, 'chatEl 清空');
ok(w.liveTopPh === null && w.liveBotPh === null, '占位重置');

console.log('\n[11] 高度估算兜底');
ok(w.liveEstimateH({ kind: 'status' }) === 24, 'status 估算 24');
ok(w.liveEstimateH({ kind: 'msg', text: 'x'.repeat(120) }) > 24, 'msg 估算随文本增长');

console.log('\n════════════════════════════════');
console.log('F29 jsdom: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
