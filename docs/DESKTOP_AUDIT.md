# TICKET-D1a 全栈刨根审计报告

- 分支：feat/ticket-d1（自 main 763c376 切出）
- 审计时间：2026-08-12
- 审计范围：apps/desktop/ 四层全翻 + 实跑取证
- 审计方式：静态代码比对（renderer dist 产物 vs 现行 bobo_tui_gateway）+ 三次实跑（npm start ×2 带/不带 BOBO_GW_SOCKET、后端 stdio/socket 双模式冒烟、setup 流程冒烟）

## 结论摘要

桌面版**四层均有问题**，共 20 条。其中阻断 2、高 6、中 4、低 8。后端 JSON-RPC 方法/事件协议整体兼容（无断裂），最大断点在前端源码缺失与主进程环境变量污染。修复优先级：E1（哑火）> R1（源码）> B3/E2/E4（功能）> B1（安全闸，D-1d 范畴）。

---

## Layer 1 前端 renderer 层（apps/desktop/dist/）

### R1【阻断】renderer 源码整体缺失，只剩压缩构建产物
- 现象：apps/desktop/ 下无 src/、无 vite.config.ts、无 tsconfig.json；dist/assets/index-nE15esVH.js 为 2026-06-19 压缩产物（54 天未更新）。
- 根因：commit df8fa05（2026-06-19）"chore: remove dead Vite/React source files" 删除全部前端源码（App.tsx 439 行、gateway.ts 128 行、gateway-browser.ts 96 行、main.tsx、index.css、vite.config.ts、tsconfig.json），package.json 同步移除 vite/react/typescript 依赖。
- 证据：`git log --all --name-only -- apps/desktop/`；`git show --stat df8fa05`。
- 影响：D-1d"GUI 平齐 TUI"无源码可改；dist JS 是压缩产物无法直接维护；审计也只能基于产物反推行为。
- 修复建议：`git checkout df8fa05^ -- apps/desktop/src apps/desktop/vite.config.ts apps/desktop/tsconfig.json` 恢复源码（App.tsx/gateway.ts 等），恢复 vite 依赖后重建 dev 流程（main.cjs 已留 BOBO_DESKTOP_DEV=1 走 localhost:5173 的分支）。
- 严重度：**阻断**（D-1d 前置条件）。

### R2【高】renderer 订阅 thinking.delta，后端永不到达
- 现象：renderer 订阅 9 类事件含 thinking.delta，但该事件从未收到。
- 根因：后端把 engine 的 thinking.delta 映射为 message.delta 发射（core/engine_adapter.py:158-167 `elif event_type == "thinking.delta": emit("message.delta", ...)`），不再发 thinking.delta。
- 证据：dist JS `on("thinking.delta")` vs engine_adapter.py:158-167。
- 影响：思维流依赖 message.delta（内容一致，有兜底），功能未坏，但订阅清单与后端不一致，修复时容易踩。
- 修复建议：renderer 去掉 thinking.delta 订阅，统一 message.delta；或后端恢复发射 thinking.delta。
- 严重度：高（不阻塞，但属于协议错位）。

### R3【低】后端多个事件 renderer 未订阅
- 现象：后端发射的 notes.tree、approval.request、gateway.error、error、notes.changed、terminal.output、session.cleared、session.auto_state、session.office_state 在 renderer 无处理器，落入 console.warn("Unhandled message")。
- 证据：dist JS `on(...)` 订阅清单（gateway.ready/message.start/message.delta/message.complete/tool.start/tool.complete/status.update/thinking.delta/backend.exited）vs entry.py:330-365、engine_adapter.py emit 清单、prompts.py:189/265/288。
- 影响：笔记树（notes.tree）、闸确认（approval.request，见 B1）、会话状态指示均缺失。
- 修复建议：D-1d 按需补订阅。
- 严重度：低（功能缺失项，非崩溃）。

### R4【低】browser 模式（ws://localhost:9876）无后端配套
- 现象：renderer 在无 window.boboAPI 时连 ws://localhost:9876（dist JS `ml.connect(9876)`），但桌面版后端走 stdio（无 BOBO_GW_SOCKET 指向 9876）。
- 影响：仅影响网页调试场景，Electron 内不受影响。
- 严重度：低。

---

## Layer 2 Electron 主进程层（electron/main.cjs, preload.cjs）

