---
ticket: TICKET-O1
title: OFFICE MODE 执法内核——角色注入 + 能力矩阵 + 受保护清单 + 票据授权书
branch: feat/ticket-o1
status: 待施工
author: Kimi 开票（依据《OFFICE MODE 设计草案 v0.3.1》）
date: 2026-08-10
authorized_paths:
  - core/engine.py
  - core/command_safety.py
  - tools/file_operation.py
  - tools/edit_file.py
  - tools/file_writer.py
  - tools/execute_terminal.py
  - data/protected_paths.json
  - tests/
---

# TICKET-O1 OFFICE MODE 执法内核

## 一、立法依据

《OFFICE MODE 设计草案 v0.3.1》（library/agent开发/）。一句话：开关在 owner 嘴里（/office 仅老板 bobo 注册，O-2 票做），搭建在老板手里（O-2），**本票只做镣铐**——员工进程出生即戴，且普通模式零影响。

## 二、最高验收原则（凌驾一切）

**普通模式零影响**：环境无 `BOBO_ROLE` 时，所有行为与本票施工前逐字节一致。每条验收必须配一条"无角色对照组"测试。宁可 office 限制漏一处，不可普通模式变一毫。

## 三、施工内容

### O1-1 角色读取（engine 启动时一次性读取）

- `core/engine.py` `__init__`：`self._role = os.environ.get("BOBO_ROLE")`，合法值 `staff` / `dispatcher` / None；非法值按 None 处理并写审计事件 `office.role`（含原始值）。
- 只读，全程不可变；不提供任何运行时修改入口。

### O1-2 受保护清单

- 新建 `data/protected_paths.json`（本票授权路径内含它）：

```json
{
  "globs": [
    "tools/*relay*.py",
    "tools/agent_connect.py",
    "tools/agent_scan.py",
    "data/relay_v2/**",
    "bobo_tui_gateway/**",
    "core/**",
    "library/**",
    "data/protected_paths.json",
    "data/office_roles.json"
  ]
}
```

- 加载落点：`core/command_safety.py` 新增 `load_protected_paths()` + `is_protected(path) -> bool`（glob 匹配，相对项目根解析；文件缺失/损坏 → 返回空清单 + 审计，**不得炸启动**）。
- `tests/` 不进清单（票据永远要写测试）。

### O1-3 能力矩阵（只在有角色时激活）

| 能力 | staff | dispatcher |
|---|---|---|
| git 写操作（commit/push/reset/rebase/tag/checkout 切分支/stash 外的一切写） | 全禁 | 全禁 |
| 受保护路径 写/删/移 | 全禁，唯一豁免=当前会话票据 authorized_paths 显式列出该路径 | 全禁，**无豁免** |
| library/** 直接文件写（file_operation/edit_file/file_writer/execute_terminal） | 全禁（记忆系统专有接口 v5_memory/memory_mirror 不在此限） | 全禁 |
| 票据范围外文件写 | 全禁（范围=票据 authorized_paths；无票据则全部写操作拒绝） | 全禁（一切写拒绝） |
| 跨 agent 发消息、读操作 | 本票不动 | 本票不动 |

dispatcher 一句话：**一切写操作全禁，无例外通道**。

### O1-4 拦截落点（与 AUTO MODE 同一条决策链）

1. `core/engine.py` `_confirm`：在 test_mode 判断之后、auto 分支之前，插入 office 角色判断段（`_office_decide(tool_name, tool_args)`）：有角色 → 按矩阵裁决，deny 直接拒绝（零弹窗，系统性拦截同黑名单逻辑，reason 写明"OFFICE 角色限制 — …"）；无角色 → 直接跳过本段，走原有链路。
2. 文件类工具参数取路径：`file_operation(action/path/files)`、`edit_file(path)`、`file_writer(path)`；写/删/移动类 action 才拦截，读 action 放行。
3. `execute_terminal`：git 写操作判定复用 `classify_command` + git 写子命令清单（commit/push/reset/rebase/tag/checkout/branch -D/stash pop 等，列出明确清单）；命令中的受保护路径提取做最佳努力（引号/管道漏判由 O-3 快照兜底，本票承认 6-7 成）。
4. 每次拦截写 events.jsonl：`type: office.guard`，字段含 role/tool/path 或 command/verdict/reason/sid。

### O1-5 票据授权书读取

- 读 `data/tickets/*.md` frontmatter：`ticket` + `authorized_paths`。当前会话票据 = 环境变量 `BOBO_TICKET`（启动注入，同 BOBO_ROLE 一并由搭建器注入；O-2 之前手工注入即可）。
- 豁免判定：路径在受保护清单 且 在当前票据 authorized_paths 中 → staff 放行（dispatcher 无此通道）。
- 票据缺失/无 BOBO_TICKET/路径未列出 → 按无豁免处理。

## 四、验收清单（每条=角色组+无角色对照组）

1. staff + 无票据：file_operation 写 `tools/team_relay_v2.py` → 拒绝 + 审计；**对照：无角色同操作行为与施工前一致（弹窗/放行逻辑不变）**。
2. staff + 票据 authorized_paths 含 `tools/team_relay_v2.py`：写该文件 → 放行；写同目录 `tools/agent_connect.py`（未列出）→ 拒绝。
3. dispatcher + 票据含同路径：写 → 仍拒绝（无豁免通道）。
4. staff：execute_terminal `git commit -m x` → 拒绝；`git status`/`git log`/`git diff` → 放行；**对照：无角色 git commit 走施工前原有链路**。
5. staff：file_operation 写 `library/MEMORY.md` → 拒绝；v5_memory 正常写入不受影响。
6. BOBO_ROLE=bogus：按无角色处理 + 审计事件，行为与普通模式一致。
7. data/protected_paths.json 缺失：不炸启动，空清单 + 审计。
8. 审计事件字段齐全（role/tool/verdict/reason/sid）。
9. 全量 pytest 零回归（基线 1759 passed / 2 skipped）+ 新增测试全过。
10. 真实库三文件 md5（data/knowledge_base.json / library/MEMORY.md / library/index.md）跑前跑后一致。

## 五、纪律

- 分支 `feat/ticket-o1`（自最新 main 切出）；未终审不 merge 不 push；五查汇报。
- 施工前必须重读 v0.3.1 设计稿；与稿有出入以稿为准并在汇报中说明。
- 本票不做：/office 命令注册（O-2）、搭建器（O-2）、快照（O-3）、前端任何改动。
- 启动验证方式（O-2 未做前）：`BOBO_ROLE=staff BOBO_TICKET=TICKET-O1 bobo` 手工注入。
