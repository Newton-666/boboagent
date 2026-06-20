# Changelog

## 0.5.0 — 2026-06-20

### 工程化基础设施
- 新增 CHANGELOG.md
- 新增 CI（GitHub Actions），每次推送自动运行 331 个测试

### 代码框架（Hermes 差距追赶）
- **多文件协调**：提示词允许批量编辑不冲突的文件，STATE_EXECUTING 加冲突检测保护
- **工具结果预算**：tool 消息独立 30K 字符上限，超出时按比例截断，不挤压代码内容
- **测试回归分析**：自动对比上次运行结果，标注已有失败 vs 新增失败
- **压缩优先级**：先丢弃状态更新/思考过程等低价值消息，最后才丢代码内容
- **文件阅读记录**：engine 记录已读文件路径+摘要，上下文压缩后自动注入最近 3 个文件摘要
- **edit_file 自动上下文**：old_string 不唯一时展示第一个匹配位置的前后文，不再直接拒绝

### 后端架构
- **引擎适配层**：新建 `core/engine_adapter.py`，server.py 不再直接 import Engine 类。改 engine 构造函数不再需要改 server.py
- **线程安全**：`_sessions` 和 `_current_sid` 全部读写点加锁，防止主线程和 engine 线程竞争
- **超时机制**：engine 执行超过 120 秒自动触发中断信号，防止幽灵线程堆积
- **cancel/is_running**：适配层暴露标准接口，server.py 不再直接操作 threading.Event
- **循环检测**：搜索类工具连续调用超过 3 次，自动注入提示让 LLM 停止搜索直接回答

### 桌面端
- **启动稳定性**：修复启动竞态条件，gateway.ready 3 次重试，消息缓冲防丢失
- **重启恢复**：后端崩溃后 60 秒自动重试，重置计数器
- **代码高亮**：重写 highlight() 函数——所有正则在纯文本上匹配，从右到左一次插入 span，彻底消除 HTML 结构损坏
- **表格渲染**：支持无分隔行的 LLM 风格表格，自动检测列数一致性，避免内联 `|` 误渲染
- **HTML 预览面板**：代码块上出现"预览"按钮，右侧 sandbox iframe 直接渲染，支持 allow-scripts
- **键盘快捷键**：Cmd+N 新建会话、Cmd+, 设置、Escape 停止思考
- **侧栏交互**：会话搜索（实时过滤）、会话改名（✎ 图标）、自动隐藏侧栏（窗口 <640px）
- **设置面板**：tab 导航（基础设置/API/高级设置）、Model 选择联动 Provider、清理数据按钮
- **macOS 通知**：工具完成时系统原生通知
- **欢迎页**：TUI 同款像素风格 ASCII art logo
- **死者清理**：删除 Vite/React 11 个文件（-3,814 行）、WS 服务器、无效 RPC、死导出

### 桌面端稳定性
- 重启计数器归零固定、发送超时保护、双击发送防护、settings 错误检测
- textarea 自动增高、发送按钮加载脉冲、工具结果可选中

## 0.4.0 — 2026-06-16

### Obsidian 护城河
- **code_to_obsidian**：自动将代码决策保存到 Obsidian vault
- **cross_project_search**：跨多项目同时搜索
- **review_to_obsidian**：PR 审查后自动创建 Obsidian 审查笔记

### 工具
- 新增 wiki_rebuild 工具（自动知识图谱）
- 新增 index_project（代码库索引，5 种语言）
- 新增 save_skill 工具

## 0.3.0 — 2026-06-16

### 多语言 auto-fix
- 支持 5 种语言：Python、JavaScript、Bash、Go、Rust
- 统一的 auto-fix 管线：执行失败 → LLM 修复 → 语法检查 → 重新执行（最多 3 次）
- 智能 diff reviewer（自动 git diff 审查 + 四维度提示）
- 代码库索引（函数/类/类型签名提取）

## 0.2.4 — 2026-06-16

### 安全追平
- write_denied 路径系统（30+ 精确路径黑名单 + 10+ 前缀规则）
- 二进制文件检测（扩展名 + magic bytes + null 字节）
- 环境隔离沙箱（sanitize_env 剥离 API Key/Token/Secret）

## 0.2.3 — 2026-06-16

### 紧急修复
- 修复 pip 安装后 gateway exited 崩溃（config.py 未包含在 pip 包中）
- 修复 TUI 构建产物过期

## 0.1.0 — 2026-06-13

初始版本
- 基础对话引擎（ReAct 循环）
- 70+ 工具（Web/文件/代码/邮件/日历/Obsidian/Notion/GitHub/记忆）
- Hermes Ink TUI 前端
- 教学模式 / 技能录制
- 对话回退 / 快照系统
- 命令安全白名单系统
- 7 种 LLM Provider 支持（DeepSeek/OpenAI/Anthropic/OpenRouter/Google/Ollama/Custom）