### E1【阻断】spawn 后端不清除 BOBO_GW_SOCKET → 后端误入 socket 模式 → 桌面版完全哑火
- 现象：在带 BOBO_GW_SOCKET 的 shell 里 npm start，Electron 窗口正常打开，但后端 stdout 无任何输出，renderer 永远 "Waiting for backend..."，发消息无响应。
- 根因：main.cjs startBackend() `env = {...process.env, BOBO_BACKEND:'1', ...}` 原样继承环境变量。现行 entry.py:497 `if sock_path: _run_socket_backend(sock_path); return`——一旦 BOBO_GW_SOCKET 非空即走 socket 模式 accept() 空等客户端（桌面版无 socket 客户端），stdio 通路废弃。
- 证据（实测）：`env | grep BOBO_GW_SOCKET` 显示当前 shell 即携带 `BOBO_GW_SOCKET=/var/folders/.../bobo-gw-55370-*.sock`（TUI 会话注入）；带该变量 spawn 后端 → 4s+6s stdout 0 字节、进程卡 accept（stack_dump.log 显示 `_run_socket_backend` → `socket.readinto`）；`env -u BOBO_GW_SOCKET` 后同进程 3s 内正常发 gateway.ready + notes.tree，RPC 全部应答。
- 触发场景：用户从跑着 TUI 的终端启动桌面版、或任何继承该变量的 shell/launchd 环境。真实风险高。
- 修复建议：spawn env 显式 `del env["BOBO_GW_SOCKET"]`（以及 BOBO_SESSION_DIR、BOBO_BACKEND 之外的 TUI 专属变量），强制走 stdio。
- 严重度：**阻断**。

### E2【高】resolvePython() 不感知 install.sh 三级安装（user-site / pipx / venv）
- 现象：桌面版只探测 /opt/homebrew/bin/python3 → /usr/local/bin/python3 → /usr/bin/python3 → python3。
- 根因：install.sh 安装顺序为 `pip install --user` → pipx → venv（~/.bobo/venv）；venv/pipx 安装用户的解释器在 ~/.bobo/venv/bin/python 或 ~/.local/pipx/venvs，均不在探测列表。
- 证据：main.cjs resolvePython() vs install.sh 第 55-105 行。
- 影响：venv 安装用户桌面版会选到系统 python3（可能无依赖）→ 后端启动失败或 import 报错，且重启策略会 60s 无限重试（E8）。
- 修复建议：探测优先级加入 ~/.bobo/venv/bin/python、pipx venv 路径；或与共享后端（D-1c）统一为"用已安装的 bobo 解释器"。
- 严重度：高。

### E3【高】dev 模式数据目录与 TUI 不一致（~/.bobo vs 仓库 data/）
- 现象：桌面版 dev 模式 BOBO_DATA_DIR=~/.bobo，TUI dev 模式默认仓库 data/，两端会话/记忆/知识库各写各的。
- 根因：main.cjs env 显式 `BOBO_DATA_DIR: process.env.BOBO_DATA_DIR || ~/.bobo`；config.py:13-19 无 BOBO_DATA_DIR 且仓库 data/ 存在时用仓库 data/。
- 证据：实测桌面版后端日志 `已加载配置: /Users/niuqingwei/.bobo/.env`（run1/run2 日志）；config.py:13-19。
- 影响：D-1c"共享同一 ~/.bobo 数据目录"在 dev 模式下不成立；同一会话在两端不可见。
- 修复建议：dev 模式桌面版不设 BOBO_DATA_DIR（跟随 config.py 默认），或 TUI dev 也统一 ~/.bobo；D-1c 定案。
- 严重度：高。

### E4【高】打包版 installBoboBackend 不拷 data/ → 记忆库/票据/知识库全缺
- 现象：packaged 首次运行拷 core/tools/bobo_tui_gateway/config.py/pyproject.toml 到 ~/.bobo，无 data/。
- 根因：main.cjs installBoboBackend() 拷贝清单不含 data/（library/、knowledge_base.json、tickets/、sessions/、logs/）。
- 证据：main.cjs:210-260（installBoboBackend 拷贝循环）。
- 影响：打包版引擎无记忆库、无票据授权（protected_paths 上下文）、无技能标准、无历史会话——功能大幅降级；且每次发布都要重新装。
- 修复建议：extraResources 增加 data/ 初始快照，或 D-1c 改为共享已安装后端的 data/（推荐，符合票意）。
- 严重度：高。

