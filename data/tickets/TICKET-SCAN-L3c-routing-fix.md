# TICKET-SCAN-L3c：多模式输入路由三修（实弹抓获）

> 立案：2026-08-10 · owner 实弹 L3b 抓获三 bug（附现场：用户说"pi,你能看到吗"被 bobo 抢答，
>   bobo 思考过程被转发给 pi，pi 回复带满屏终端噪音）
> 分支：feat/scan-l3c-routing-fix（自最新 main 切出）
> 纪律：branch 施工、五查汇报、未终审不 merge 不 push

---

## 一、Bug 与根因（已代码核实）

**Bug 1：多模式输入被双发（主犯）**
`handle_prompt_submit`（prompts.py:130-143）：relay active 时 push 给 relay 后**仍无条件启动引擎**——用户输入同时进 relay 和 bobo 大脑，bobo 抢答。
正确行为：多模式下用户输入 = 发给 pi 的消息。**relay active → 推给 relay 后直接 return ok，不启动引擎。**

**Bug 2：bobo 思考过程被转发**
relay 抓 bobo 回复未剥离 thinking/reasoning 段，内部推理原样发给 pi。
正确行为：转发前剥离思考段（💭 思考过程 块），只发最终回复正文。

**Bug 3：pi 回复是生屏幕**
capture-pane 抓回的内容含 pi 的工具调用噪音（ls/rg/head 输出、提示符、加载动画），原样显示。
正确行为：提取 pi 的实际回复文本（过滤命令回显、工具输出块、提示符行、spinner），显示/转发均为净化后内容。

## 二、施工内容

1. **路由闸**：prompts.py handle_prompt_submit——relay active 时 push + return，不进引擎启动路径；relay 内部若需要 bobo 接话（pi 回复后），由 relay 线程显式调用引擎（带 pi 的消息作为输入），不允许用户输入直通引擎；
2. **思考剥离**：bobo 回复提取时剔除 thinking 块（复用现有 thinking 标记格式），单测钉死"思考内容不出现在转发文本"；
3. **pi 输出净化**：新增净化函数——去掉命令行回显（$ 开头）、工具输出块（Took Xs、ctrl+o expand、行数省略提示）、提示符、spinner 行；宁保守：净化后为空则显示"[pi 输出解析中]"而非倒垃圾；
4. **多模式隔离复核**：/disconnect 或 ESC 退出后输入路由完全恢复（多模式关闭零变化断言已有，补这三条路径）。

## 三、验收（终审口径）

1. 多模式下用户输入**不触发引擎**（断言：relay active 时 submit 后 is_running(sid)==False 且 relay 队列收到原文）；
2. 转发给 pi 的文本**不含思考段**（含 💭 标记的样例输入，断言输出零思考内容）;
3. pi 模拟脏屏幕（含 $ 命令/Took/spinner）→ 显示文本只剩回复正文；
4. /disconnect 后输入立即恢复正常引擎路径；
5. 多模式关闭时行为零变化；auto 决策环零回归；
6. 全量 pytest（基线 1747/2）零回归；前端如涉及改动，收工含构建+部署+产物提交三步；真实库 md5 闸门照旧。

## 四、边界（明确不做）

- 不改互传轮数/话题编排逻辑；
- 不做 pi 回复的语义摘要（只净化噪音，不改写内容——透明原则）；
- 不动 auto 模式。

## 五、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文 / commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
