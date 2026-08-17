/**
 * discover.ts — locate the running bobo gateway unix socket.
 *
 * Priority (TICKET-VSC-1):
 *   1. explicit path (VS Code setting bobo.socketPath, injected by extension.ts)
 *   2. BOBO_GW_SOCKET env var
 *   3. scan os.tmpdir() for `bobo-gw-<pid>-<ts>.sock` (the ui-tui naming
 *      convention, verified in ui-tui/src/gatewayClient.ts), newest mtime first.
 *
 * Pure logic — no vscode import, unit-testable.
 */

import * as os from 'os';
import * as fs from 'fs';
import * as path from 'path';

/** Candidate socket paths, highest priority first. */
export function candidateSocketPaths(explicit?: string, env = process.env): string[] {
  const out: string[] = [];
  if (explicit && explicit.trim()) out.push(explicit.trim());
  const fromEnv = env.BOBO_GW_SOCKET;
  if (fromEnv && fromEnv.trim()) out.push(fromEnv.trim());
  for (const p of scanTmpSockets()) out.push(p);
  // de-dup, keep first occurrence
  return [...new Set(out)];
}

/** Scan tmpdir for bobo-gw-*.sock, newest mtime first. */
export function scanTmpSockets(): string[] {
  const dir = os.tmpdir();
  let entries: fs.Dirent[] = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const socks = entries
    .filter((e) => e.isSocket() || e.isFile())
    .filter((e) => /^bobo-gw-.*\.sock$/.test(e.name))
    .map((e) => {
      const full = path.join(dir, e.name);
      let mtime = 0;
      try {
        mtime = fs.statSync(full).mtimeMs;
      } catch {
        /* stat race — keep 0 */
      }
      return { full, mtime };
    })
    .sort((a, b) => b.mtime - a.mtime)
    .map((x) => x.full);
  return socks;
}

/** True when a socket path exists and is connectable (best-effort). */
export function socketExists(p: string): boolean {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}
