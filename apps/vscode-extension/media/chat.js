// chat.js — TICKET-VSC-1C：webview 面板脚本。
// VSC-1B：外置脚本 + nonce（新版 VS Code 拦内联脚本）+ webview ready 握手。
// VSC-1C：渲染管线换 mdRender（marked → DOMPurify，复刻桌面端 mdReply）；
//   空态欢迎 "Let's finish up something today."（有消息后隐藏）；
//   流式 delta 累积文本容错渲染，complete 定稿重渲染。
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
// md-render.js 未就绪时回退纯文本转义（正文不丢，防 HTML 直插）
const mdRender = (window.mdRender && window.mdRender.mdRender) ||
  (function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); });
let current = null;
let currentText = '';
function setStatus(s, cls) { status.textContent = s; dot.className = 'dot' + (cls ? ' ' + cls : ''); }
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function hideWelcome() { if (welcome) welcome.style.display = 'none'; }
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
window.addEventListener('message', (ev) => {
  const m = ev.data; if (!m || !m.kind) return;
  if (m.kind === 'session') { /* session bound */ }
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
    // 流式：累积文本走 mdRender 容错渲染（半截代码块/表格不 throw），complete 定稿
    const d = ensureAnswer();
    currentText += m.text;
    d.querySelector('.txt').innerHTML = mdRender(currentText);
    chat.scrollTop = chat.scrollHeight;
  }
  else if (m.kind === 'complete') {
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
vscode.postMessage({ kind: 'ready' });
