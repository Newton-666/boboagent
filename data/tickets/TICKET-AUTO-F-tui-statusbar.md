# TICKET-AUTO-F：TUI 底栏 AUTO ON 状态指示

> 立案：2026-08-10 · 依据 v0.7 裁决三
> 分支：feat/ticket-auto-f（自最新 main 切出）
> 纪律：branch 施工、五查汇报、未终审不 merge 不 push
> 规模：小票（前端为主 + 后端状态推送）
> 本票附带实弹测试任务：施工中途 owner 会按 ESC 中断并说"继续"——此为 E-1 中断保进度的真实环境验收，按ESC后继续干活即可，不必汇报异常。

---

## 一、背景与现状

- `/auto` 现状：prompts.py 的 handle_slash_exec 返回文本（如"AUTO MODE 已开启（会话级）"），显示在**对话流内**；
- v0.7 裁决三：AUTO ON 指示必须在 **TUI 底部状态栏**（与模型名、context 用量同栏），不再混入对话流；
- auto 开关是会话级状态（票 A 落在 ctx 会话级，engine 经 `_auto_mode_getter` 读取）。

## 二、施工内容

### F-1. 后端：auto 状态推送

- /auto 切换时，gateway 向前端推送状态事件（如 `session.auto_state {on: bool}`）；
- 会话恢复/切换时，前端能查到当前会话的 auto 状态（ resume 不丢指示）；
- slash 返回文本可保留简短确认，但**主指示走状态栏**。

### F-2. 前端：底栏指示

- TUI 底部状态栏（模型名 / context 用量那一栏）增加 AUTO 指示：
  - auto 开：显示醒目的 `AUTO ON`（建议用主题强调色）；
  - auto 关：不显示（不占栏位）；
- 状态随 `session.auto_state` 事件实时更新；切换会话时跟随该会话状态。

### F-3. 测试

- 前端：底栏组件在 auto on/off 下的渲染用例；事件更新用例；
- 后端：/auto 切换时事件发射用例（含 sid）；resume 后状态可查询用例。

## 三、验收（终审口径）

1. `/auto` 开启 → 底栏出现 AUTO ON，对话流不再被大段状态文本占用；
2. `/auto` 关闭 → 指示消失；
3. 切换/恢复会话 → 指示跟随该会话实际状态；
4. auto 决策环零回归（A/B/D/E 测试全过）；
5. 全量 pytest（基线 1688/2）+ 前端 vitest（基线：14 个遗留 failed，不得新增失败）零回归；
6. 真实库 md5 闸门照旧。

## 四、边界（明确不做）

- 不动 auto 决策树、ESC 逻辑、Ctrl+C；
- 不做票 C 台账字段；
- 不改底栏其他指示的样式。

## 五、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文（pytest + vitest）/ commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