### E5【中】真实环境 ~/.bobo/.env 存在坏行（多行值无引号）
- 现象：npm start 日志刷 20+ 条 `python-dotenv could not parse statement starting at line 18/20/22-43`。
- 根因：~/.bobo/.env 中 BOBO_SYSTEM_PROMPT_CODE_WORKFLOW 值为多行 Markdown 未加引号（第 18 行起），python-dotenv 只取第一行，其余行全部解析失败。
- 证据（实测）：run1/run2 日志；`sed -n '1,50p' ~/.bobo/.env`（第 18-43 行为未引号多行）。
- 影响：该变量被截断为第一行；每次启动刷屏报错；save-env 追加逻辑会保留坏行永久污染。
- 修复建议：save-env/setup.submit 写入时对含换行/特殊字符的值加引号；提供一次坏行清理（将多行值收敛为单行或引号包裹）。
- 严重度：中。

### E6【中】icon.icns 加载失败
- 现象：`[13091:...] WARNING:electron_api_native_image.cc(196)] Failed to load image from path '.../apps/desktop/build/icon.icns'`。
- 证据（实测）：run4 日志；文件存在（5.4KB）但 Electron 无法解码。
- 影响：窗口/dock 图标缺失。
- 修复建议：重新生成合法 icns（sips/iconutil）。
- 严重度：中。

### E7【低】window-all-closed 即退出，与 macOS 惯例不符
- 现象：所有窗口关闭 → stopBackend + app.quit()；activate 分支（重建窗口）形同虚设。
- 证据：main.cjs window-all-closed handler。
- 影响：用户体验（点红叉即整个应用退出），功能无损。
- 修复建议：macOS 下 window-all-closed 不退出，仅 stopBackend；activate 重建。
- 严重度：低。

### E8【低】崩溃 3 次后 60s 无限重试
- 现象：后端崩溃 3 次后进入 60s 周期无限重启。
- 证据：main.cjs exit handler（`setTimeout(... 60000)` 无上限）。
- 影响：若根因是 E2（Python 路径错误），将永久空转弹窗；资源占用。
- 修复建议：上限次数后转人工（显示错误 + 停止自动重启）。
- 严重度：低。

### E9【低】save-env 每次调用都重启后端
- 现象：save-env handler stopBackend + 500ms 后 startBackend。
- 证据：main.cjs save-env handler。
- 影响：配置流程若多次调用则频繁重启；renderer 实际走 setup.submit（不重启，见 B3），该通道基本闲置。
- 严重度：低。

---

## Layer 3 后端接口层（bobo_tui_gateway vs renderer 调用）

### B1【高】安全闸确认在 GUI 下不可用（approval.request 无 UI / approval.respond 无调用）
- 现象：引擎触发确认（goal_gate/命令安全闸）时发 approval.request，renderer 未订阅 → 无人确认 → 120s 超时自动拒绝 → GUI 中受保护操作全部失败。
- 证据：dist JS 订阅清单无 approval.*；core/engine_adapter.py:184-200 confirm_callback（`emit("approval.request")` + 120s `_wait_for_confirmation`）。
- 影响：桌面版无法执行任何需要闸确认的操作（受保护路径写操作、高危命令等）；这是 D-1d 必须补的平齐项。
- 修复建议：D-1d 加确认弹窗 UI + approval.respond 调用。
- 严重度：高（安全功能缺失，非崩溃）。

### B2【低】JSON-RPC 方法/事件协议整体兼容（实测通过）
- 现象：renderer 调用的 setup.status / session.create / session.resume / prompt.submit 全部存在，返回格式兼容；事件格式（jsonrpc 2.0 + method:event + params.type/payload）与 renderer 解析逻辑一致。
- 证据（实测冒烟）：setup.status → provider_configured ✓；session.create → session_id ✓；session.resume → messages ✓；gateway.ready/notes.tree 事件到达 ✓。
- 影响：无。接口层无断裂，是本审计中唯一全绿的一层。
- 严重度：低（信息项）。

### B3【高】setup.submit 写文件后不刷新运行时 API_KEY（实测）
- 现象：配置流程 setup.submit 返回 ok 后，setup.status 仍返回 provider_configured:false；renderer 据此创建会话发 prompt.submit，后端仍用旧（空）API_KEY → 对话失败。
- 根因：config.py 的 API_KEY 为模块级常量（import 时读一次）；handle_setup_submit 只 write_atomic 写 .env，不更新 os.environ / 不重启后端。
- 证据（实测）：冒烟脚本 setup.submit（provider_configured:true）→ setup.status（provider_configured:false）；configs.py:22-70。
- 影响：桌面版首次配置 API key 后必须手动重启 app 才能对话；TUI 若同样走 setup.submit 也受影响（TUI 未实测，标注待查）。
- 修复建议：setup.submit 同步 os.environ + 刷新 config 缓存（或返回"需重启后端"标记，renderer 调用 save-env 通道重启）。
- 严重度：高。

