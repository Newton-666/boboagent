# TICKET-FRONTEND-GREEN

> 类型：测试体系偿还（前端存量 4 个失败）
> 开票：2026-08-23 · 与阶段 2（test-layering）并行
> 依据：TICKET-MAIN-REGREEN 分拣——前端 4 个失败根因在 main 前端票改 dist 未同步静态守卫
> 红线：**不可为绿改守卫语义**——先判研"守卫是否是真的"，是真的就修前端，不是才更新守卫

---

## 1. 失败清单（4 个）

| 测试 | 断言内容 | 现状 | 疑点 |
|---|---|---|---|
| `test_v4b0_2_busy_gate_static` | 发送闸门必须保留 `messaging` 判断 | 前端 HTML 缺该判断 | **可能是真 bug**：A 会话运行时 B 会话仍可发（实弹复发风险） |
| `test_v2a_css_zero_change_on_existing` | P0-1 前既有 CSS 与基线逐字节一致 | dist CSS 被 main 票改动 | 需对比 rollback/pre-p0-1 判定是"新 CSS 合法添加"还是"旧 CSS 被改" |
| `test_v2b_css_zero_change_on_existing` | 同上 | 同上 | 同上 |
| `test_v2b3_1_slash_route_static` | sendPrompt/execSlash 路由结构 | GUI 缺某子串 | 需定位缺的是哪段 |

## 2. 判研程序（每个失败三选一）

1. 守卫是真的（前端确实违背了它守护的铁律）→ **修前端**（恢复 messaging 判断 / 还原 CSS / 修路由），附实弹验证；
2. 守卫过时（main 有意改变了前端行为，守卫没跟上）→ 更新守卫到新现实，并记录变更票号；
3. 环境/构建产物（dist 是构建产物被误提交）→ 按产物纪律处理（重新构建/入 gitignore），不动守卫。

## 3. 边界

- 只处理 4 个失败及其根因；不重构前端；
- 若判研发现 `messaging` 判断真的丢失 → 这是**安全回归**（A 运行中 B 可发送），按 bug 优先处理并实弹验证；
- 完成标准：4 个测试全绿 + 判研结论入票 + CHANGE-LOG 记录。

## 4. 前置

- 依赖阶段 2 的"分层后全量"作为回归基线（前端不动引擎，互不阻塞）。
