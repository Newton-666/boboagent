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
    // VSC-1B 实弹修复：新版 VS Code webview 无 CSP 声明时拦内联脚本——
    // 脚本外置 media/chat.js + nonce + 显式 CSP
    // VSC-1C：vendor（marked/purify/highlight）+ md-render 管线脚本同走 nonce 本地引入
    const nonce = getNonce();
    const scriptUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'chat.js'));
    const mdRenderUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'md-render.js'));
    const markedUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'vendor', 'marked.min.js'));
    const purifyUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'vendor', 'purify.min.js'));
    const highlightUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'vendor', 'highlight.min.js'));
    const cspSource = this.view.webview.cspSource;
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'; font-src ${cspSource}; img-src ${cspSource} https:;">
<style>
/* TICKET-VSC-1C：复刻桌面端 design token（apps/desktop/dist/index.html :root） */
:root { --bg:#faf9f2; --bg2:#f2f1e8; --bg3:#eae8dc; --text:#2d2d2d; --text2:#777; --text-muted:#999; --border:#e0ded4; --hover:#e8e6da; --green:#4caf50; --font-reply:'Charter','Songti SC','Noto Serif CJK SC',serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.6 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif; height:100vh; display:flex; flex-direction:column; }
#header { display:flex; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid var(--border); background:var(--bg2); }
#status { font-size:12px; color:var(--text-muted); }
.dot { width:8px; height:8px; border-radius:50%; background:#c9c4b8; }
.dot.on { background:var(--green); }
.dot.busy { background:#e8913a; }
#explain-wrap { margin-left:auto; display:flex; align-items:center; gap:4px; font-size:12px; color:var(--text-muted); }
#chat { flex:1; overflow-y:auto; padding:12px; }
/* 空态欢迎（复刻桌面端 #welcome-title：font-reply 700 36px 居中） */
#welcome { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px; }
#welcome-title { font-family:var(--font-reply); font-weight:700; font-size:36px; color:var(--text); margin:0; text-align:center; line-height:1.3; padding:0 16px; }
/* 消息气泡（复刻桌面端 index.html:96-159：圆角12 / padding 10-18 / user 右对齐 bg2+border） */
.msg { padding:10px 18px; border-radius:12px; margin-bottom:20px; max-width:85%; }
.msg.user { background:var(--bg2); border:1px solid var(--border); margin-left:auto; white-space:pre-wrap; word-break:break-word; }
.msg .who { font-size:12px; font-weight:600; color:var(--text2); margin-bottom:4px; }
.msg .txt { white-space:pre-wrap; word-break:break-word; }
.msg .txt strong, .msg .txt b { color:#e8913a; }
.msg.bobo .txt { font-family:var(--font-reply); }
.msg.bobo .txt h1 { font-size:20px; font-weight:700; margin:18px 0 6px; }
.msg.bobo .txt h2 { font-size:18px; font-weight:700; margin:16px 0 5px; }
.msg.bobo .txt h3 { font-size:16px; font-weight:700; margin:14px 0 4px; }
.msg.bobo .txt h4 { font-size:15px; font-weight:700; margin:12px 0 3px; }
.msg.bobo .txt h5, .msg.bobo .txt h6 { font-size:14px; font-weight:700; margin:10px 0 3px; color:var(--text2); }
.msg.bobo .txt p { margin:4px 0; }
.msg.bobo .txt ul, .msg.bobo .txt ol { margin:6px 0; padding-left:24px; }
.msg.bobo .txt li { margin:2px 0; }
.msg.bobo .txt blockquote { border-left:3px solid #e8913a; margin:8px 0; padding:2px 12px; color:var(--text2); background:var(--bg2); border-radius:0 6px 6px 0; }
.msg.bobo .txt blockquote p { margin:2px 0; }
.msg.bobo .txt pre { background:var(--bg3); border:1px solid var(--border); border-radius:6px; padding:12px 14px; overflow-x:auto; }
.msg.bobo .txt pre code { background:none; border:none; padding:0; font-size:13px; }
.msg.bobo .txt code { background:var(--bg3); border:1px solid var(--border); padding:1px 5px; border-radius:3px; font-size:13px; }
.msg.bobo .txt table { border-collapse:collapse; margin:8px 0; font-size:13px; width:100%; }
.msg.bobo .txt th, .msg.bobo .txt td { border:1px solid var(--border); padding:6px 10px; text-align:left; }
.msg.bobo .txt th { background:var(--bg3); font-weight:600; }
.msg.bobo .txt tr:nth-child(even) td { background:var(--bg2); }
.msg.bobo .txt a { color:var(--text2); text-decoration:underline; }
.msg.bobo .txt a:hover { text-decoration:underline; }
.msg.bobo .txt hr { border:none; border-top:1px solid var(--border); margin:12px 0; }
.msg.bobo .txt del { color:var(--text2); }
.msg.bobo .txt u { text-decoration:underline; }
/* diff 增色（复刻桌面端：add #7ec87b / del #f48771） */
.msg.bobo .txt .diff-add { color:#7ec87b; }
.msg.bobo .txt .diff-del { color:#f48771; }
.msg.bobo .txt .diff-file { color:var(--text2); font-weight:600; }
/* highlight.js 主题（复刻桌面端：取色只用色板 + 既有语义色） */
.msg.bobo .txt .hljs { color:var(--text); background:transparent; }
.msg.bobo .txt .hljs-comment, .msg.bobo .txt .hljs-quote { color:var(--text-muted); font-style:italic; }
.msg.bobo .txt .hljs-keyword, .msg.bobo .txt .hljs-selector-tag, .msg.bobo .txt .hljs-built_in { color:#e8913a; }
.msg.bobo .txt .hljs-string, .msg.bobo .txt .hljs-regexp, .msg.bobo .txt .hljs-addition { color:#50a14f; }
.msg.bobo .txt .hljs-number, .msg.bobo .txt .hljs-literal { color:var(--text2); }
.msg.bobo .txt .hljs-title, .msg.bobo .txt .hljs-section, .msg.bobo .txt .hljs-attr, .msg.bobo .txt .hljs-attribute { color:var(--text2); }
.msg.bobo .txt .hljs-variable, .msg.bobo .txt .hljs-template-variable { color:var(--text2); }
.msg.bobo .txt .hljs-type, .msg.bobo .txt .hljs-class .hljs-title { color:var(--text2); }
.msg.bobo .txt .hljs-deletion { color:#f48771; }
.msg.bobo .txt .hljs-meta { color:var(--text-muted); }
.msg.bobo .txt .hljs-emphasis { font-style:italic; }
.msg.bobo .txt .hljs-strong { font-weight:700; }
#inputbar { display:flex; gap:6px; padding:8px; border-top:1px solid var(--border); background:var(--bg2); }
#input { flex:1; border:1px solid var(--border); border-radius:6px; padding:6px 8px; background:var(--bg); font:inherit; }
#send { border:1px solid var(--border); border-radius:6px; background:var(--bg); padding:6px 12px; cursor:pointer; }
#send:hover { background:var(--bg3); }
#pairing { display:none; margin:10px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
#pairing.show { display:block; }
#pairing p { margin:0 0 8px; font-size:13px; }
#pairing button { border:1px solid var(--border); border-radius:6px; padding:4px 10px; cursor:pointer; background:var(--bg); }
/* 选区卡片（VSC-1B 功能保留，样式对齐气泡同一套 token） */
#selection { display:none; margin:8px 10px 0; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
#selection.show { display:block; }
#selection .sel-head { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--text-muted); margin-bottom:4px; }
#selection .sel-file { font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#selection .sel-lines { flex-shrink:0; }
#selection pre { margin:0; max-height:120px; overflow:auto; background:var(--bg3); }
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
<div id="welcome"><div id="welcome-title">Let's finish up something today.</div></div>
<div id="chat"></div>
<div id="inputbar"><input id="input" placeholder="Ask a follow-up…"><button id="send">Send</button></div>
<script nonce="${nonce}" src="${markedUri}"></script>
<script nonce="${nonce}" src="${purifyUri}"></script>
<script nonce="${nonce}" src="${highlightUri}"></script>
<script nonce="${nonce}" src="${mdRenderUri}"></script>
<script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

/** 生成 webview CSP nonce（VSC-1B）。 */
function getNonce(): string {
  let text = '';
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) text += possible.charAt(Math.floor(Math.random() * possible.length));
  return text;
}
