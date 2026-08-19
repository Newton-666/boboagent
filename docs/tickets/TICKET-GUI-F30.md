# 票 GUI-F30：桌面端关闭后 gateway 不刷新（Cmd+Q 后旧后端残留，重开不加载新代码）

分支 `feat/ticket-gui-f30-gw-refresh`，自最新 main（`3f743eac`）切出。
回滚标签 `rollback/pre-gui-f30` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（2026-08-19 owner 反馈）

**现象**：Cmd+Q 关闭桌面端 → 重开窗口 → **后端（gateway）仍是旧进程**，
不加载新代码。owner 操作逻辑（终端关闭或 Cmd+Q）与大多数用户一致——
"关掉再打开，后端也应该刷新"。

**现状（Kimi 代码取证）**：
- 桌面端启动时 `probeSocket` 探测活跃 socket（main.cjs:104）→ 有则**复用
  不 spawn**（105-110：`backendProcess = null`）；
- 窗口关闭 → `stopBackend()`（main.cjs:228-250）——但**只杀
  `backendProcess`（自己 spawn 的）**；复用外部后端时 `backendProcess`
  为 null（注释 245-246 明说"天然杀不到外部进程"）；
- 结果：**复用场景下 Cmd+Q 杀不掉 gateway** → 旧进程永远活着 →
  下次打开又复用 → **代码更新永不生效**（COST-6 教训实锤：21:14 提交
  22:03 收编，gateway 20:25 旧进程跑到 22:18 才被手动重启，期间 bobo
  施工连续 400 误判"没修好"）。

**Owner 诉求（定调）**：关掉再打开窗口时，**后端同步刷新**（加载最新代码）。

## 施工项

### 1. 核心：窗口关闭时杀掉 gateway + 下次打开重新 spawn

- `stopBackend()` 扩展：**无论是否自己 spawn**，都杀掉占用
  GW_SOCK_PATH 的进程（复用场景也能杀到外部 gateway）；
- 下次启动：**不再无条件复用**——探测到活跃 socket 时判断是否"本窗口
  之前遗留"（或简单方案：**每次启动都清理旧 socket + 重新 spawn**）；
- 目标行为：Cmd+Q → gateway 退出 → 重开窗口 → 新 gateway 加载最新代码。

### 2. 会话持久化确认（不丢历史）

- gateway 有磁盘持久化（save_session_to_disk）——杀进程不丢已落盘的
  会话历史；
- **进行中任务**（未完成的工具调用/回合）会中断——验收时确认提示
  或可接受（代码更新场景下用户预期如此）。

### 3. 方案取舍（施工时按 owner 定调选）

- **方案 C（推荐）**：Cmd+Q 必杀 gateway；每次启动清理旧 socket 重新
  spawn。简单、行为可预期（"关=刷新"）；
- **方案 B（备选）**：版本感知复用——gateway 心跳带代码 hash，桌面端
  对比，不一致才重启。不打断正常使用，但实现复杂；
- 施工定案需写清理由（owner 已倾向"关掉=刷新"的操作直觉）。

### 4. 回归保障

- 全量 pytest 零失败（基线 2797 passed / 2 skipped / 1 xpassed；
  cost1b 分支名环境失败为既有已知项）；
- 桌面端 e2e（gateway-socket 测试）：复用/杀进程/重连路径全过；
- **手工验证**：改一处 core/ 代码 → Cmd+Q → 重开 → 确认新代码生效
  （验证"刷新"闭环）。

## 验收标准（终审逐条复跑）

1. Cmd+Q 关闭窗口 → gateway 进程退出（ps 确认无 bobo_tui_gateway.entry）；
2. 重开窗口 → 新 gateway 启动 → **加载最新代码**（改 core/ 后实测生效）；
3. 会话历史不丢（重开后 session 列表完整）；
4. 全量 pytest 零失败 + 桌面端 e2e 全过；
5. 收工报告落 `library/agent开发/TICKET-GUI-F30完成报告.md`
   （md5/git 实况/测试原话/手工验证步骤与结果）。

## 风险自查点

- **杀外部 gateway 的副作用**：若用户手动起了 gateway（TUI 用），桌面端
  Cmd+Q 杀掉它会影响 TUI——需确认杀的是"桌面端自己 spawn 的"还是"任何
  占用 socket 的"（owner 场景：TUI 与桌面端是否共用 gateway？若共用，
  桌面端 Cmd+Q 杀 gateway 会断 TUI 连接——需权衡）；
- **反复重启成本**：每次打开重 spawn，启动多等几秒（可接受）；
- **进行中任务**：杀进程中断未完成回合（代码更新场景可预期）；
- **与 SAFETY-1 冲突**：stopBackend 的 backendStopRequested 防幽灵复活
  逻辑需保留（避免杀完又被自动重启）；
- **TEL-8 守卫**：main.cjs 改动需特批登记 GUI-F30 标记；
- **write_obsidian 陷阱**：报告落 `library/agent开发/`（已错 7 次的教训）。

## 已完成取证（Kimi 调查结论，施工不必重复）

- 复用逻辑：main.cjs:104-110（probeSocket → 复用不 spawn → backendProcess=null）；
- 关闭逻辑：main.cjs:228-250（stopBackend 只杀自 spawn，注释 245-246 明说
  杀不到外部）；
- 崩溃/陈旧教训：PROGRESS"收编后必须重启 gateway"（2026-08-19，COST-6
  事故：旧进程 20:25 跑新代码 21:14 提交未加载 → 连续 400 误判）；
- 会话持久化：save_session_to_disk 已存在（gateway 落盘）；
- 基线 pytest：2797 passed / 2 skipped / 1 xpassed；cost1b 已知项除外。
