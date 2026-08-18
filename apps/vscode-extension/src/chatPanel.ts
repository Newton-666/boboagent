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
  private newChatCb: (() => void) | null = null;
  private switchSessionCb: ((sid: string) => void) | null = null;
  private requestSessionsCb: (() => void) | null = null;
  // 票 VSC-2B：审批卡决策（choice: allow/deny）。diffDecisionCb 随审批闸门废弃
  //（Reject 语义前移到执行前，diff 展示只读）。
  private approvalDecisionCb: ((choice: string) => void) | null = null;
  // 票 VSC-2B：停止按钮回调（webview 点停止/Esc → host 发 session.interrupt）
  private stopCb: (() => void) | null = null;

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

  /** TICKET-VSC-2B：推会话列表到 webview。 */
  setSessions(sessions: unknown[]): void {
    this.post({ kind: 'sessionList', sessions });
  }

  /** TICKET-VSC-2B：推思考过程（折叠块）到 webview。 */
  handleThinking(sid: string, text: string): void {
    if (!text) return;
    this.post({ kind: 'think', sessionId: sid, text });
  }

  /** TICKET-VSC-2B/C：推工具行事件到 webview（tool.start / tool.complete）。 */
  handleTool(sid: string, ev: Record<string, unknown>): void {
    this.post({ kind: 'tool', sessionId: sid, event: ev });
  }

  /** 票 VSC-2B：审批卡（tool_name + arguments 摘要；执行前无 diff，不显示 diff）。 */
  showApprovalCard(sid: string, ev: Record<string, unknown>): void {
    this.post({ kind: 'approvalCard', sessionId: sid, event: ev });
  }

  /** 票 VSC-2B：审批已响应（allow/deny），收起卡片。 */
  approvalDone(): void {
    this.post({ kind: 'approvalDone' });
  }

  /** 票 VSC-2B：120s 超时（引擎侧放弃），卡片置灰"已超时"。 */
  approvalTimeout(sid: string): void {
    this.post({ kind: 'approvalTimeout', sessionId: sid });
  }

  /** TICKET-VSC-2D：推台账条目到折叠区。 */
  setLedger(items: { id: string; title: string; status: string }[]): void {
    this.post({ kind: 'ledger', items });
  }

  /** TICKET-VSC-2B：清空面板（New chat 后）。 */
  clearChat(): void {
    this.post({ kind: 'clearChat' });
  }

  /** TICKET-VSC-2B：渲染会话历史（session.resume 的 transcript）。 */
  setHistory(messages: unknown[]): void {
    this.post({ kind: 'history', messages });
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

  /** 票 VSC-2B：状态栏文本（如中断后 Stopped）。 */
  setStatus(text: string): void {
    this.post({ kind: 'status', text });
  }

  /** Ask the webview to show the pairing confirmation prompt. */
  askPairing(): void {
    this.post({ kind: 'pairing' });
  }

  onPairingConfirmed(cb: () => void): void {
    this.pairingCb = cb;
  }

  /** TICKET-VSC-2B：webview 点了 New chat。 */
  onNewChat(cb: () => void): void { this.newChatCb = cb; }

  /** TICKET-VSC-2B：webview 点了某会话（切换）。 */
  onSwitchSession(cb: (sid: string) => void): void { this.switchSessionCb = cb; }

  /** TICKET-VSC-2B：webview 请求会话列表。 */
  onRequestSessions(cb: () => void): void { this.requestSessionsCb = cb; }

  /** 票 VSC-2B：webview 对审批卡做了 Accept/Reject 决定（choice: allow/deny）。 */
  onApprovalDecision(cb: (choice: string) => void): void { this.approvalDecisionCb = cb; }

  /** 票 VSC-2B：回合进行中 Send⇄停止钮切换（message.start→true / complete→false）。 */
  setRunning(running: boolean): void {
    this.post({ kind: 'busy', running });
  }

  /** 票 VSC-2B：webview 请求停止（点停止钮/Esc）。 */
  onStopRequested(cb: () => void): void { this.stopCb = cb; }

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

  private onMessage(msg: { kind?: string; text?: string; explain?: boolean; confirm?: boolean; sessionId?: string; filePath?: string; accept?: boolean; choice?: string }): void {
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
    } else if (msg.kind === 'newChat' && this.newChatCb) {
      this.newChatCb();
    } else if (msg.kind === 'switchSession' && typeof msg.sessionId === 'string' && this.switchSessionCb) {
      this.switchSessionCb(msg.sessionId);
    } else if (msg.kind === 'requestSessions' && this.requestSessionsCb) {
      this.requestSessionsCb();
    } else if (msg.kind === 'approvalDecision' && typeof msg.choice === 'string' && this.approvalDecisionCb) {
      this.approvalDecisionCb(msg.choice);
    } else if (msg.kind === 'stop' && this.stopCb) {
      this.stopCb();
    }
  }

  private renderHtml(): string {
    // VSC-1B 实弹修复：新版 VS Code webview 无 CSP 声明时拦内联脚本——
    // 脚本外置 media/chat.js + nonce + 显式 CSP
    // VSC-1C：vendor（marked/purify/highlight）+ md-render 管线脚本同走 nonce 本地引入
    const nonce = getNonce();
    const scriptUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'chat.js'));
    const partsUri = this.view.webview.asWebviewUri(vscode.Uri.joinPath(this.ctx.extensionUri, 'media', 'parts.js'));
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
/* TICKET-VSC-1C：复刻桌面端 design token；VSC-2A：对比度治理（WCAG AA ≥4.5:1，
   色值对照表见 src/contrast.ts，勿手动改色——测试矩阵会拦不达标的回退） */
