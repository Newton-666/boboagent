/**
 * explain.ts — Explain mode prompt prefix (TICKET-VSC-1 learning mode).
 *
 * Design: explain is a prompt prefix only — the reasoning model is untouched
 * (owner red line: capability never degraded). Answer style switches between
 * "direct answer" and "teach-first" (concepts / why / further reading),
 * Chinese explanations, code comments stay in the original language.
 *
 * Pure logic — unit-testable.
 */

export const EXPLAIN_PREFIX = `You are in EXPLAIN mode — teach, do not just answer.
Explain the concept first (what it is, in plain words), then why this code is written this way,
then walk through the selected code step by step. Give further-reading pointers at the end.
Explain in Chinese; keep any code snippets and comments in their original language.`;

export const DIRECT_PREFIX = `Answer the question directly and concisely.`;

/** Build the prompt body: system-style prefix + user context message. */
export function buildPrompt(userMessage: string, explain: boolean): string {
  const prefix = explain ? EXPLAIN_PREFIX : DIRECT_PREFIX;
  return `${prefix}\n\n---\n\n${userMessage}`;
}

/** True when the user message already carries the explain directive. */
export function hasExplainDirective(text: string): boolean {
  return text.includes('EXPLAIN mode') || /请解释|解释一下|为什么.*这么写|讲一讲/i.test(text);
}
