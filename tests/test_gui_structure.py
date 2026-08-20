"""TICKET-GUI-T2 专项测试 — 前端结构完整性检查。

背景：apps/desktop/dist/index.html 是单文件 vanilla JS（唯一真身），
无构建管线。单文件最怕"改了不知道影响哪"——AI/人手改动时手滑删了
半个函数、事件监听断链、括号不闭合，都会静默破坏渲染链路。

本测试作为"结构闸门"：任何 GUI 改动后，跑一遍即知结构是否完整。
- 括号平衡（语法级破坏）
- 关键函数存在性（渲染链路断裂）
- 关键事件注册（事件断链）
- 主脚本大小（异常截断）

覆盖（票验收）：
- T2-1 括号平衡：主脚本 { } 配对最终深度为 0
- T2-2 关键函数：CRITICAL_FUNCS 全部存在（缺一个渲染链路断裂）
- T2-3 关键事件：CRITICAL_EVENTS 全部注册（缺一个事件断链）
- T2-4 主脚本规模：> 50K chars（防异常截断/空文件）
- T2-5 函数提取工具：extract_func 能提取关键函数且括号闭合
"""

from gui_harness import (
    CRITICAL_EVENTS,
    CRITICAL_FUNCS,
    bracket_balance,
    extract_func,
    extract_main_js,
    gui_file,
)


def test_t2_1_bracket_balance():
    """主脚本括号必须平衡（语法级破坏的哨兵）。"""
    main = extract_main_js()
    assert bracket_balance(main) == 0, "主脚本 { } 不平衡——可能存在语法破坏"


def test_t2_2_critical_funcs_present():
    """关键渲染函数必须全部存在。"""
    main = extract_main_js()
    missing = [
        fn for fn in CRITICAL_FUNCS
        if not __import__("re").search(
            r"(?:async\s+)?function\s+" + fn + r"\s*\(", main
        )
    ]
    assert not missing, f"关键函数缺失: {missing}"


def test_t2_3_critical_events_registered():
    """关键事件监听必须全部注册。"""
    main = extract_main_js()
    missing = [evt for evt in CRITICAL_EVENTS if f"on('{evt}'" not in main]
    assert not missing, f"关键事件监听缺失: {missing}"


def test_t2_4_main_script_size():
    """主脚本不能异常短（防截断/空文件）。"""
    main = extract_main_js()
    assert len(main) > 50000, f"主脚本异常短: {len(main)} chars"


def test_t2_5_extract_func_roundtrip():
    """extract_func 工具自身必须能提取关键函数且括号闭合（工具自检）。"""
    main = extract_main_js()
    for fn in ["addMsg", "renderFullHistory", "buildHistUnits", "loadSession"]:
        code = extract_func(main, fn)
        assert code.strip().startswith(("function", "async")), f"{fn} 提取失败"
        assert bracket_balance(code) == 0, f"{fn} 提取的代码括号不平衡"
