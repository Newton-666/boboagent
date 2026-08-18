// chat.js — TICKET-VSC-2：webview 面板脚本。
// VSC-1B：外置脚本 + nonce + webview ready 握手。
// VSC-1C：渲染管线 mdRender（marked → DOMPurify 复刻桌面端）；空态欢迎；流式累积。
// VSC-2A：对比度走 CSS 变量（chatPanel.ts :root），本文件零色值。
// VSC-2B：会话切换（New chat/下拉列表）、思考折叠块（think-box）。
// VSC-2C：diff 快照只读展示（审批已前移到执行前闸门）。
// VSC-2D：台账折叠区（Ledger）。
// 票 VSC-2B：工具聚合卡（桌面端移植）、审批卡（approval.request 唯一卡）、
// 停止按钮（Send⇄Stop + Esc → session.interrupt）。
const vscode = acquireVsCodeApi();
const chat = document.getElementById('chat');
const dot = document.getElementById('dot');
const status = document.getElementById('status');
const explain = document.getElementById('explain');
const selCard = document.getElementById('selection');
const selFile = document.getElementById('sel-file');
const selLines = document.getElementById('sel-lines');
const selCode = document.getElementById('sel-code');
const welcome = document.getElementById('welcome');
const sessCurrent = document.getElementById('sess-current');
const sessDropdown = document.getElementById('sess-dropdown');
const ledgerBody = document.getElementById('ledger-body');
const ledgerCount = document.getElementById('ledger-count');
const ledger = document.getElementById('ledger');
const sendBtn = document.getElementById('send');
const stopBtn = document.getElementById('stop');
const inputEl = document.getElementById('input');
// md-render.js 未就绪时回退纯文本转义（正文不丢，防 HTML 直插）
const mdRender = (window.mdRender && window.mdRender.mdRender) ||
  (function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); });
// parts.js：UI 组件 HTML 构建（纯函数，见 parts.js）
const parts = (window.parts) || {
  buildThinkBlock: (t) => '<div class="think-box"><div class="think-label"><span>思考过程</span></div><div class="think-text">' + String(t) + '</div></div>',
  buildToolAggCard: () => '<div class="tool-agg"><span class="tool-agg-head"><span class="tool-agg-arrow">▸</span><span class="tool-agg-title">0 个工具调用</span></span><div class="tool-agg-body" style="display:none"></div></div>',
  buildToolItem: (ev) => '<div class="tool" data-name="' + (ev.name || 'tool') + '"><span class="tool-dot done"></span><span class="tool-name">' + (ev.name || 'tool') + '</span><div class="tool-result"></div></div>',
  buildApprovalCard: (ev) => '<div class="approval-card"><div class="approval-title">' + (ev.tool_name || ev.name || 'tool') + ' 请求写审批</div><div class="diff-actions"><button class="approve">Accept</button><button class="reject">Reject</button></div></div>',
  buildDiffBlock: (d) => '<div class="diff-block"><pre>' + String(d) + '</pre></div>',
  buildLedgerItem: (it) => '<div class="lg-item"><span class="lg-dot ' + (it.status || 'pending') + '"></span><span class="lg-title">' + (it.title || it.id || '') + '</span></div>',
  buildSessionItem: (s, a) => '<div class="sess-item' + (a ? ' active' : '') + '" data-id="' + s.id + '"><div>' + (s.title || s.id) + '</div><div class="sess-meta">' + (s.message_count || 0) + ' msgs</div></div>',
};
let current = null;      // 当前流式 bobo 气泡
let currentText = '';    // 流式累积文本
let currentSid = null;   // 当前会话（GW-MULTI 全广播语义：只渲染本会话事件）
let sessions = [];       // 会话列表缓存

