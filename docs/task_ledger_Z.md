# 票 Z 任务台账 — 收工闸 v2

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 1 | engine.py: 缝1 无账强制建账（_ledger_reminded 标记，工具轮≥2且无台账时注入提醒） | pending | |
| 2 | engine.py: 缝2 承诺检测闸（未来时正则 + 收束白名单，共享 _ledger_reinject_count） | pending | |
| 3 | engine.py: 缝3 熔断放行写 goal_gate.released / goal_gate.promise_detected 事件 | pending | 含原有 ledger 放行路径 |
| 4 | engine.py: 干净收工时重置 _ledger_reminded | pending | |
| 5 | tests/test_goal_gate.py: 验收测试（复刻 10:50 案/无账提醒/熔断逃生/闲聊零误拦/收束白名单） | pending | |
| 6 | 全量 pytest 回归不破坏 | pending | |
| 7 | 五查汇报 + git status 原文 | pending | |
