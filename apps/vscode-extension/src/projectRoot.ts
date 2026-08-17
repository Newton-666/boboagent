// projectRoot.ts — TICKET-VSC-2C：project_root 推导（与选区解耦）。
//
// 背景：send 入口此前把 project_root 绑在选区上下文上（selCtx.workspaceRoot），
// 无选区时 currentSelectionContext() 返 null → project_root undefined → bobo 感知
// 不到 VS Code 打开的文件夹，建文件落到后端 cwd（owner 实弹：test 文件夹建文件失败）。
//
// 修复：project_root 无条件取 workspace 根（有 workspace 就带 fsPath，
// 单文件/无 workspace 才 undefined）。独立纯函数模块（无 vscode 依赖），
// 便于 node 单测直测三种分支。
export interface WorkspaceFolderLike {
  uri: { fsPath: string };
}

export function resolveProjectRoot(
  folders: readonly WorkspaceFolderLike[] | undefined,
): string | undefined {
  return folders?.[0]?.uri.fsPath;
}
