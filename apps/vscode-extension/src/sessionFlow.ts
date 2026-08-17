/**
 * sessionFlow.ts — TICKET-VSC-1B pure flow logic (unit-testable).
 *
 * vscode-free helpers extracted from extension.ts so the two bug fixes and the
 * selection preview can be covered by node:test without mocking the VS Code API:
 *
 *   1. applySessionResult — session.create 成功时 sessionId 无条件落 state，
 *      面板存在才补 setSession（修 Bug 2：面板未打开时 sid 不再被静默丢弃）。
 *   2. resolveAskGate — askWithContext 的报错分支拆分：
 *      socket 未连上 vs 已连但 sessionId 未就绪（不再报假 "not connected"）。
 *   3. buildSelectionPayload — 选区预览负载：非空选区才产出，text 截断到 500。
 */

export interface SessionState {
  sessionId: string | null;
}

/**
 * Apply a session.create result. Returns the sid (or null when absent).
 * 无 panel（面板未打开）时 sessionId 仍保存；有 panel 时回调其 setSession。
 */
export function applySessionResult(
  state: SessionState,
  sid: string | null | undefined,
  setPanelSession: ((sid: string) => void) | null,
): string | null {
  if (!sid) return null;
  state.sessionId = sid;
  if (setPanelSession) setPanelSession(sid);
  return sid;
}

export type AskGate =
  | { kind: 'ok' }
  | { kind: 'not_connected' }   // socket 未连上（或从未建立）
  | { kind: 'connecting' };     // 已连接但 sessionId 未就绪

/** 决定 ask 入口的报错分支（纯判定，方便单测）。 */
export function resolveAskGate(clientConnected: boolean, sessionId: string | null): AskGate {
  if (!clientConnected) return { kind: 'not_connected' };
  if (!sessionId) return { kind: 'connecting' };
  return { kind: 'ok' };
}

export interface SelectionPayload {
  filePath: string;
  startLine: number; // 1-based, inclusive
  endLine: number;
  text: string;      // 截断后 ≤500 字符
}

/**
 * 组装"当前选中"预览负载：空选区/空文本 → null（不发）；text 截断到 maxLen。
 * 与 Ask bobo 发送的 SelectionContext 同源字段（filePath/startLine/endLine/text）。
 */
export function buildSelectionPayload(
  filePath: string,
  startLine: number,
  endLine: number,
  text: string,
  maxLen = 500,
): SelectionPayload | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return {
    filePath,
    startLine,
    endLine,
    text: trimmed.length > maxLen ? trimmed.slice(0, maxLen) : trimmed,
  };
}

// ── TICKET-VSC-2B：会话切换状态机（纯判定）──

export type SwitchPlan =
  | { kind: 'same' }            // 目标就是当前会话，无动作
  | { kind: 'switch'; sid: string } // 需 resume + 渲染历史 + 清空视图
  | { kind: 'missing' };        // 列表里找不到目标（防御，不发请求）

/** 会话切换决策：目标=当前 → same；目标在列表 → switch；否则 missing。 */
export function planSwitchSession(
  currentSid: string | null,
  targetSid: string,
  knownIds: string[],
): SwitchPlan {
  if (currentSid === targetSid) return { kind: 'same' };
  if (!knownIds.includes(targetSid)) return { kind: 'missing' };
  return { kind: 'switch', sid: targetSid };
}

/** New chat 决策：无 sessionId 时必须先 session.create。 */
export function needsSessionCreate(sessionId: string | null): boolean {
  return !sessionId;
}

/** 会话列表按 started_at 倒序（新→旧），置顶 pinned 优先。 */
export function sortSessions(
  sessions: { id: string; started_at?: number; pinned?: boolean }[],
): { id: string; started_at?: number; pinned?: boolean }[] {
  return [...sessions].sort((a, b) => {
    if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
    return (b.started_at || 0) - (a.started_at || 0);
  });
}
