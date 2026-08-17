/**
 * extension.ts — TICKET-VSC-1 entry point.
 *
 * Flow (Ask bobo):
 *   1. discover socket path (setting > env > tmpdir scan)
 *   2. if none: human-friendly "start bobo first" message
 *   3. first-time pairing confirmation (local socket, one-shot)
 *   4. connect (SocketClient, auto-reconnect w/ exponential backoff)
 *   5. session.create -> bind ChatPanel to sid
 *   6. build context pack from the editor selection -> prompt.submit
 *   7. stream message.delta into the webview; finalize on message.complete
 *
 * Zero-interference: this extension is a pure client — no gateway/core/desktop
 * changes, ever.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { SocketClient } from './socketClient';
import { candidateSocketPaths, socketExists } from './discover';
import { ChatPanel } from './chatPanel';
import { buildUserMessage, SelectionContext, extractDiagnostics } from './contextPack';
import { buildPrompt } from './explain';
import { splitThinking } from './markdown';
import { applySessionResult, resolveAskGate, buildSelectionPayload } from './sessionFlow';

const PAIRING_KEY = 'bobo.paired.v1';
const PAIRING_MSG = 'bobo: first-time pairing — allow this VS Code window to talk to the local bobo gateway?';

export function activate(ctx: vscode.ExtensionContext): void {
  const state: {
    client: SocketClient | null;
    panel: ChatPanel | null;
    sessionId: string | null;
  } = { client: null, panel: null, sessionId: null };

  // ── webview provider (sidebar view container) ──
  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider('boboChat', {
      resolveWebviewView(view) {
        const panel = new ChatPanel(ctx, view);
        state.panel = panel;
        if (state.sessionId) panel.setSession(state.sessionId);
        panel.onPairingConfirmed(() => {
          // paired: start the actual socket session
          ctx.workspaceState.update(PAIRING_KEY, true);
          ensureConnected(state, ctx);
        });
        if (state.client && state.client.connected) panel.setExplain(panel.explain);
      },
    }),
  );

  // ── commands ──
  ctx.subscriptions.push(
    vscode.commands.registerCommand('bobo.askSelection', async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showInformationMessage('bobo: open a file and select some code first.');
        return;
      }
      const selection = editor.selection;
      if (selection.isEmpty) {
        vscode.window.showInformationMessage('bobo: select a snippet of code, then run Ask bobo.');
        return;
      }
      const doc = editor.document;
      const selectedText = doc.getText(selection);
      const relPath = toRelativePath(doc.uri, vscode.workspace.getWorkspaceFolder(doc.uri)?.uri);
      const diags = extractDiagnostics(
        vscode.languages.getDiagnostics(doc.uri).map((d) => ({
          severity: d.severity as number,
          message: d.message,
          range: { start: { line: d.range.start.line } },
        })),
      );
      const wsRoot = vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath;
      const selCtx: SelectionContext = {
        filePath: relPath || doc.uri.fsPath,
        languageId: doc.languageId,
        selectedText,
        startLine: selection.start.line + 1,
        endLine: selection.end.line + 1,
        diagnostics: diags,
        workspaceRoot: wsRoot,
      };

      // socket discovery + pairing gate
      const sock = pickSocket(ctx);
      if (!sock) {
        vscode.window.showInformationMessage(
          'bobo: no running bobo gateway found. Start it first — run `bobo` in a terminal (TUI) or launch the bobo desktop app.',
        );
        return;
      }
      const paired = ctx.workspaceState.get<boolean>(PAIRING_KEY, false);
      if (!paired && state.panel) {
        state.panel.askPairing();
        // remember pending context; proceed after Allow
        state.panel.onPairingConfirmed(() => {
          ensureConnected(state, ctx);
          void askWithContext(state, ctx, selCtx);
        });
        return;
      }
      if (!state.client) ensureConnected(state, ctx);
      await waitConnected(state);
      await askWithContext(state, ctx, selCtx);
    }),
  );

  ctx.subscriptions.push(
    vscode.commands.registerCommand('bobo.toggleExplain', () => {
      if (!state.panel) { vscode.window.showInformationMessage('bobo: open the bobo chat view first.'); return; }
      state.panel.setExplain(!state.panel.explain);
    }),
  );

  ctx.subscriptions.push(
    vscode.commands.registerCommand('bobo.setExplain', (on: boolean) => {
      if (state.panel) state.panel.setExplain(!!on);
    }),
  );

  ctx.subscriptions.push(
    vscode.commands.registerCommand('bobo.submitQuestion', async (arg: { text?: string }) => {
      const text = arg && arg.text ? arg.text : '';
      if (!text || !state.client || !state.sessionId) return;
      try {
        const explain = state.panel ? state.panel.explain : false;
        await state.client.send('prompt.submit', {
          session_id: state.sessionId,
          text: buildPrompt(text, explain),
        });
      } catch (e) {
        vscode.window.showErrorMessage(`bobo: ${(e as Error).message}`);
      }
    }),
  );

  // ── TICKET-VSC-1B：选中代码实时预览（owner 需求最小版）──
  // 非空选区才发；300ms 防抖（多次 selection 事件只发最后一次，防刷屏）；
  // text 截断 500 字符；无 panel（面板未开）时丢弃——面板后开不补历史选区（最小版）。
  let selectionTimer: NodeJS.Timeout | null = null;
  ctx.subscriptions.push(
    vscode.window.onDidChangeTextEditorSelection((ev) => {
      if (selectionTimer) clearTimeout(selectionTimer);
      selectionTimer = setTimeout(() => {
        const editor = ev.textEditor;
        const panel = state.panel;
        if (!panel) return;
        const sel = editor.selection;
        if (!sel || sel.isEmpty) {
          panel.setSelection(null);
          return;
        }
        const doc = editor.document;
        const relPath = toRelativePath(doc.uri, vscode.workspace.getWorkspaceFolder(doc.uri)?.uri);
        const payload = buildSelectionPayload(
          relPath || doc.uri.fsPath,
          sel.start.line + 1,
          sel.end.line + 1,
          doc.getText(sel),
        );
        panel.setSelection(payload);
      }, 300);
    }),
  );

  // ── helpers ──

  function pickSocket(ctx2: vscode.ExtensionContext): string | null {
    const setting = vscode.workspace.getConfiguration('bobo').get<string>('socketPath', '');
    const candidates = candidateSocketPaths(setting);
    for (const c of candidates) {
      if (socketExists(c)) return c;
    }
    return candidates.length ? candidates[0] : null;
  }

  function ensureConnected(st: typeof state, ctx2: vscode.ExtensionContext): void {
    if (st.client) return;
    const sock = pickSocket(ctx2);
    if (!sock) return;
    const client = new SocketClient({
      onConnect: () => {
        // TICKET-VSC-1B（Bug 2 修复）：sessionId 无条件落 state——
        // 面板未打开时不再被静默丢弃；面板已开/后开都通过 setSession 绑定。
        void client.send('session.create', {}).then((r: any) => {
          const sid = r && r.session_id;
          applySessionResult(
            st,
            sid,
            st.panel ? (s) => st.panel && st.panel.setSession(s) : null,
          );
        }).catch((e: Error) => {
          // 不静默吞错：session.create 失败留 log（票风险自查点）
          console.error('bobo: session.create failed', e && e.message);
        });
      },
      onDisconnect: () => {
        if (st.panel) st.panel.handleEvent({ type: 'gateway.error' } as any);
      },
      onEvent: (ev) => {
        const p = (ev.params || {}) as Record<string, unknown>;
        const t = String(p.type || '');
        // gateway nests event fields under params.payload (verified live):
        //   {"type":"message.delta","payload":{"text":"...","session_id":"..."},"session_id":"..."}
        const payload = (p.payload || {}) as Record<string, unknown>;
        const merged: Record<string, unknown> = { ...p, ...payload };
        if (t === 'message.delta' && typeof merged.text === 'string' && st.panel) {
          st.panel.handleDelta(String(merged.session_id || ''), merged.text);
        } else if (t === 'message.complete' && st.panel) {
          const final = String(merged.final_text || '');
          const { body } = splitThinking(final);
          st.panel.handleComplete(String(merged.session_id || ''), body || final);
        } else if (st.panel) {
          const { type: _t, ...rest } = merged;
          st.panel.handleEvent({ type: t, ...rest } as any);
        }
      },
    });
    st.client = client;
    client.connect(sock);
  }

  function waitConnected(st: typeof state): Promise<void> {
    if (st.client && st.client.connected) return Promise.resolve();
    return new Promise((resolve) => {
      const t0 = Date.now();
      const iv = setInterval(() => {
        if (st.client && st.client.connected) { clearInterval(iv); resolve(); }
        else if (Date.now() - t0 > 5000) { clearInterval(iv); resolve(); }
      }, 100);
    });
  }

  async function askWithContext(st: typeof state, ctx2: vscode.ExtensionContext, selCtx: SelectionContext): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    // TICKET-VSC-1B：报错分支拆分——socket 未连上 vs 已连但 sessionId 未就绪
    const gate = resolveAskGate(!!(st.client && st.client.connected), st.sessionId);
    if (gate.kind === 'not_connected') {
      vscode.window.showErrorMessage('bobo: not connected to the bobo gateway.');
      return;
    }
    if (gate.kind === 'connecting') {
      // 已连接但 session.create 尚未完成：提示稍等并自动重试一次
      vscode.window.showErrorMessage('bobo: connecting, try again in a moment.');
      const client = st.client;
      if (client) {
        try {
          const r: any = await client.send('session.create', {});
          const sid = r && r.session_id;
          applySessionResult(
            st,
            sid,
            st.panel ? (s) => st.panel && st.panel.setSession(s) : null,
          );
        } catch (e) {
          console.error('bobo: session.create retry failed', (e as Error).message);
          return;
        }
      }
      if (!st.sessionId) return; // 重试仍未就绪，放弃（错误已提示）
    }
    // ensure a fresh session per ask (clean context), but keep the follow-up sid
    const userMsg = buildUserMessage(selCtx);
    const explain = st.panel ? st.panel.explain : false;
    try {
      await st.client!.send('prompt.submit', {
        session_id: st.sessionId,
        text: buildPrompt(userMsg, explain),
        project_root: selCtx.workspaceRoot || undefined,
      });
    } catch (e) {
      vscode.window.showErrorMessage(`bobo: ${(e as Error).message}`);
    }
  }

  if (vscode.window.activeTextEditor) {
    // eager: nothing — we connect lazily on first Ask
  }
}

export function deactivate(): void {
  /* SocketClient closes itself on process exit; nothing to do. */
}

function toRelativePath(uri: vscode.Uri, wsUri?: vscode.Uri): string | null {
  if (!wsUri) return null;
  const rel = path.relative(wsUri.fsPath, uri.fsPath);
  if (rel.startsWith('..')) return null;
  return rel.split(path.sep).join('/');
}
