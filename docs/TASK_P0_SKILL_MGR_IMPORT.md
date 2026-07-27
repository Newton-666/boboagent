# TASK_P0_SKILL_MGR_IMPORT — P0：injector._skill_mgr 断链修复

> 2026-07-27 Kimi 出单。小改但 P0——每轮对话都在静默失败的活 bug，
> 新日志系统抓到的第一条鱼。
> 证据：data/logs/bobo.log 每 3-10 秒一条
> "注入技能工作流失败: cannot import name '_skill_mgr' from 'tools'"

## 背景（已定位）

- `core/injector.py:74` `from tools import _skill_mgr` —— ticket-009
  把 SkillExecutor 并入 `core/skill_manager.py` 时删掉了 tools 里的
  `_skill_mgr`，injector 没跟上
- 后果：injector 的"可参考的技能工作流"注入块（约 74-119 行）
  每轮抛 ImportError 被 except 吞掉，该块功能整体失效
- **不影响** code-fix/self-hosting 标准注入（engine._load_skill_standards
  是纯文件扫描，另一条路）——已核实，不要扩大修复范围

## 任务文本（粘贴给 bobo）

```
任务：修复 injector 的 _skill_mgr 断链（feat/fix-skillmgr-import 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

证据：data/logs/bobo.log 反复刷
"注入技能工作流失败: cannot import name '_skill_mgr' from 'tools'"
断点：core/injector.py:74 —— ticket-009 把 SkillExecutor 并入
core/skill_manager.py，injector 还在 import 已删除的 tools._skill_mgr。

要求：
1. git checkout -b feat/fix-skillmgr-import，全程在该分支
2. 先读 core/injector.py:60-120 和 core/skill_manager.py，
   搞清楚 SkillManager 现在对外提供什么接口
   （get_skill_tools / get_skill 的等价物是否存在）
3. 修复方向二选一，commit message 说明选择理由：
   a. 改接 core/skill_manager 的现存接口（优先，如果接口等价）
   b. 若录制技能系统已整体废弃，删除 injector 里这个失效注入块
      （删代码也是修复——但先确认 skill-standards 不走这里，
      engine._load_skill_standards 是纯文件扫描，已核实）
4. 补测试：注入路径不再抛 ImportError（可用 mock 验证注入块
   完整走通或验证块已移除且不影响其余注入段）
5. ./.venv/bin/python3 -m pytest tests/ -q 全绿
6. 在 feat 分支 commit，五查汇报（表格），然后停
   （v2 规矩：允许本地 merge，禁止 push）

验收标准：
① bobo.log 不再刷"注入技能工作流失败"（修后跑几轮对话验证）
② 选择 a 则注入块功能恢复；选择 b 则其余注入段（API/记忆等）
   不受影响——二选一必须有证据
③ 不动 engine._load_skill_standards 路径
④ pytest 全绿 + 五查表格 + 未 push
```

## 备注

- 这是日志系统的第一个战果，修复后建议在 commit message 记一笔
- 验证①需要真跑 bobo 看日志——用户配合重启验证
