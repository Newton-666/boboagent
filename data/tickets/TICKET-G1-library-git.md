# TICKET-G1 主库 library 版本化保底（血案后遗症根治票）

> 分支：`feat/ticket-g1-library-git`（从最新 main 切出）
> 优先级：高。主库目前零版本控制，Time Machine 是唯一兜底——血案证明这不够。

## 〇、背景

08-09 血案：主库 20+ 篇笔记被测试误删，`git ls-files library/` 为空，回收站无踪，
全靠 Time Machine 本地快照侥幸救回。主库是用户资产，必须有自己的版本历史，
且**不依赖任何外部工具、不被任何测试触及**。

## 一、owner 裁决方向

笔记含研究内容（技术研究/健康日报/MEMORY 个人记忆），**默认不推送到任何远端**，
本地版本化即可。若日后要远端备份，另开新票评估私有仓库，本票不做。

## 二、方案（已定为推荐路线，施工按此做）

**library/ 就地 init 独立 git 仓库**（与项目仓库互不嵌套干扰）：

1. `library/.git`：独立仓库，首次提交纳入全部现有笔记（含 `.history/` 若恢复）。
2. **项目主仓库忽略**：项目根 `.gitignore` 加 `library/.git/`（主仓库仍不追踪笔记内容，
   但允许追踪 `library/.gitignore`、`library/README.md` 两个说明文件——可选）。
3. **自动提交钩子**：`tools/living_notes.py` 在 `_rebuild_index()` 完成后、镜像 sync 前，
   若 `library/.git` 存在则执行 `git -C library add -A && git -C library commit -m "<自动提交: 动作+主题+sid>"`，
   无变更时跳过；所有 git 失败静默降级（记 `notes.error` 事件），绝不阻塞笔记主流程。
   实现为 `tools/library_git.py`（<100 行），living_notes 运行时导入（同 library_mirror 纪律）。
4. **library/.gitignore**：`.DS_Store`。
5. **健康日报写入路径**（core/engine 或对应生成处）同样接自动提交钩子——
   若实现成本高，改为每日首次 write_living_notes 时兜底提交即可，施工者可选择并说明。

## 三、安全红线

- 钩子**只允许 add/commit**，禁止任何 push/reset/checkout/clean/rm 类写操作；
- 钩子必须 try/except 全捕获，git 缺席/仓库损坏时降级不阻塞；
- 禁止把 `library/.git` 嵌套追踪进项目主仓库；
- 测试：凡触发 write_living_notes 的测试，钩子指向 tmp 库或 monkeypatch 掉，
  严禁在真实 `library/` 里产生测试提交。

## 四、验收标准（终审逐条复跑）

1. 施工后 `git -C library log --oneline` 有初始提交；真实走一次 write_living_notes（可 mock LLM）
   → library 仓库出现新自动提交，提交信息含动作与 sid；
2. 无变更时重复触发 → 不产生空提交；
3. git 不存在/仓库损坏场景 → 笔记写入照常，notes.error 事件落盘；
4. 全量 `pytest tests/ -q` 零回归；新增测试覆盖 1-3；
5. `git status`（项目主仓库）不显示 library 笔记内容变更；
6. 全程分支施工，未 merge/push，停 `feat/ticket-g1-library-git` 等终审。

## 五、禁止项

- 禁止 push library 仓库到任何远端；
- 禁止改动笔记正文内容；
- 禁止 merge/push 项目主仓库；禁止绕过终审。
