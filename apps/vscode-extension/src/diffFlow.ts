/**
 * diffFlow.ts — TICKET-VSC-2C diff 协作纯逻辑（vscode-free，可单测）。
 *
 * 数据源（实探 core/engine_adapter.py）：
 *   tool.start    {tool_id, name, arguments, context, session_id}
 *   tool.complete {tool_id, name, arguments, duration, result_text, inline_diff, error, session_id}
 * 其中 arguments 含工具入参（edit_file 有 file_path；file_operation 有 path/content）。
 *
 * 流程：写文件工具 start → 取目标文件快照（内存）；complete 带 inline_diff →
 * 扩展侧开 vscode.diff（快照 vs 文件）；面板出 Accept/Reject 卡。
 * Reject = 快照逐字节写回（fs 直写，不碰编辑器 dirty 缓冲）。
 */

/** 写文件工具白名单（arguments 里带明确文件路径的）。 */
export const WRITE_TOOLS = new Set(['edit_file', 'file_operation']);

/** 从工具 arguments 提取目标文件路径（相对/绝对）；无明确路径返回 null。 */
export function extractTargetPath(name: string, args: Record<string, unknown> | undefined | null): string | null {
  if (!WRITE_TOOLS.has(name) || !args) return null;
  // edit_file → file_path；file_operation → path
  const p = args.file_path ?? args.path;
  if (typeof p === 'string' && p.trim()) return p.trim();
  return null;
}

/** 判断该 tool.complete 事件是否带 diff 数据（inline_diff 非空）。 */
export function hasInlineDiff(ev: { inline_diff?: unknown }): boolean {
  return typeof ev.inline_diff === 'string' && ev.inline_diff.trim().length > 0;
}

export interface SnapshotEntry {
  /** 快照时的绝对路径（若 arguments 给的是相对路径，由调用方 resolve 后传入）。 */
  absPath: string;
  /** 逐字节原文。 */
  content: string;
  /** 快照时文件是否存在（新建场景 false；Reject 时删除文件还原"不存在"）。 */
  existed: boolean;
  /** 快照时间（epoch ms）。 */
  takenAt: number;
  /** 是否来自 edit_file（默认 file_operation 也算写文件）。 */
  toolName: string;
}

/** 内存快照表：absPath → SnapshotEntry。纯数据，由调用方（extension）持有。 */
export class SnapshotStore {
  private map = new Map<string, SnapshotEntry>();

  set(entry: SnapshotEntry): void {
    this.map.set(entry.absPath, entry);
  }

  get(absPath: string): SnapshotEntry | undefined {
    return this.map.get(absPath);
  }

  has(absPath: string): boolean {
    return this.map.has(absPath);
  }

  delete(absPath: string): void {
    this.map.delete(absPath);
  }

  clear(): void {
    this.map.clear();
  }

  size(): number {
    return this.map.size;
  }
}

/**
 * Reject 写回：把快照内容逐字节写回文件（fs 直写，不碰编辑器 dirty 缓冲）。
 * 返回写入的字节数；文件不存在时创建。
 * 纯函数形态（fs 注入）以便单测：默认用 require('fs')。
 */
export function restoreSnapshot(
  entry: SnapshotEntry,
  fs: {
    writeFileSync: (p: string, data: string | Buffer, enc?: BufferEncoding) => void;
    unlinkSync?: (p: string) => void;
    mkdirSync?: (p: string, opts?: { recursive: boolean }) => void;
    dirname?: (p: string) => string;
  } = require('fs'),
  path: { dirname: (p: string) => string } = require('path'),
): number {
  if (!entry.existed) {
    // 新建文件被 Reject：删除还原"不存在"（文件已不存在也视为达成）
    if (fs.unlinkSync) { try { fs.unlinkSync(entry.absPath); } catch { /* 已不存在 */ } }
    return 0;
  }
  const dir = path.dirname(entry.absPath);
  if (fs.mkdirSync) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(entry.absPath, entry.content, 'utf8');
  return Buffer.byteLength(entry.content, 'utf8');
}

/** 从 tool.start/tool.complete 的 arguments 提取快照骨架（内容由调用方现读现填）。 */
export function snapshotEntryFromTool(
  name: string,
  args: Record<string, unknown> | undefined | null,
  absPathResolver: (p: string) => string,
  nowMs: number,
  existed = true,
): SnapshotEntry | null {
  const target = extractTargetPath(name, args);
  if (!target) return null;
  return {
    absPath: absPathResolver(target),
    content: '',
    existed,
    takenAt: nowMs,
    toolName: name,
  };
}
