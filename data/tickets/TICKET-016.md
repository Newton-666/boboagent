# TICKET-016: 修复审批弹窗 patchUiState ReferenceError（闪退根因）

| 属性 | 值 |
|------|-----|
| 分级 | P0 |
| 分支 | fix/ticket-016-approval-patchuistate |
| 前置 | 无 |

## 背景（故障证据链）

2026-07-31 晚 bobo TUI 两次"闪退"，监控定位到根因：

- `~/.hermes/logs/tui_gateway_crash.log` 自 7/29 起反复出现
  `unhandledRejection: ReferenceError: patchUiState is not defined`
- 22:06:11 `bobo.log` 记录用户确认审批（`approval.respond`）后，
  同一秒 crash.log 出现该 ReferenceError，5 秒后 Node 进程死亡、
  python 后端 exit 0，TUI 闪退
- Node 死亡又触发 zsh 作业表段错误（macOS .ips 报告），终端整个消失

根因代码：`ui-tui/src/app/useInputHandlers.ts`

- 第 22 行 `import { getUiState } from './uiStore.js'` — **漏了 `patchUiState`**
- 第 282 行（数字键 1-4 审批确认）和第 291 行（回车审批确认）却调用了
  `patchUiState({ status: 'running…' })`
- esbuild 打包不做类型检查，裸引用原样进入 `dist/entry.js`，
  运行时一按审批确认键就抛 ReferenceError

## 任务内容（只允许以下改动，不要顺手改无关代码）

### 1. 补 import（核心修复）

`ui-tui/src/app/useInputHandlers.ts` 第 22 行改为：

```ts
import { getUiState, patchUiState } from './uiStore.js'
```

### 2. 重新打包并同步两份产物

```bash
cd ui-tui && npm run build
cp ui-tui/dist/entry.js bobo_tui_gateway/static/entry.js
```

验证：打包后 `grep -c "patchUiState" ui-tui/dist/entry.js` 的所有引用
必须能被解析（不允许再有未定义的裸引用；可用
`python3 -c "import re;d=open('ui-tui/dist/entry.js').read();print(len(re.findall(r'(?<![A-Za-z0-9_\$])patchUiState(?![0-9])(?![A-Za-z0-9_\$])',d)))"`
检查，若输出 0 或该符号已有定义则通过）。

### 3. 加防御：unhandledRejection 兜底（防止同类潜伏 bug 再杀人）

在 `ui-tui/src/entry.tsx`（进程入口）顶部附近，确保存在
`process.on('unhandledRejection', ...)` 处理：记录到
`recordParentLifecycle`（`src/lib/parentLog.ts`）并在 TUI 底部
显示一条错误提示，**不杀进程**。

注意：先读现有入口代码，若已有该 handler 则只需确认它会
记录到 parentLog，不要重复添加。

### 4. 回归测试

- `cd ui-tui && npm run typecheck` 无错误
- `cd ui-tui && npm test` 全绿
- 仓库根目录 `pytest tests/ -q` 全绿（确认 python 侧无回归）

## 验收标准

- [ ] 1. `useInputHandlers.ts` 的 import 行包含 `patchUiState`
- [ ] 2. `npm run typecheck` 通过（这一步在修复前应该能复现报错，修复后必须通过）
- [ ] 3. `ui-tui/dist/entry.js` 与 `bobo_tui_gateway/static/entry.js` 重新打包且 md5 一致
- [ ] 4. `npm test` 全绿
- [ ] 5. `pytest tests/ -q` 全绿
- [ ] 6. 入口存在 unhandledRejection 兜底（记录日志 + UI 提示，不退出进程）
- [ ] 7. 所有改动 commit 在 `fix/ticket-016-approval-patchuistate` 分支，不碰 main，不 push
