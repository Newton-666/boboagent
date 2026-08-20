# TICKET-GUI-T1/T2/T3 — 前端工程兜底（自进化前置）

> 开票：2026-08-20（owner 拍板：先装眼睛再讨论自进化）
> 分支：`feat/gui-test-infra`，提交：`d20e6993`
> 回滚标签：`rollback/pre-gui-test-infra-20260820`（ebcbee7d）

## 背景

自进化 = 系统不断改自己。bobo 要具备自进化能力（用户感知"bobo 更懂我"），
前提是每次改动有安全网——否则高频改自己 = 盲改。前端（dist/index.html
4687 行 vanilla 单文件）此前**零测试**，任何改动全靠人肉实弹验证。

## 三张票

### GUI-T1 测试基建（tests/gui_harness.py）
- `extract_main_js()` 提取主脚本 / `extract_func()` 括号配对提取函数
- `run_node()` node 实跑（行为验证）/ `make_el()` DOM 元素桩
- `bracket_balance()` 括号平衡 / `assert_structure()` 整体结构闸门

### GUI-T2 结构检查（tests/test_gui_structure.py，5 用例）
- 括号平衡 / 关键函数存在（18 个）/ 关键事件注册（11 个）/ 脚本规模 / 工具自检

### GUI-T3 关键路径测试（tests/test_gui_critical_paths.py，4 用例）
- 窗口化渲染链（201 条消息 buildHistUnits+renderHistWindow）
- 滚动重建不炸（F19-C busy 挂起）
- 推理流 + 工具边界清空（叠罗汉回归，真实 handler 提取）
- F19 三处修复代码形态仍在

## 验证

- GUI 测试 19/19 passed（含既有 F19/F19b）
- 全量 pytest 2810 passed（+13 新增；6 failed 基线已有，零回归）
- 零功能改动：仅 tests/ + docs/GUI-LESSONS.md，dist/index.html 未动

## 教训（GUI-LESSONS L15）

提取 JS 函数体做测试时**必须保留原参数名**——改名导致函数体引用绑定到外层
全局变量，测试误判。测试桩的忠实度决定测试可信度。
