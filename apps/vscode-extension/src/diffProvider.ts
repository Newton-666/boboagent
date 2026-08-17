/**
 * diffProvider.ts — TICKET-VSC-2C 只读内存文档提供者（vscode.diff 左侧快照）。
 *
 * scheme: bobo-diff。getSnapshotUri(absPath) 生成只读 uri；
 * 内容来自 SnapshotStore（tool.start 时捕获），不落临时文件。
 */

import * as vscode from 'vscode';
import { SnapshotStore } from './diffFlow';

const SCHEME = 'bobo-diff';

export class DiffSnapshotProvider implements vscode.TextDocumentContentProvider {
  private store: SnapshotStore;
  private onDidChangeEmitter = new vscode.EventEmitter<vscode.Uri>();

  constructor(store: SnapshotStore) {
    this.store = store;
  }

  readonly onDidChange = this.onDidChangeEmitter.event;

  provideTextDocumentContent(uri: vscode.Uri): string {
    // uri 形如 bobo-diff://snapshot/<absPath>
    const absPath = uri.path;
    const entry = this.store.get(absPath);
    return entry ? entry.content : '';
  }

  /** 生成左侧快照 uri（只读；内容由 provideTextDocumentContent 现取）。 */
  snapshotUri(absPath: string): vscode.Uri {
    return vscode.Uri.parse(`${SCHEME}://snapshot${encodeURI(absPath)}`);
  }

  /** 快照更新后通知 VS Code 刷新。 */
  refresh(absPath: string): void {
    this.onDidChangeEmitter.fire(this.snapshotUri(absPath));
  }
}