function setStatus(s, cls) { status.textContent = s; dot.className = 'dot' + (cls ? ' ' + cls : ''); }
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function hideWelcome() { if (welcome) welcome.style.display = 'none'; }
function showWelcome() { if (welcome) welcome.style.display = ''; }
// TICKET-COST-5：动态块渲染剥离（方案 D）——历史显示【COST-2 动态块】治理。
// 与桌面端 index.html stripDynBlock 同逻辑（injector.py:750-765 格式：
// 标记\n + 块间\n\n连接 + \n\n + 原文；原文分隔 = 最后一个 \n\n）。
function stripDynBlock(text) {
  if (!text || typeof text !== 'string') return text;
  if (text.indexOf('【COST-2 动态块】') !== 0) return text;
  const i = text.lastIndexOf('\n\n');
  if (i < 0) return '';
  return text.slice(i + 2);
}
function addUser(text) {
  hideWelcome();
  text = stripDynBlock(text);   // TICKET-COST-5：历史（renderHistory）与实时统一剥离，无标记原样
  const d = el('div', 'msg user');
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}
function ensureAnswer() {
  if (current) return current;
  hideWelcome();
  const d = el('div', 'msg bobo');
  d.appendChild(el('div', 'who', 'bobo'));
  const txt = el('div', 'txt');
  d.appendChild(txt);
  current = d;
  currentText = '';
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

// ── VSC-2B：思考折叠块 ──
function addThinkBox(text) {
  hideWelcome();
  const box = document.createElement('div');
  box.innerHTML = parts.buildThinkBlock(text);
  const node = box.firstElementChild;
  node.addEventListener('click', () => node.classList.toggle('open'));
  chat.appendChild(node);
  chat.scrollTop = chat.scrollHeight;
}

// ── 票 VSC-2B：工具聚合卡（桌面端 addTool/toolSummary/appendDiffBlock 移植）──
// 一轮内的工具调用全部收进一张 .tool-agg 卡："N 个工具调用"一行，默认折叠。
// 工具卡：icon + 状态点 + 名称 + 摘要；complete 时更新状态点并追加只读 diff 块。
let aggCard = null;        // 当前回合聚合卡元素
let aggBodyEl = null;      // 聚合卡 body（工具卡挂这里）
let aggTitleEl = null;     // "N 个工具调用" 标题
let aggCount = 0;          // 当前回合工具计数
const toolItems = {};      // name → 工具卡元素（同名工具复用更新）

function ensureAggCard() {
  if (aggCard && chat.contains(aggCard)) return;
  hideWelcome();
  const wrap = document.createElement('div');
  wrap.innerHTML = parts.buildToolAggCard();
  aggCard = wrap.firstElementChild;
  aggBodyEl = aggCard.querySelector('.tool-agg-body');
  aggTitleEl = aggCard.querySelector('.tool-agg-title');
  aggCard.addEventListener('click', (e) => {
    if (e.target.closest('.tool')) return; // 点工具卡本身不折叠（卡内自有展开）
    const body = aggCard.querySelector('.tool-agg-body');
    const arrow = aggCard.querySelector('.tool-agg-arrow');
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    if (arrow) arrow.textContent = open ? '▸' : '▾';
  });
  chat.appendChild(aggCard);
}

function addToolItem(ev) {
  ensureAggCard();
  aggCount++;
  aggTitleEl.textContent = aggCount + ' 个工具调用';
  const name = String(ev.name || 'tool');
  const isStart = (ev.type || 'tool.start') === 'tool.start';
  let item = toolItems[name];
  if (!item || !chat.contains(item)) {
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildToolItem(ev);
    item = wrap.firstElementChild;
    // 展开体（buildToolItem 返回 item+body 两个元素）紧跟 item 挂载
    item.addEventListener('click', () => {
      const r = item.querySelector('.tool-result');
      if (r) { r.classList.toggle('open'); const tg = item.querySelector('.tool-toggle'); if (tg) { tg.textContent = r.classList.contains('open') ? '▾' : '▸'; tg.style.display = 'inline'; } }
    });
    aggBodyEl.appendChild(item);
    toolItems[name] = item;
    const body = wrap.children[1];
    if (body && body.classList.contains('tool-body')) item.after(body);
  } else {
    // 复用：complete 覆盖 start（状态点 + 摘要 + 结果体）
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildToolItem(ev);
    const fresh = wrap.firstElementChild;
    item.querySelector('.tool-dot').className = fresh.querySelector('.tool-dot').className;
    const ctx = fresh.querySelector('.tool-context');
    const ctxOld = item.querySelector('.tool-context');
    if (ctx) { if (ctxOld) ctxOld.textContent = ctx.textContent; else item.insertBefore(document.createTextNode(' '), item.querySelector('.tool-toggle')), item.insertBefore(ctx, item.querySelector('.tool-toggle')); }
    if (fresh.nextElementSibling && fresh.nextElementSibling.classList.contains('tool-body')) {
      const body = fresh.nextElementSibling;
      item.after(body);
    }
  }
  // 票 VSC-2B：complete + inline_diff → 只读 diff 块（appendDiffBlock 同款）
  if (!isStart && ev.inline_diff) {
    const dWrap = document.createElement('div');
    dWrap.innerHTML = parts.buildDiffBlock(ev.inline_diff);
    const block = dWrap.firstElementChild;
    const agg = item.closest('.tool-agg');
    const anchor = agg || item;
    if (anchor.nextSibling) chat.insertBefore(block, anchor.nextSibling);
    else chat.appendChild(block);
  }
  chat.scrollTop = chat.scrollHeight;
}

// ── 票 VSC-2B：审批卡（approval.request 唯一卡；Accept/Reject → host respond）──
// 串行闸门：approvalGate 保证同一时刻只有一张卡（新卡到来自动关旧卡，防双弹）。
const approvalGate = parts.createApprovalGate();
function addApprovalCard(ev) {
  hideWelcome();
  approvalGate.open(() => removeApprovalCard()); // 旧卡被顶掉时先收走
  const wrap = document.createElement('div');
  wrap.innerHTML = parts.buildApprovalCard(ev);
  const card = wrap.firstElementChild;
  card.querySelector('.approve').addEventListener('click', () => vscode.postMessage({ kind: 'approvalDecision', choice: parts.APPROVAL_CHOICES.accept }));
  card.querySelector('.reject').addEventListener('click', () => vscode.postMessage({ kind: 'approvalDecision', choice: parts.APPROVAL_CHOICES.reject }));
  chat.appendChild(card);
  chat.scrollTop = chat.scrollHeight;
}
function removeApprovalCard() {
  approvalGate.close();
  for (const card of chat.querySelectorAll('.approval-card')) card.remove();
}
function approvalTimeoutCard() {
  const id = approvalGate.timeout();
  if (id === null) return;
  const card = chat.querySelector('.approval-card');
  if (!card) return;
  card.classList.add('timeout');
  const actions = card.querySelector('.diff-actions');
  if (actions) actions.innerHTML = '<span class="approval-timedout">已超时（120s 未确认，工具已放弃）</span>';
}

// ── VSC-2B：Send⇄Stop 切换（host message.start/complete 驱动）──
function setRunning(running) {
  const v = parts.runningView(!!running);
  sendBtn.style.display = v.send;
  stopBtn.classList.toggle('show', v.stop === 'show');
}

// ── VSC-2B：会话列表 ──
function renderSessions() {
  sessDropdown.innerHTML = '';
  for (const s of sessions) {
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildSessionItem(s, s.id === currentSid);
    const item = wrap.firstElementChild;
    item.addEventListener('click', () => {
      sessDropdown.classList.remove('show');
      if (s.id !== currentSid) vscode.postMessage({ kind: 'switchSession', sessionId: s.id });
    });
    sessDropdown.appendChild(item);
  }
}

// ── VSC-2D：台账折叠区 ──
function renderLedger(items) {
  ledgerBody.innerHTML = '';
  if (!items || !items.length) { ledgerCount.textContent = ''; return; }
  ledgerCount.textContent = ' · ' + items.length;
  for (const it of items) {
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildLedgerItem(it);
    ledgerBody.appendChild(wrap.firstElementChild);
  }
}

// ── VSC-2B：历史渲染（session.resume transcript）──
function renderHistory(messages) {
  for (const m of (messages || [])) {
    const role = m.role;
    if (role === 'user') {
      addUser(m.text || '');
    } else if (role === 'assistant') {
      if (m.thinking) addThinkBox(m.thinking);
      if (m.text) {
        const d = ensureAnswer();
        d.querySelector('.txt').innerHTML = mdRender(m.text);
        current = null; currentText = '';
      }
    } else if (role === 'tool') {
      // 历史 tool 消息渲染为聚合卡内工具项（name + 截断内容）
      addToolItem({ type: 'tool.complete', name: m.name || 'tool', result_text: m.content || m.context || '', inline_diff: m.inline_diff || '' });
    }
  }
  if (current) { current = null; currentText = ''; }
}

window.addEventListener('message', (ev) => {
  const m = ev.data; if (!m || !m.kind) return;
  if (m.kind === 'session') {
    currentSid = m.sessionId || currentSid;
    const cur = sessions.find((s) => s.id === currentSid);
    sessCurrent.textContent = (cur && cur.title) || (currentSid ? 'session ' + currentSid.slice(-6) : 'new session');
  }
  else if (m.kind === 'clearChat') {
    chat.innerHTML = '';
    current = null; currentText = '';
    aggCard = null; aggBodyEl = null; aggTitleEl = null; aggCount = 0;
    for (const k in toolItems) delete toolItems[k];
    showWelcome();
    setStatus('done', 'on');
    setRunning(false);
  }
  else if (m.kind === 'history') { renderHistory(m.messages); setStatus('done', 'on'); }
  else if (m.kind === 'sessionList') {
    sessions = Array.isArray(m.sessions) ? m.sessions : [];
    renderSessions();
    if (currentSid) {
      const cur = sessions.find((s) => s.id === currentSid);
      sessCurrent.textContent = (cur && cur.title) || sessCurrent.textContent;
    }
  }
  else if (m.kind === 'think') {
    if (m.sessionId && m.sessionId !== currentSid) return; // GW-MULTI 过滤
    addThinkBox(m.text);
  }
  else if (m.kind === 'tool') {
    if (m.sessionId && m.sessionId !== currentSid) return; // GW-MULTI 过滤
    addToolItem(m.event || {});
  }
  else if (m.kind === 'approvalCard') { addApprovalCard(m.event || {}); }
  else if (m.kind === 'approvalDone') { removeApprovalCard(); }
  else if (m.kind === 'approvalTimeout') { approvalTimeoutCard(); }
  else if (m.kind === 'ledger') { renderLedger(m.items); }
  else if (m.kind === 'busy') { setRunning(!!m.running); }
  else if (m.kind === 'status') { setStatus(String(m.text || '').slice(0, 60), 'busy'); }
  else if (m.kind === 'explain') { explain.checked = m.on; }
  else if (m.kind === 'selection') {
    const s = m.sel;
    if (!s || !s.filePath) { selCard.classList.remove('show'); return; }
    selFile.textContent = s.filePath;
    selLines.textContent = ':' + s.startLine + '-' + s.endLine;
    selCode.textContent = s.text;
    selCard.classList.add('show');
  }
  else if (m.kind === 'pairing') { document.getElementById('pairing').classList.add('show'); }
  else if (m.kind === 'event') {
    const t = m.type;
    if (t === 'gateway.ready') setStatus('connected', 'on');
    else if (t === 'gateway.error') setStatus('gateway error', 'busy');
    else if (t === 'message.start') setStatus('bobo is thinking…', 'busy');
    else if (t === 'status.update') setStatus(String(m.data.text || '').slice(0, 60), 'busy');
  }
  else if (m.kind === 'delta') {
    if (m.sessionId && m.sessionId !== currentSid) return;
    const d = ensureAnswer();
    currentText += m.text;
    d.querySelector('.txt').innerHTML = mdRender(currentText);
    chat.scrollTop = chat.scrollHeight;
  }
  else if (m.kind === 'complete') {
    if (m.sessionId && m.sessionId !== currentSid) return;
    if (current) { current.innerHTML = ''; current = null; currentText = ''; }
    const d = ensureAnswer();
    d.querySelector('.txt').innerHTML = mdRender(m.finalText);
    current = null;
    currentText = '';
    setStatus('done', 'on');
  }
});
sendBtn.addEventListener('click', () => {
  const t = inputEl.value.trim(); if (!t) return;
  addUser(t); inputEl.value = '';
  vscode.postMessage({ kind: 'send', text: t });
});
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendBtn.click();
  else if (e.key === 'Escape') { e.preventDefault(); vscode.postMessage({ kind: 'stop' }); } // 票 VSC-2B：Esc 停止
});
// 票 VSC-2B：停止钮 → host session.interrupt
stopBtn.addEventListener('click', () => vscode.postMessage({ kind: 'stop' }));
explain.addEventListener('change', () => vscode.postMessage({ kind: 'toggleExplain', explain: explain.checked }));
document.getElementById('pair-ok').addEventListener('click', () => { document.getElementById('pairing').classList.remove('show'); vscode.postMessage({ kind: 'pairingConfirm', confirm: true }); });
// VSC-2B：会话栏交互
document.getElementById('new-chat').addEventListener('click', () => vscode.postMessage({ kind: 'newChat' }));
document.getElementById('sess-toggle').addEventListener('click', () => {
  if (!sessDropdown.classList.contains('show')) vscode.postMessage({ kind: 'requestSessions' });
  sessDropdown.classList.toggle('show');
});
document.addEventListener('click', (e) => { if (!sessDropdown.contains(e.target) && e.target.id !== 'sess-toggle') sessDropdown.classList.remove('show'); });
// VSC-2D：台账折叠
ledger.addEventListener('click', () => ledger.classList.toggle('open'));
vscode.postMessage({ kind: 'ready' });
