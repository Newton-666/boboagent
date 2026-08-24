"""router_accuracy.py — 路由器准确性评估（B 阶段补测）

黄金集：任务 → 期望 {必带工具, 期望技能, 期望记忆类型}。
测量（确定性，规则路由器可精确计算）：
  工具召回率 = 必带工具 ⊆ 路由器输出 ? 1 : 漏了哪些
  技能准确率 = 路由器技能 == 期望技能 ?
  记忆准确率 = 路由器记忆类型 覆盖期望 ?

用法：python3 scripts/router_accuracy.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.router import route

# ── 黄金集（任务 → 期望路由）──
GOLDEN = [
    ("修复这个函数的 bug，pytest 报错", {"code-fix"},
     {"edit_file", "grep_code", "read_local_file", "run_tests"},
     {"LESSON", "FACT"}),
    ("把当前工作区改动提交一下", {"git-workflow"},
     {"execute_terminal", "git_status"}, set()),
    ("帮我查一下上海和北京的房价对比", {"research"},
     {"web_search", "web_fetch", "search_obsidian"}, {"FACT"}),
    ("把内容整理进 Obsidian 笔记", {"note-taking"},
     {"write_obsidian", "append_obsidian", "read_obsidian", "search_obsidian"}, set()),
    ("运行 pytest 看看测试情况", {"code-fix"},
     {"execute_terminal", "run_tests", "grep_code"}, {"LESSON", "FACT"}),
    ("帮我记住以后都用 Python", set(), {"save_memory", "search_memory"}, {"USER_PREF"}),
    ("看看邮箱新邮件", set(), {"search_emails", "read_email_content"}, set()),
    ("你好", set(), set(), set()),
    ("现在几点了", set(), {"get_current_time"}, set()),
    ("读取 config.py 内容", set(), {"read_local_file", "list_directory", "grep_code"}, set()),
]


def main():
    rows = []
    for task, exp_skills, exp_tools, exp_mem in GOLDEN:
        p = route(task)
        got_tools = set(p.tool_names)
        got_skills = set(p.skill_names)
        got_mem = set(p.memory_types)
        tool_miss = exp_tools - got_tools      # 漏掉该带的
        tool_extra = got_tools - exp_tools - {"get_current_time", "read_local_file",
                                              "list_directory", "grep_code",
                                              "save_memory", "search_memory", "execute_terminal"}
        skill_ok = got_skills == exp_skills
        mem_ok = exp_mem.issubset(got_mem) if exp_mem else not got_mem
        rows.append((task, tool_miss, tool_extra, skill_ok, mem_ok))
        print(f"{task[:22]:<24} 工具漏:{str(sorted(tool_miss) or '无'):<24} "
              f"工具多余:{str(sorted(tool_extra) or '无'):<12} 技能:{'✓' if skill_ok else '✗'+str(sorted(got_skills))} 记忆:{'✓' if mem_ok else '✗'}")
    tool_miss_all = sum(len(r[1]) for r in rows)
    tool_extra_all = sum(len(r[2]) for r in rows)
    skill_ok_all = sum(1 for r in rows if r[3])
    mem_ok_all = sum(1 for r in rows if r[4])
    print("-" * 80)
    print(f"工具：漏带 {tool_miss_all} 个必带 · 多余 {tool_extra_all} 个无关（常驻不计）")
    print(f"技能：{skill_ok_all}/{len(GOLDEN)} 任务技能选对")
    print(f"记忆：{mem_ok_all}/{len(GOLDEN)} 任务记忆类型正确")


if __name__ == "__main__":
    main()
