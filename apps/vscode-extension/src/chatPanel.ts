/**
 * chatPanel.ts — the webview chat panel (VSC-1).
 *
 * Responsibilities:
 *   - create/show a WebviewView (sidebar) with the chat UI
 *   - forward RPC events (message.delta / message.complete / status.update)
 *     to the webview as postMessage
 *   - receive user questions / explain toggles from the webview
 *
 * The webview HTML is generated here (escaped), CSS/JS live in media/.
 */

import * as vscode from 'vscode';

export class ChatPanel {
  private readonly view: vscode.WebviewView;
  private readonly ctx: vscode.ExtensionContext;
  private sessionId: string | null = null;
  private explainOn = false;
  private pairingCb: (() => void) | null = null;

  constructor(ctx: vscode.ExtensionContext, view: vscode.WebviewView) {
    this.ctx = ctx;
    this.view = view;
    view.webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(ctx.extensionUri, 'media')] };
    view.webview.html = this.renderHtml();
    view.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
  }

  setSession(sid: string): void {
    this.sessionId = sid;
    this.post({ kind: 'session', sessionId: sid });
  }

  setExplain(on: boolean): void {
    this.explainOn = on;
    this.post({ kind: 'explain', on });
  }

  /** TICKET-VSC-1B：推"当前选中"预览到 webview（null = 无选区/隐藏卡片）。 */
  setSelection(sel: { filePath: string; startLine: number; endLine: number; text: string } | null): void {
    this.post({ kind: 'selection', sel });
  }

  get explain(): boolean { return this.explainOn; }

  /** Forward a gateway event to the webview. */
  handleEvent(ev: { type: string; [k: string]: unknown }): void {
    this.post({ kind: 'event', type: ev.type, data: ev });
  }

  /** Ask the webview to render an incoming answer chunk (message.delta). */
  handleDelta(sid: string, text: string): void {
    this.post({ kind: 'delta', sessionId: sid, text });
  }

  /** Ask the webview to finalize an answer (message.complete). */
  handleComplete(sid: string, finalText: string): void {
    this.post({ kind: 'complete', sessionId: sid, finalText });
  }

  /** Ask the webview to show the pairing confirmation prompt. */
  askPairing(): void {
    this.post({ kind: 'pairing' });
  }

  onPairingConfirmed(cb: () => void): void {
    this.pairingCb = cb;
  }

  private post(msg: unknown): void {
    // VSC-1B 实弹修复：webview 加载完成前 postMessage 会丢——排队，ready 后补发
    if (!this.webviewReady) { this.pending.push(msg); return; }
    try {
      this.view.webview.postMessage(msg);
    } catch {
      /* view disposed */
    }
  }

  private webviewReady = false;
  private pending: unknown[] = [];

  private onMessage(msg: { kind?: string; text?: string; explain?: boolean; confirm?: boolean }): void {
    if (!msg) return;
    if (msg.kind === 'ready') {
      this.webviewReady = true;
      for (const m of this.pending.splice(0)) {
        try { this.view.webview.postMessage(m); } catch { /* disposed */ }
      }
      return;
    }
    if (msg.kind === 'send' && typeof msg.text === 'string') {
      vscode.commands.executeCommand('bobo.submitQuestion', { text: msg.text });
    } else if (msg.kind === 'toggleExplain' && typeof msg.explain === 'boolean') {
      this.explainOn = msg.explain;
      vscode.commands.executeCommand('bobo.setExplain', msg.explain);
    } else if (msg.kind === 'pairingConfirm' && msg.confirm === true && this.pairingCb) {
      this.pairingCb();
    }
  }

  private renderHtml(): string {
    const media = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'chat.html'));
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root { --bg:#faf9f2; --panel:#fffdf7; --text:#2d2d2d; --muted:#777; --accent:#b3562a; --border:#e0ded4; --code-bg:#f2f1e8; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.6 -apple-system,'SF Pro','Noto Sans SC',system-ui,sans-serif; height:100vh; display:flex; flex-direction:column; }
#header { display:flex; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid var(--border); background:var(--panel); }
#status { font-size:12px; color:var(--muted); }
.dot { width:8px; height:8px; border-radius:50%; background:#c9c4b8; }
.dot.on { background:#4caf50; }
.dot.busy { background:#e8913a; }
#explain-wrap { margin-left:auto; display:flex; align-items:center; gap:4px; font-size:12px; color:var(--muted); }
#chat { flex:1; overflow-y:auto; padding:10px; }
.msg { margin-bottom:12px; }
.msg.user { white-space:pre-wrap; }
.msg.bobo h4 { margin:0 0 4px; font-size:12px; color:var(--muted); font-weight:600; }
pre { background:var(--code-bg); border-radius:6px; padding:8px; overflow-x:auto; font:12px/1.5 'SF Mono',Menlo,monospace; }
code { background:var(--code-bg); border-radius:3px; padding:1px 4px; font:12px 'SF Mono',Menlo,monospace; }
pre code { background:none; padding:0; }
.tok-kw { color:#7a4a9e; } .tok-str { color:#a05c2a; } .tok-cmt { color:#8a8a8a; font-style:italic; }
blockquote { margin:4px 0; padding:2px 10px; border-left:3px solid var(--border); color:var(--muted); }
hr { border:none; border-top:1px solid var(--border); margin:10px 0; }
#inputbar { display:flex; gap:6px; padding:8px; border-top:1px solid var(--border); background:var(--panel); }
#input { flex:1; border:1px solid var(--border); border-radius:6px; padding:6px 8px; background:#fff; font:inherit; }
#send { border:1px solid var(--border); border-radius:6px; background:var(--panel); padding:6px 12px; cursor:pointer; }
#send:hover { background:var(--code-bg); }
#pairing { display:none; margin:10px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--panel); }
#pairing.show { display:block; }
#pairing p { margin:0 0 8px; font-size:13px; }
#pairing button { border:1px solid var(--border); border-radius:6px; padding:4px 10px; cursor:pointer; background:#fff; }
#selection { display:none; margin:8px 10px 0; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--panel); }
#selection.show { display:block; }
#selection .sel-head { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--muted); margin-bottom:4px; }
#selection .sel-file { font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#selection .sel-lines { flex-shrink:0; }
#selection pre { margin:0; max-height:120px; overflow:auto; }
</style>
</head>
<body>
<div id="header">
  <span class="dot" id="dot"></span>
  <span id="status">bobo — connecting…</span>
  <label id="explain-wrap"><input type="checkbox" id="explain"> Explain</label>
</div>
<div id="selection">
  <div class="sel-head"><span class="sel-file" id="sel-file"></span><span class="sel-lines" id="sel-lines"></span></div>
  <pre id="sel-code"></pre>
</div>
<div id="pairing"><p>Allow this VS Code window to talk to the local bobo gateway? The socket is local-only (127.0.0.1 equivalent).</p><button id="pair-ok">Allow</button></div>
<div id="chat"></div>
<div id="inputbar"><input id="input" placeholder="Ask a follow-up…"><button id="send">Send</button></div>
<script>
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
</script>
</body>
</html>`;
  }
}
