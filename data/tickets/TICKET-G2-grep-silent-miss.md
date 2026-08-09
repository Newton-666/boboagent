# TICKET-G2：grep_code 静默漏检修复

> 立案：2026-08-09 · Kimi 终审立案 · 新 session 施工
> 优先级：中（AUTO MODE 施工前的热身票，先行修复以保证后续侦察质量）
> 纪律：branch 施工（fix/ticket-g2-grep-silent-miss）、五查汇报、未终审不 merge 不 push

---

## 一、罪证（已核实，非推测）

1. `tools/grep_code.py:69-80` `_search_ripgrep` 的 rg 调用**无 `--no-ignore-vcs` 与 `--hidden`**：
   - rg 默认遵守 .gitignore → 项目 `data/` 整个目录（events.jsonl、票据、日志）被静默跳过；
   - rg 默认跳过隐藏文件/目录 → 点开头的正常内容全漏。
2. 实测误判（R1 侦察已记录）：搜 `OBSIDIAN_VAULT`/`mirror`，工具报 0 匹配，终端 `grep -r` 实际 22 处——差异全部落在 gitignore 区。
3. `tools/grep_code.py:40-44` Python 回退路径与 rg 规则不一致（只跳点开头的文件、另有自建跳过清单）——**同一次搜索的结果集取决于 rg 是否安装**，两条路两套口径。
4. `MAX_MATCHES = 50` 截断提示太弱（"仅显示前 50 条"），残集被当成全集使用。

危害定性：静默漏检比报错恶劣——报错知道重试，漏检直接拿错误结论往下走。AUTO MODE 的证据链/灰名单审计大量依赖搜索 data/logs，此票不修，后续侦察全部不可信。

## 二、施工内容

1. `_search_ripgrep` 的 cmd 增加 `--no-ignore-vcs --hidden`（保留 rg 默认跳 `.git/` 本体与二进制文件的行为）；
2. `_search_python` 回退路径对齐同一口径：不再跳过点开头的正常文件/目录（`.git` 等 VCS 元目录除外）；
3. 结果输出头部强制标注搜索口径：
   - 被跳过项统计（如 `.git/` 内部文件、二进制文件数）；
   - 若结果达 MAX_MATCHES，头部明示"结果已截断，实际 ≥N 条"；
4. 新增 `tests/test_grep_code_silent_miss.py`：
   - 在 gitignore 区（tmp 目录 + 配套 .gitignore）埋词，断言能搜到；
   - 在点开头的正常目录（如 `.config/`）埋词，断言能搜到；
   - 断言输出包含口径标注行。

## 三、验收（终审口径，判分人复跑为准）

1. 埋点词（gitignore 区 + 点目录）全部可搜到；
2. rg 可用与不可用（模拟回退）两条路径结果集一致；
3. 输出头部含口径标注；截断时明示；
4. 全量 pytest 零回归（当前基线 1570 passed / 2 skipped）；
5. 真实库 `data/knowledge_base.json` 与 `library/MEMORY.md` 全量跑前后 md5 不变（D2 闸门应自动覆盖，终审会复验）。

## 四、边界（明确不做）

- 不改 MAX_MATCHES 的值（只改提示强度）；
- 不重构输出格式主体；
- 不碰其他工具。

## 五、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文 / commit hash 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