---

## Layer 4 底层依赖层（package.json / electron-builder / install.sh）

### D1【高】Electron ^33 已 EOL（安全停更）
- 现象：package.json devDependencies electron ^33.0.0；Electron 33 已于 2025 年 EOL，无安全更新。
- 证据：package.json; 票背景已知。
- 影响：安全风险（本地加载 + contextIsolation 下风险有限，但长期不可接受）。
- 修复建议：本票不升级（票约定），D-1 后单列升级票。
- 严重度：高（已知项，本票不做）。

### D2【中】无 engines / Node 版本约束
- 现象：package.json 无 engines 字段；electron-builder ^25。
- 证据：package.json。
- 影响：Node 版本漂移不可控（本机 Node 22 实测可跑）。
- 修复建议：加 engines（node >=18）。
- 严重度：中。

### D3【低】extraResources 路径有效（dev 模式不走打包）
- 现象：from ../../core 等相对 apps/desktop = 仓库根，路径正确；dev 模式 PYTHONPATH=仓库根直接共享源码。
- 证据：package.json build.extraResources；实测 run1/run2 后端 cwd/项目根正确。
- 影响：无（但打包快照机制与 D-1c"共享已安装后端"矛盾，D-1c 定案时处理）。
- 严重度：低。

### D4【低】install.sh 与桌面版零对接
- 现象：install.sh 只装 bobo CLI，无桌面版；桌面版也不引导 install.sh。
- 证据：install.sh 全文。
- 影响：D-1c 共享后端需要明确安装契约（桌面版依赖 bobo 已安装或自带）。
- 严重度：低。

### D5【中】dist/index.html 无 Content-Security-Policy
- 现象：Electron 启动日志 `Electron Security Warning (Insecure Content-Security-Policy)`。
- 证据（实测）：run4 日志。
- 影响：本地文件加载 + contextIsolation:true 下风险有限，但应加 CSP（default-src 'self'）防御。
- 修复建议：dist/index.html 加 CSP meta；恢复源码后一并处理。
- 严重度：中。

---

## 实跑取证记录

| # | 实验 | 命令/方式 | 结果 | 对应条目 |
|---|------|-----------|------|----------|
| 1 | 后端 stdio 冒烟（带 BOBO_GW_SOCKET） | env 继承 spawn | stdout 0 字节、卡 accept 6s+ | E1 |
| 2 | 后端 stdio 冒烟（env -u BOBO_GW_SOCKET） | 3.14 python spawn | 3s 内 gateway.ready + notes.tree；setup.status/session.create 全应答 | B2 |
| 3 | npm start（带 BOBO_GW_SOCKET） | Electron 实跑 | 窗口正常、后端 spawn 3.14、无任何后端消息 | E1 |
| 4 | npm start（env -u BOBO_GW_SOCKET） | Electron 实跑 | 窗口 "Bobo"、后端 env 确认无 GW_SOCKET、dotenv 坏行刷屏、icon 失败 | E5/E6 |
| 5 | npm start（ELECTRON_ENABLE_LOGGING） | Electron 实跑 | renderer 仅 CSP warning，无 Connected 日志（状态机不可终端观测） | D5 |
| 6 | setup 流程冒烟 | 空 BOBO_DATA_DIR spawn | setup.submit ok → setup.status 仍 false | B3 |
| 7 | stack_dump 取证 | data/logs/stack_dump.log | TUI gateway 走 socket 模式、LLM worker 网络阻塞为正常态 | E1 佐证 |

## 严重度统计

- 阻断 2：R1（源码缺失）、E1（GW_SOCKET 哑火）
- 高 6：R2、E2、E3、E4、B1、B3
- 中 4：E5、E6、D2、D5
- 低 8：R3、R4、E7、E8、E9、B2、D3、D4

## 修复顺序建议（供 D-1b 参考，最终由 Kimi 裁决）

1. E1（一行级修复，立刻解除哑火）
2. B3 + E5（配置链路，否则装好也聊不了天）
3. E2（Python 路径对齐 install.sh 三级）
4. E3/E4/D3（数据目录与共享后端，D-1c 一并定案）
5. R1（恢复源码，D-1d 前置）
6. B1（闸确认 UI，D-1d）
