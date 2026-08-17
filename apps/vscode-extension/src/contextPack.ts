/**
 * contextPack.ts — assemble the "selected code" context bundle sent to bobo.
 *
 * TICKET-VSC-1: file relative path + language id + selected snippet + start/end
 * line numbers + current-file diagnostics (error/warning summary).
 *
 * Pure logic — unit-testable.
 */

export type DiagSeverity = 'error' | 'warning' | 'info' | 'hint';

export interface DiagnosticItem {
  severity: DiagSeverity;
  message: string;
  line: number; // 1-based
}

export interface SelectionContext {
  /** Relative path from the workspace root (or absolute when no workspace). */
  filePath: string;
  languageId: string;
  selectedText: string;
  /** 1-based, inclusive. */
  startLine: number;
  endLine: number;
  diagnostics: DiagnosticItem[];
  /** Workspace root, when available. */
  workspaceRoot?: string;
}

/** Build the human-readable context block. */
export function buildContextBlock(ctx: SelectionContext): string {
  const lines: string[] = [];
  lines.push(`File: ${ctx.filePath} (${ctx.languageId || 'plaintext'})`);
  lines.push(`Lines: ${ctx.startLine}-${ctx.endLine}`);
  if (ctx.workspaceRoot) lines.push(`Project root: ${ctx.workspaceRoot}`);
  if (ctx.diagnostics && ctx.diagnostics.length > 0) {
    lines.push('Diagnostics:');
    for (const d of ctx.diagnostics) {
      lines.push(`- [${d.severity}] line ${d.line}: ${d.message}`);
    }
  }
  lines.push('```' + (ctx.languageId || ''));
  lines.push(ctx.selectedText);
  lines.push('```');
  return lines.join('\n');
}

/** Short single-line label (used in the chat header / session title). */
export function buildContextLabel(ctx: SelectionContext): string {
  const seg = ctx.filePath.split(/[\\/]/).pop() || ctx.filePath;
  return `${seg}:${ctx.startLine}-${ctx.endLine}`;
}

/** Default question when only the snippet is selected. */
export const DEFAULT_QUESTION = 'Explain this code.';

/** Assemble the final user message: context block + question. */
export function buildUserMessage(ctx: SelectionContext, question?: string): string {
  const q = (question && question.trim()) ? question.trim() : DEFAULT_QUESTION;
  return `${buildContextBlock(ctx)}\n\n${q}`;
}

/** Extract diagnostics from a vscode Diagnostic[]-like array (testable shape). */
export function extractDiagnostics(
  items: Array<{ severity: number | string; message: string; range: { start: { line: number } } }>,
  severityNames: Record<number, DiagSeverity> = { 0: 'error', 1: 'warning', 2: 'info', 3: 'hint' },
): DiagnosticItem[] {
  const out: DiagnosticItem[] = [];
  for (const it of items) {
    const sev = typeof it.severity === 'string' ? (it.severity as DiagSeverity) : severityNames[it.severity as number];
    if (sev !== 'error' && sev !== 'warning') continue; // only error/warning go in
    out.push({ severity: sev, message: it.message, line: it.range.start.line + 1 });
  }
  return out;
}
