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
import { SnapshotStore, extractTargetPath, hasInlineDiff, WRITE_TOOLS } from './diffFlow';
import { DiffSnapshotProvider } from './diffProvider';
import { resolveProjectRoot } from './projectRoot';

const PAIRING_KEY = 'bobo.paired.v1';
const PAIRING_MSG = 'bobo: first-time pairing — allow this VS Code window to talk to the local bobo gateway?';

export function activate(ctx: vscode.ExtensionContext): void {
  const state: {
    client: SocketClient | null;
    panel: ChatPanel | null;
    sessionId: string | null;
    // 票 VSC-2B：审批卡串行令牌——新卡到来递增，旧卡的 120s 超时计时器据此作废
    approvalToken: number;
  } = { client: null, panel: null, sessionId: null, approvalToken: 0 };

  // ── TICKET-VSC-2C：diff 快照（内存）+ 只读文档提供者 ──
  const snapshots = new SnapshotStore();
  const diffProvider = new DiffSnapshotProvider(snapshots);
  ctx.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider('bobo-diff', diffProvider),
  );

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
        // ── TICKET-VSC-2B/C：面板新协议回调 ──
        panel.onNewChat(() => { void newChat(state, ctx); });
        panel.onSwitchSession((sid) => { void switchSession(state, ctx, sid); });
        panel.onRequestSessions(() => { void refreshSessionList(state, ctx); });
        // 票 VSC-2B：审批卡 Accept/Reject → approval.respond（allow/deny）。
        // 原 VSC-2 的 diffDecisionCb（事后 Reject 快照写回）随审批闸门废弃——
        // Reject 语义已前移到审批闸门（执行前），diff 展示只读。
        panel.onApprovalDecision((choice) => { void respondApproval(state, ctx, choice); });
        // 票 VSC-2B：停止按钮（点停止钮/Esc）→ session.interrupt
        panel.onStopRequested(() => { void stopCurrentRun(state, ctx); });
        if (state.client && state.client.connected) panel.setExplain(panel.explain);
        // VSC-1B 实弹修复：打开面板即连接——已配对直接连；未配对先问（否则
        // 状态永远卡 connecting、Send 因无 client 静默无效）
        if (ctx.workspaceState.get<boolean>(PAIRING_KEY, false)) {
          ensureConnected(state, ctx);
        } else {
          panel.askPairing();
        }
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
      if (!text) return;
      // VSC-1B 实弹修复：面板内发送也要走连接闸门——未连接先连 + 等待 +
      // sessionId 未就绪自动补一次 session.create，绝不静默 return
      if (!state.client) { ensureConnected(state, ctx); await waitConnected(state); }
      const gate = resolveAskGate(!!(state.client && state.client.connected), state.sessionId);
      if (gate.kind === 'not_connected') {
        vscode.window.showErrorMessage('bobo: not connected to the bobo gateway.');
        return;
      }
      if (gate.kind === 'connecting' && state.client) {
        try {
          const r: any = await state.client.send('session.create', {});
          applySessionResult(state, r && r.session_id,
            state.panel ? (s) => state.panel && state.panel.setSession(s) : null);
        } catch (e) {
          vscode.window.showErrorMessage(`bobo: ${(e as Error).message}`);
          return;
        }
      }
      if (!state.client || !state.sessionId) {
        vscode.window.showErrorMessage('bobo: connecting, try again in a moment.');
        return;
      }
      try {
        const explain = state.panel ? state.panel.explain : false;
        // VSC-1B 实弹修复：面板提问带上当前高亮选区——"解释一下这行代码"
        // 必须让 bobo 看到选中的代码块，而不是只发一句裸文本
        const selCtx = currentSelectionContext();
        const outgoing = selCtx ? buildUserMessage(selCtx, text) : text;
        // VSC-2C：project_root 与选区解耦——无条件取 workspace 根（有 workspace 就带，
        // 单文件/无 workspace 才 undefined）。此前依赖 selCtx.workspaceRoot，无选区时
        // currentSelectionContext() 返 null → project_root undefined → bobo 感知不到
        // VS Code 打开的文件夹，建文件落到后端 cwd。
        const wsRoot = resolveProjectRoot(vscode.workspace.workspaceFolders);
        await state.client.send('prompt.submit', {
          session_id: state.sessionId,
          text: buildPrompt(outgoing, explain),
          project_root: wsRoot,
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

  /** 当前编辑器的选区上下文（无编辑器/空选区 → null）。askSelection 与面板 Send 共用。 */
  function currentSelectionContext(): SelectionContext | null {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.selection.isEmpty) return null;
    const doc = editor.document;
    const relPath = toRelativePath(doc.uri, vscode.workspace.getWorkspaceFolder(doc.uri)?.uri);
    return {
      filePath: relPath || doc.uri.fsPath,
      languageId: doc.languageId,
      selectedText: doc.getText(editor.selection),
      startLine: editor.selection.start.line + 1,
      endLine: editor.selection.end.line + 1,
      diagnostics: extractDiagnostics(
        vscode.languages.getDiagnostics(doc.uri).map((d) => ({
          severity: d.severity as number,
          message: d.message,
          range: { start: { line: d.range.start.line } },
        })),
      ),
      workspaceRoot: vscode.workspace.getWorkspaceFolder(doc.uri)?.uri.fsPath,
    };
  }

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
          // 票 VSC-2B：会话创建即开写审批闸门（配对确认后的第一时间，
          // 避免首轮工具调用漏闸）。开关挂会话对象，随 session.resume 存活。
          if (sid) {
            void client.send('session.set_write_approval', { session_id: sid, on: true })
              .catch((e: Error) => console.error('bobo: set_write_approval failed', e && e.message));
          }
        }).catch((e: Error) => {
          // 不静默吞错：session.create 失败留 log（票风险自查点）
          console.error('bobo: session.create failed', e && e.message);
        });
      },
      onDisconnect: () => {
        if (st.panel) {
          st.panel.setRunning(false);
          st.panel.handleEvent({ type: 'gateway.error' } as any);
        }
      },
      onEvent: (ev) => {
        const p = (ev.params || {}) as Record<string, unknown>;
        const t = String(p.type || '');
        // gateway nests event fields under params.payload (verified live):
        //   {"type":"message.delta","payload":{"text":"...","session_id":"..."},"session_id":"..."}
        const payload = (p.payload || {}) as Record<string, unknown>;
        const merged: Record<string, unknown> = { ...p, ...payload };
        const sid = String(merged.session_id || '');
        if (t === 'message.start' && st.panel) {
          // 票 VSC-2B：回合开始 → Send 切停止钮
          st.panel.setRunning(true);
        } else if (t === 'message.delta' && typeof merged.text === 'string' && st.panel) {
          st.panel.handleDelta(sid, merged.text);
        } else if (t === 'message.complete' && st.panel) {
          // 票 VSC-2B：回合结束 → 停止钮切回 Send
          st.panel.setRunning(false);
          const final = String(merged.final_text || '');
          const { body, thinking } = splitThinking(final);
          // VSC-2B：thinking 单独推折叠块，正文照旧流式定稿
          st.panel.handleThinking(sid, thinking);
          st.panel.handleComplete(sid, body || final);
        } else if (t === 'approval.request') {
          // 票 VSC-2B：写审批闸门（reason=write_approval）——唯一审批卡。
          // 引擎天然串行（一次只跑一个工具，pending_confirm 按 sid 单槽）；
          // 扩展侧再保险：新卡到来先关旧 diff/旧卡，一次只弹一个。
          const reason = String(merged.reason || '');
          if (reason === 'write_approval' && st.panel) {
            st.approvalToken = (st.approvalToken || 0) + 1;
            const token = st.approvalToken;
            void closeBoboDiffs();
            st.panel.showApprovalCard(sid, merged);
            // 120s 超时置灰（引擎侧既有超时放弃语义，卡片同步提示"已超时"）
            setTimeout(() => {
              if (st.approvalToken === token && st.panel) st.panel.approvalTimeout(sid);
            }, 120000);
          }
        } else if (t === 'tool.start' && st.panel) {
          // VSC-2C：写文件工具 start → 目标文件快照（内存）
          captureSnapshot(st, snapshots, merged);
          st.panel.handleTool(sid, merged);
        } else if (t === 'tool.complete' && st.panel) {
          st.panel.handleTool(sid, merged);
          // 票 VSC-2B：diff 只读展示——审批已在执行前过闸门（approval.request
          // 分支），此处仅开 vscode.diff 快照对比，不再弹 Accept/Reject 审批卡
          //（防双弹；原 VSC-2 直开审批路径已移除）。
          const name = String(merged.name || '');
          if (WRITE_TOOLS.has(name) && hasInlineDiff(merged)) {
            const args = (merged.arguments || {}) as Record<string, unknown>;
            const rel = extractTargetPath(name, args);
            if (rel) {
              const abs = resolveAbsPath(rel);
              if (snapshots.has(abs)) {
                void openDiff(diffProvider, abs);
              }
            }
          }
          // VSC-2D：task_ledger 完成 → 台账折叠区（arguments.items 为条目）
          if (name === 'task_ledger') {
            const args = (merged.arguments || {}) as Record<string, unknown>;
            const items = Array.isArray(args.items)
              ? (args.items as unknown[]).filter(
                  (x): x is { id: string; title: string; status: string } =>
                    !!x && typeof (x as any).id === 'string' && typeof (x as any).title === 'string' && typeof (x as any).status === 'string',
                )
              : [];
            st.panel.setLedger(items);
          }
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

  // ── TICKET-VSC-2B/C helpers ──

  /** New chat：session.create → 绑定面板 + 清空视图。 */
  async function newChat(st: typeof state, ctx2: vscode.ExtensionContext): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    if (!st.client) return;
    try {
      const r: any = await st.client.send('session.create', {});
      applySessionResult(st, r && r.session_id, st.panel ? (s) => st.panel && st.panel.setSession(s) : null);
      if (st.panel) {
        st.panel.clearChat();
        st.panel.setSession(st.sessionId as string);
      }
      void refreshSessionList(st, ctx2);
    } catch (e) {
      vscode.window.showErrorMessage(`bobo: ${(e as Error).message}`);
    }
  }

  /** 切换会话：session.resume（实探确认既有 RPC；无 session.load）→ 渲染历史。 */
  async function switchSession(st: typeof state, ctx2: vscode.ExtensionContext, sid: string): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    if (!st.client) return;
    try {
      const r: any = await st.client.send('session.resume', { session_id: sid });
      if (r && r.resumed) {
        applySessionResult(st, r.session_id, st.panel ? (s) => st.panel && st.panel.setSession(s) : null);
        if (st.panel) {
          st.panel.clearChat();
          st.panel.setSession(r.session_id);
          st.panel.setHistory(r.messages || []);
        }
      } else if (r && r.error) {
        vscode.window.showErrorMessage(`bobo: ${r.error.message || '切换会话失败'}`);
      }
    } catch (e) {
      vscode.window.showErrorMessage(`bobo: ${(e as Error).message}`);
    }
  }

  /** 拉取会话列表并推给面板。 */
  async function refreshSessionList(st: typeof state, ctx2: vscode.ExtensionContext): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    if (!st.client || !st.panel) return;
    try {
      const r: any = await st.client.send('session.list', {});
      st.panel.setSessions(Array.isArray(r && r.sessions) ? r.sessions : []);
    } catch {
      /* 列表失败静默（面板已有当前会话可继续） */
    }
  }

  /** tool.start：写文件工具 → 读目标文件快照入内存。 */
  function captureSnapshot(st: typeof state, store: SnapshotStore, ev: Record<string, unknown>): void {
    const name = String(ev.name || '');
    if (!WRITE_TOOLS.has(name)) return;
    const args = (ev.arguments || {}) as Record<string, unknown>;
    const rel = extractTargetPath(name, args);
    if (!rel) return;
    const abs = resolveAbsPath(rel);
    let content = '';
    let existed = true;
    try {
      content = require('fs').readFileSync(abs, 'utf8');
    } catch {
      existed = false; // 新建场景：快照空串 + existed=false，Reject = 删除文件还原"不存在"
    }
    store.set({ absPath: abs, content, existed, takenAt: Date.now(), toolName: name });
  }

  /** 打开 VS Code 原生 diff（左侧只读快照 vs 右侧磁盘文件）。 */
  async function openDiff(provider: DiffSnapshotProvider, abs: string): Promise<void> {
    try {
      await vscode.commands.executeCommand(
        'vscode.diff',
        provider.snapshotUri(abs),
        vscode.Uri.file(abs),
        'bobo 改动',
      );
    } catch (e) {
      console.error('bobo: vscode.diff failed', (e as Error).message);
    }
  }

  /** 票 VSC-2B：审批卡决策 → approval.respond（allow/deny）。
   * 原 handleDiffDecision（事后 Reject 快照写回）废弃——Reject 语义已前移
   * 到审批闸门（执行前）；diff 展示只读，无决策按钮。 */
  async function respondApproval(st: typeof state, ctx2: vscode.ExtensionContext, choice: string): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    if (!st.client || !st.sessionId) return;
    try {
      await st.client.send('approval.respond', { session_id: st.sessionId, choice });
      if (st.panel) st.panel.approvalDone();
    } catch (e) {
      vscode.window.showErrorMessage(`bobo: approval.respond failed ${(e as Error).message}`);
    }
  }

  /** 票 VSC-2B：停止当前回合 → session.interrupt；状态栏 Stopped，输入区恢复可发。 */
  async function stopCurrentRun(st: typeof state, ctx2: vscode.ExtensionContext): Promise<void> {
    if (!st.client) { ensureConnected(st, ctx2); await waitConnected(st); }
    if (!st.client || !st.sessionId) return;
    try {
      await st.client.send('session.interrupt', { session_id: st.sessionId });
      if (st.panel) {
        st.panel.setRunning(false);
        st.panel.setStatus('Stopped');
      }
    } catch (e) {
      vscode.window.showErrorMessage(`bobo: session.interrupt failed ${(e as Error).message}`);
    }
  }

  /** 只关 bobo 自己的 diff tab（uri scheme=bobo-diff），不碰用户编辑器 tab。
   * 风险自查点：workbench.action.closeActiveEditor 会误关用户 tab，禁用。 */
  async function closeBoboDiffs(): Promise<void> {
    try {
      for (const ed of vscode.window.visibleTextEditors) {
        if (ed.document.uri.scheme === 'bobo-diff') {
          await vscode.commands.executeCommand('workbench.action.closeActiveEditor', ed.document.uri);
        }
      }
    } catch (e) {
      console.error('bobo: closeBoboDiffs failed', (e as Error).message);
    }
  }

  /** 相对/绝对路径 → 绝对（相对路径锚定 workspace 根）。 */
  function resolveAbsPath(p: string): string {
    if (path.isAbsolute(p)) return p;
    const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
    return ws ? path.join(ws.uri.fsPath, p) : path.resolve(p);
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
