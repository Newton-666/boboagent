"""TICKET-O3 豁免测试：RELAY_ORDER 环境变量（逗号分隔轮巡名单）。

票 O-3（owner 2026-08-11 指令）：tools/team_relay_v2.py 加 RELAY_ORDER
环境变量——默认 bobo,hermes,claude,pi 现行为零变化；RELAY_ORDER=bobo,pi
支持 2 人小队（pane 序号 = 名单序号）。relay 其余逻辑冻结。

覆盖：
  1. 默认（无 RELAY_ORDER）：ORDER/PANES 仍为 4 方，现行为零变化
  2. RELAY_ORDER=bobo,pi：ORDER=["bobo","pi"]，pane 映射 0.0/0.1
  3. 空/非法 RELAY_ORDER 回退默认（零变化保险）
"""

import os
import sys

import pytest

sys.path.insert(0, ".")
import tools.team_relay_v2 as rv


class TestRelayOrder:
    def test_default_order_four_way(self):
        """无 RELAY_ORDER：ORDER 默认 4 方，build_panes 默认映射零变化"""
        assert rv.DEFAULT_ORDER == ["bobo", "hermes", "claude", "pi"]
        assert rv._resolve_order() == ["bobo", "hermes", "claude", "pi"]
        panes = rv.build_panes("my_session")
        assert panes == {
            "bobo": "my_session:0.0",
            "hermes": "my_session:0.1",
            "claude": "my_session:0.2",
            "pi": "my_session:0.3",
        }

    def test_two_person_order(self, monkeypatch):
        """RELAY_ORDER=bobo,pi：两人序轮巡，pane 0.0=bobo / 0.1=pi"""
        monkeypatch.setenv("RELAY_ORDER", "bobo,pi")
        assert rv._resolve_order() == ["bobo", "pi"]
        panes = rv.build_panes("stage0-2staff", ["bobo", "pi"])
        assert panes == {
            "bobo": "stage0-2staff:0.0",
            "pi": "stage0-2staff:0.1",
        }

    def test_empty_order_falls_back(self, monkeypatch):
        """RELAY_ORDER 空/纯逗号/未知角色：回退默认 4 方，不崩"""
        for raw in ("", "  ", ",,,", " , "):
            monkeypatch.setenv("RELAY_ORDER", raw)
            assert rv._resolve_order() == ["bobo", "hermes", "claude", "pi"], raw

    def test_invalid_agent_falls_back(self, monkeypatch):
        """票 O-3 审查 P1（pi 0006）：含非法角色名 → 整体回退默认。

        只过滤空串不校验角色名 → foo,bar 会返回 ["foo","bar"] 不回退，
        与票面"空/非法回退默认"不符。修复后任一名字非合法角色即回退。
        """
        for raw in ("foo,bar", "hermes,evil", "bobo,pi,zzz", "  bobo ,  hacker  "):
            monkeypatch.setenv("RELAY_ORDER", raw)
            assert rv._resolve_order() == ["bobo", "hermes", "claude", "pi"], raw

    def test_order_drives_forward_chain(self, monkeypatch):
        """两人序转发链闭环：bobo→pi→bobo（rounds*len(ORDER) 完成条件适配）"""
        monkeypatch.setenv("RELAY_ORDER", "bobo,pi")
        order = rv._resolve_order()
        assert order == ["bobo", "pi"]
        # 下一位 = (index+1) % len(ORDER)，与主循环逻辑一致
        nxt = {name: order[(order.index(name) + 1) % len(order)] for name in order}
        assert nxt == {"bobo": "pi", "pi": "bobo"}
