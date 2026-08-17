const vscode = acquireVsCodeApi();
const chat = document.getElementById('chat');
const dot = document.getElementById('dot');
const status = document.getElementById('status');
const explain = document.getElementById('explain');
const selCard = document.getElementById('selection');
const selFile = document.getElementById('sel-file');
const selLines = document.getElementById('sel-lines');
const selCode = document.getElementById('sel-code');
let current = null;
function setStatus(s, cls) { status.textContent = s; dot.className = 'dot' + (cls ? ' ' + cls : ''); }
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function addUser(text) { const d = el('div', 'msg user'); d.textContent = text; chat.appendChild(d); chat.scrollTop = chat.scrollHeight; }
function ensureAnswer() {
  if (current) return current;
  const d = el('div', 'msg bobo'); d.appendChild(el('h4', null, 'bobo'));
  current = d; chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  return d;
}
function renderInto(md) {
  // inline mini-renderer (esc-first): same rules as extension markdown.ts
  const esc = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  let t = esc(md);
  t = t.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\n/g, '<br>');
  return t;
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
  else if (m.kind === 'delta') { ensureAnswer().appendChild(el('span', null, m.text)); chat.scrollTop = chat.scrollHeight; }
  else if (m.kind === 'complete') {
    if (current) current.innerHTML = '';
    ensureAnswer();
    current.innerHTML = '<h4>bobo</h4>' + renderInto(m.finalText);
    current = null;
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