:root { --bg:#faf9f2; --bg2:#f2f1e8; --bg3:#eae8dc; --text:#2d2d2d; --text2:#5c5c5c; --text-muted:#6f6f6f; --border:#e0ded4; --hover:#e8e6da; --green:#4caf50; --accent:#a34e1a; --str:#2f6b2e; --num:#7a5f32; --del:#b3402a; --font-reply:'Charter','Songti SC','Noto Serif CJK SC',serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.6 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif; height:100vh; display:flex; flex-direction:column; }
#header { display:flex; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid var(--border); background:var(--bg2); }
#status { font-size:12px; color:var(--text2); }
.dot { width:8px; height:8px; border-radius:50%; background:#c9c4b8; }
.dot.on { background:var(--green); }
.dot.busy { background:#e8913a; }
#explain-wrap { margin-left:auto; display:flex; align-items:center; gap:4px; font-size:12px; color:var(--text2); }
#chat { flex:1; overflow-y:auto; padding:12px; }
/* 空态欢迎（复刻桌面端 #welcome-title：font-reply 700 36px 居中） */
#welcome { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px; }
#welcome-title { font-family:var(--font-reply); font-weight:700; font-size:36px; color:var(--text); margin:0; text-align:center; line-height:1.3; padding:0 16px; }
/* 消息气泡（复刻桌面端 index.html:96-159：圆角12 / padding 10-18 / user 右对齐 bg2+border） */
.msg { padding:10px 18px; border-radius:12px; margin-bottom:20px; max-width:85%; }
.msg.user { background:var(--bg2); border:1px solid var(--border); margin-left:auto; white-space:pre-wrap; word-break:break-word; }
.msg .who { font-size:12px; font-weight:600; color:var(--text2); margin-bottom:4px; }
.msg .txt { white-space:pre-wrap; word-break:break-word; }
.msg .txt strong, .msg .txt b { color:var(--accent); }
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
.msg.bobo .txt .diff-add { color:var(--str); }
.msg.bobo .txt .diff-del { color:var(--del); }
.msg.bobo .txt .diff-file { color:var(--text2); font-weight:600; }
/* highlight.js 主题（复刻桌面端：取色只用色板 + 既有语义色） */
/* owner 实弹反馈（2026-08-17）：窄面板里 --text2 太淡，代码正文 token 一律压回 --text 深色 */
.msg.bobo .txt .hljs { color:var(--text); background:transparent; }
.msg.bobo .txt .hljs-comment, .msg.bobo .txt .hljs-quote { color:var(--text2); font-style:italic; }
.msg.bobo .txt .hljs-keyword, .msg.bobo .txt .hljs-selector-tag, .msg.bobo .txt .hljs-built_in { color:var(--accent); }
.msg.bobo .txt .hljs-string, .msg.bobo .txt .hljs-regexp, .msg.bobo .txt .hljs-addition { color:var(--str); }
.msg.bobo .txt .hljs-number, .msg.bobo .txt .hljs-literal { color:var(--num); }
.msg.bobo .txt .hljs-title, .msg.bobo .txt .hljs-section, .msg.bobo .txt .hljs-attr, .msg.bobo .txt .hljs-attribute { color:var(--text); }
.msg.bobo .txt .hljs-variable, .msg.bobo .txt .hljs-template-variable { color:var(--text); }
.msg.bobo .txt .hljs-type, .msg.bobo .txt .hljs-class .hljs-title { color:var(--text); }
.msg.bobo .txt .hljs-deletion { color:var(--del); }
.msg.bobo .txt .hljs-meta { color:var(--text2); }
.msg.bobo .txt .hljs-emphasis { font-style:italic; }
.msg.bobo .txt .hljs-strong { font-weight:700; }
#inputbar { display:flex; gap:6px; padding:8px; border-top:1px solid var(--border); background:var(--bg2); }
#input { flex:1; border:1px solid var(--border); border-radius:6px; padding:6px 8px; background:var(--bg); font:inherit; }
#send { border:1px solid var(--border); border-radius:6px; background:var(--bg); padding:6px 12px; cursor:pointer; }
#send:hover { background:var(--bg3); }
/* 票 VSC-2B：停止按钮（参照桌面端 #stop-btn：圆形、红系 rgba(244,135,113,*)、■） */
#stop { border:1px solid rgba(244,135,113,0.4); border-radius:50%; background:rgba(244,135,113,0.12); color:#f48771; width:28px; height:28px; padding:0; cursor:pointer; font-size:12px; line-height:1; display:none; align-items:center; justify-content:center; flex-shrink:0; }
#stop:hover { background:rgba(244,135,113,0.22); }
#stop.show { display:flex; }
#pairing { display:none; margin:10px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
#pairing.show { display:block; }
#pairing p { margin:0 0 8px; font-size:13px; }
#pairing button { border:1px solid var(--border); border-radius:6px; padding:4px 10px; cursor:pointer; background:var(--bg); }
/* 选区卡片（VSC-1B 功能保留，样式对齐气泡同一套 token） */
#selection { display:none; margin:8px 10px 0; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
#selection.show { display:block; }
#selection .sel-head { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--text2); margin-bottom:4px; }
#selection .sel-file { font-weight:600; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#selection .sel-lines { flex-shrink:0; }
#selection pre { margin:0; max-height:120px; overflow:auto; background:var(--bg3); }
/* === VSC-2B：思考折叠块（对齐桌面端 think-box：默认收起只留摘要行，点击展开）=== */
.think-box { padding:8px 12px; margin:8px 0; border-radius:8px; font-size:13px; color:var(--text2); background:var(--bg2); border:1px solid var(--border); cursor:pointer; user-select:none; }
.think-box .think-label { font-size:11px; font-weight:600; color:var(--text2); display:flex; align-items:center; gap:6px; }
.think-box .think-caret { font-size:10px; transition:transform 0.15s; }
.think-box.open .think-caret { transform:rotate(90deg); }
.think-box .think-text { white-space:pre-wrap; word-break:break-word; line-height:1.5; margin-top:6px; display:none; color:var(--text); }
.think-box.open .think-text { display:block; }
/* === 票 VSC-2B：工具聚合卡（对齐桌面端 .tool-agg/.tool 视觉）=== */
.tool-agg { margin:6px 0; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
.tool-agg-head { display:block; padding:8px 12px; font-size:12px; color:var(--text2); cursor:pointer; user-select:none; }
.tool-agg-head:hover { background:var(--bg3); }
.tool-agg-arrow { display:inline-block; transition:transform 0.15s; margin-right:6px; }
.tool-agg-body { border-top:1px solid var(--border); padding:4px 0; }
.tool { font-size:13px; color:var(--text2); padding:6px 12px; cursor:pointer; border-radius:6px; display:flex; align-items:center; gap:8px; border:1px solid transparent; transition:background 0.15s, border-color 0.15s; }
.tool:hover { background:var(--bg3); border-color:var(--border); }
.tool .tool-icon { font-size:13px; flex-shrink:0; }
.tool .tool-ic { flex-shrink:0; color:var(--text-muted); display:inline-block; vertical-align:-2px; }
.tool .tool-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.tool .tool-dot.run { background:#e8913a; }
.tool .tool-dot.done { background:var(--green); }
.tool .tool-dot.fail { background:var(--del); }
.tool .tool-name { font-weight:600; color:var(--text); flex-shrink:0; }
.tool .tool-context { color:var(--text2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; }
.tool .tool-toggle { font-size:10px; color:var(--text2); flex-shrink:0; }
.tool .tool-result { display:none; width:100%; margin-top:4px; font-size:12px; color:var(--text); white-space:pre-wrap; word-break:break-word; }
.tool .tool-result.open { display:block; }
.tool-body { display:none; margin:0 0 4px; padding:6px 10px; background:var(--bg3); border:1px solid var(--border); border-radius:6px; font-size:12px; color:var(--text); }
.tool-body.open { display:block; }
.tool-body pre { margin:0; background:transparent; border:none; padding:0; }
/* 票 VSC-2B：diff 只读块（对齐桌面端 diffBlock：@@ 头 / +绿 / -红 / 上下文灰） */
.diff-block { margin:4px 10px 6px; border:1px solid var(--border); border-radius:6px; overflow:hidden; font-family:var(--mono, monospace); font-size:12px; line-height:1.45; background:var(--bg3); }
.diff-block .df { padding:2px 10px; color:var(--text2); background:var(--bg2); font-weight:600; }
.diff-block .dl { padding:1px 10px; white-space:pre-wrap; word-break:break-all; color:var(--text); }
.diff-block .dl.add { background:rgba(126,231,135,0.08); color:var(--green); }
.diff-block .dl.del { background:rgba(244,135,113,0.08); color:var(--del); }
.diff-block .dl.ctx { color:var(--text2); }
/* === 票 VSC-2B：审批卡（approval.request 唯一卡；执行前无 diff，展示 tool_name+arguments）=== */
.approval-card { margin:6px 0; padding:8px 12px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); }
.approval-card .approval-title { font-weight:600; color:var(--text); font-size:12px; display:flex; align-items:center; gap:6px; }
.approval-card .approval-args { margin:6px 0 2px; font-size:12px; color:var(--text2); word-break:break-all; line-height:1.6; }
.approval-card .diff-actions { display:flex; gap:6px; margin-top:6px; }
.approval-card button { border:1px solid var(--border); border-radius:6px; padding:3px 10px; cursor:pointer; background:var(--bg); font-size:12px; color:var(--text); }
.approval-card .approve { background:var(--str); color:#fff; border-color:var(--str); }
.approval-card .reject:hover { border-color:var(--del); color:var(--del); }
.approval-card.timeout { opacity:0.6; }
.approval-card .approval-timedout { font-size:12px; color:var(--text2); }
/* === VSC-2B：会话栏（New chat 按钮 + 会话下拉）=== */
#sessbar { position:relative; display:flex; align-items:center; gap:6px; padding:4px 10px; border-bottom:1px solid var(--border); background:var(--bg2); }
#sessbar button { border:1px solid var(--border); border-radius:6px; padding:2px 8px; cursor:pointer; background:var(--bg); font-size:12px; color:var(--text); }
#sessbar button:hover { background:var(--bg3); }
#sessbar .sess-current { font-size:12px; color:var(--text2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; }
#sess-dropdown { display:none; position:absolute; top:32px; left:10px; right:10px; z-index:50; background:var(--bg); border:1px solid var(--border); border-radius:8px; box-shadow:0 6px 20px rgba(0,0,0,0.12); max-height:240px; overflow-y:auto; }
#sess-dropdown.show { display:block; }
.sess-item { padding:6px 10px; cursor:pointer; font-size:12px; color:var(--text); border-bottom:1px solid var(--border); }
.sess-item:hover { background:var(--bg3); }
.sess-item.active { background:var(--bg3); font-weight:600; }
.sess-item .sess-meta { font-size:11px; color:var(--text2); }
/* === VSC-2D：台账折叠区 === */
#ledger { border-top:1px solid var(--border); background:var(--bg2); }
#ledger-head { padding:6px 10px; font-size:11px; font-weight:600; color:var(--text2); cursor:pointer; user-select:none; display:flex; align-items:center; gap:6px; }
#ledger-body { display:none; padding:2px 10px 8px; max-height:160px; overflow-y:auto; }
#ledger.open #ledger-body { display:block; }
#ledger-body .lg-item { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text); padding:2px 0; }
#ledger-body .lg-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
#ledger-body .lg-dot.pending { background:var(--border); }
#ledger-body .lg-dot.in_progress { background:#e8913a; }
#ledger-body .lg-dot.done { background:var(--green); }
#ledger-body .lg-title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
</head>
<body>
<div id="sessbar">
  <button id="new-chat" title="New chat">+</button>
  <span class="sess-current" id="sess-current">new session</span>
  <button id="sess-toggle" title="Sessions">☰</button>
  <div id="sess-dropdown"></div>
</div>
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
<div id="inputbar"><input id="input" placeholder="Ask a follow-up…"><button id="send">Send</button><button id="stop" title="Stop" hidden>■</button></div>
<div id="ledger">
  <div id="ledger-head">Ledger<span id="ledger-count"></span></div>
  <div id="ledger-body"></div>
</div>
<script nonce="${nonce}" src="${markedUri}"></script>
<script nonce="${nonce}" src="${purifyUri}"></script>
<script nonce="${nonce}" src="${highlightUri}"></script>
<script nonce="${nonce}" src="${mdRenderUri}"></script>
<script nonce="${nonce}" src="${partsUri}"></script>
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
