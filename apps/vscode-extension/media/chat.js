// chat.js — TICKET-VSC-2：webview 面板脚本。
// VSC-1B：外置脚本 + nonce + webview ready 握手。
// VSC-1C：渲染管线 mdRender（marked → DOMPurify 复刻桌面端）；空态欢迎；流式累积。
// VSC-2A：对比度走 CSS 变量（chatPanel.ts :root），本文件零色值。
// VSC-2B：会话切换（New chat/下拉列表）、思考折叠块（think-box）、工具行（可折叠）。
// VSC-2C：diff 卡 Accept/Reject（决策发给 host 执行 vscode.diff / 快照写回）。
// VSC-2D：台账折叠区（Ledger）。
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
// md-render.js 未就绪时回退纯文本转义（正文不丢，防 HTML 直插）
const mdRender = (window.mdRender && window.mdRender.mdRender) ||
  (function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); });
// parts.js：UI 组件 HTML 构建（纯函数，见 parts.js）
const parts = (window.parts) || {
  buildThinkBlock: (t) => '<div class="think-box"><div class="think-label"><span>思考过程</span></div><div class="think-text">' + String(t) + '</div></div>',
  buildToolRow: (ev) => '<div class="tool-row"><span class="tool-dot run"></span><span class="tool-name">' + (ev.name || 'tool') + '</span></div>',
  buildDiffCard: (f, t) => '<div class="diff-card" data-file="' + f + '"><div class="diff-file">' + (t || f) + '</div><div class="diff-actions"><button class="accept">Accept</button><button class="reject">Reject</button></div></div>',
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
function addUser(text) {
  hideWelcome();
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

// ── VSC-2B：工具行（start→run 点；complete→done/fail 点 + 可展开摘要）──
const toolRows = {}; // name → row 元素
function addToolRow(ev) {
  hideWelcome();
  const name = String(ev.name || 'tool');
  const isStart = (ev.type || 'tool.start') === 'tool.start';
  // 复用同名未完成行；否则新建
  let row = toolRows[name];
  if (!row || row.dataset.done === '1') {
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildToolRow(ev);
    row = wrap.firstElementChild;
    row.dataset.name = name;
    row.dataset.done = isStart ? '0' : '1';
    row.addEventListener('click', () => {
      row.classList.toggle('open');
      const body = row.nextElementSibling;
      if (body && body.classList.contains('tool-body')) body.classList.toggle('open', row.classList.contains('open'));
    });
    chat.appendChild(row);
    toolRows[name] = row;
    // 展开体（parts.buildToolRow 返回 row+body 两个元素）紧跟行挂载
    const body = wrap.children[1];
    if (body && body.classList.contains('tool-body')) row.after(body);
  } else {
    // 更新既有行（complete 覆盖 start）
    const wrap = document.createElement('div');
    wrap.innerHTML = parts.buildToolRow(ev);
    const fresh = wrap.firstElementChild;
    row.innerHTML = fresh.innerHTML;
    row.querySelector('.tool-dot').className = fresh.querySelector('.tool-dot').className;
    row.querySelector('.tool-ctx').textContent = fresh.querySelector('.tool-ctx').textContent;
    row.dataset.done = '1';
    if (fresh.nextElementSibling && fresh.nextElementSibling.classList.contains('tool-body')) {
      const body = fresh.nextElementSibling;
      row.after(body);
    }
  }
  chat.scrollTop = chat.scrollHeight;
}

// ── VSC-2C：diff 卡（Accept/Reject）──
function addDiffCard(filePath, title) {
  hideWelcome();
  const wrap = document.createElement('div');
  wrap.innerHTML = parts.buildDiffCard(filePath, title);
  const card = wrap.firstElementChild;
  card.querySelector('.accept').addEventListener('click', () => vscode.postMessage({ kind: 'diffDecision', filePath, accept: true }));
  card.querySelector('.reject').addEventListener('click', () => vscode.postMessage({ kind: 'diffDecision', filePath, accept: false }));
  chat.appendChild(card);
  chat.scrollTop = chat.scrollHeight;
}
function removeDiffCard(filePath) {
  for (const card of chat.querySelectorAll('.diff-card')) {
    if (card.dataset.file === filePath) card.remove();
  }
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
      // 历史 tool 消息渲染为已完成的工具行（name + 截断内容）
      addToolRow({ type: 'tool.complete', name: m.name || 'tool', result_text: m.content || m.context || '', inline_diff: m.inline_diff || '' });
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
    for (const k in toolRows) delete toolRows[k];
    showWelcome();
    setStatus('done', 'on');
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
    addToolRow(m.event || {});
  }
  else if (m.kind === 'diffCard') { addDiffCard(m.filePath, m.title); }
  else if (m.kind === 'diffCardDone') { removeDiffCard(m.filePath); }
  else if (m.kind === 'ledger') { renderLedger(m.items); }
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
document.getElementById('send').addEventListener('click', () => {
  const inp = document.getElementById('input');
  const t = inp.value.trim(); if (!t) return;
  addUser(t); inp.value = '';
  vscode.postMessage({ kind: 'send', text: t });
});
document.getElementById('input').addEventListener('keydown', (e) => { if (e.key === 'Enter') document.getElementById('send').click(); });
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
