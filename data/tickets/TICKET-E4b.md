# TICKET-E4b — 打包小修：DeepSeek 分型号窗口 + index.md 死链排查

- 分支：`fix/ticket-e4b-provider-window-index-fix`（从最新 main 切出）
- 类型：熵减计划 · 小修包
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 基线：1501 passed / 2 skipped

## A. DeepSeek 分型号窗口（owner 已拍板方向）

**背景**：`core/provider.py` 的 deepseek 条目 context_length=128000 是 V3 时代的保守值（TICKET-023）。deepseek-v4-flash / v4-pro 官方真实窗口为 1M（2026-04 发布）。当前 TUI context% 分母错误（虚报紧张）。

**施工**：
1. `core/provider.py` deepseek 条目：保留 `"context_length": 128000` 作为老型号兜底，新增 `"model_context": {"deepseek-v4-flash": 1000000, "deepseek-v4-pro": 1000000}`。
2. **压缩预算逻辑一行不动**（_get_context_budget 等保持现状）——窗口是天花板，预算是开支纪律，两者独立。
3. 测试：新增/更新用例——resolve_provider 在 API_MODEL_NAME=deepseek-v4-flash 时 context_length=1000000；老型号/未知名仍 128000；get_context_length 同步正确。

## B. index.md 死链排查

**案情**：A5 补测时 bobo 读 library/index.md，其中 `[[已有主题]]`（agent开发域）指向的 `library/agent开发/已有主题.md` 不存在——read_local_file 报路径不存在。

**施工**：
4. 取证：`library/agent开发/` 实际文件列表 vs index.md 条目，找出死链成因（文件被删但索引未重建？sanitize 改名？手动删过？），查 living_notes._rebuild_index 的触发时机，判断是 bug 还是历史残留。
5. 修复：若是重建逻辑 bug 则修最小范围；若只是历史残留，跑一次索引重建消除死链即可。
6. 测试：新增用例——笔记文件被删除后重建索引，index.md 不含死链条目。

## 验收
- 全量 pytest 零回归（基线 1501 + 新增）
- 汇报含：A 项 before/after、B 项死链成因陈述（"成因是 X，证据是 Y"）、测试清单、分支状态、是否需重启

## 边界
- 不动压缩触发预算；不动 living_notes 的合并/快照算法；不动其他 provider。
