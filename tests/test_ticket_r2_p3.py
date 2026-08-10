"""TICKET-R2-P3 验收测试：relay 进程生命周期管理（单实例锁 / venv 解释器 / office_manager 托管）。

病历（TICKET-R2 阶段0，2026-08-10 23:03–23:33 首跑取证）：
  - 23:22 同一 office 重复启动 4 次 relay、双实例并发（v1 pgrep 锁在
    cmdline 变体下漏判，日志双重行实锤）
  - 一次 python: No such file or directory（用了框架 Python 而非项目 venv）

施工要求（票 R2-P3）：
  1. 单实例锁：启动前查 relay.state 存活进程（state pid 为唯一事实源），
     pgrep 仅作兜底（拦旧版未写 state 的 relay）
  2. 启动改用项目 .venv 解释器（$RELAY_PYTHON 可覆盖；系统解释器兜底，
     绝不裸用 'python3'）
  3. office_manager launch/teardown 接管 relay 进程唯一性 / 解释器 /
     崩溃重启（teardown 定向停本 session，不全量 pkill）

全程 mock tmux + 临时目录，不碰真实 relay_v2 目录、不碰真实库。
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, ".")
import tools.team_relay_v2 as rv
import tools.office_manager as om


# ── 1. pid 探活 ──

class TestPidAlive:
    def test_alive_self_pid(self):
        assert rv._pid_alive(os.getpid()) is True

    def test_dead_killed_pid(self):
        """已退出的子进程 pid → 判死（ProcessLookupError 分支）"""
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        assert rv._pid_alive(p.pid) is False

    def test_invalid_pids(self):
        assert rv._pid_alive(0) is False
        assert rv._pid_alive(None) is False
        assert rv._pid_alive(-1) is False


# ── 2. 单实例锁（state pid 事实源 + pgrep 兜底）──

class TestSingleInstanceLock:
    def test_state_pid_alive_refuses(self, tmp_path, monkeypatch):
        """state 记录存活 pid → 拒绝启动（双实例防线）"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        rv.save_state({"pid": os.getpid(), "started_at": "t",
                       "bobo": 0, "hermes": 0, "claude": 0, "pi": 0})
        assert rv._acquire_single_instance() is False

    def test_state_pid_dead_acquires(self, tmp_path, monkeypatch):
        """state pid 已死（陈旧）且 pgrep 无命中 → 获得锁"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        rv.save_state({"pid": p.pid, "bobo": 0, "hermes": 0,
                       "claude": 0, "pi": 0})
        monkeypatch.setattr(rv, "_pgrep_relay", lambda: [])
        assert rv._acquire_single_instance() is True

    def test_pgrep_fallback_refuses(self, tmp_path, monkeypatch):
        """state 无存活 pid 但 pgrep 兜底发现同类 relay → 拒绝（拦旧版）"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        rv.save_state({"bobo": 0, "hermes": 0, "claude": 0, "pi": 0})
        monkeypatch.setattr(rv, "_pgrep_relay", lambda: ["424242"])
        assert rv._acquire_single_instance() is False

    def test_state_pid_roundtrip(self, tmp_path, monkeypatch):
        """pid + started_at 随 relay.state 持久化（接管/心跳的事实源）"""
        monkeypatch.setattr(rv, "STATE_PATH", str(tmp_path / "relay.state"))
        rv.save_state({"pid": 12345, "started_at": "2026-08-10T23:00:00",
                       "bobo": 3, "hermes": 0, "claude": 1, "pi": 0})
        st = rv.load_state()
        assert st["pid"] == 12345
        assert st["started_at"] == "2026-08-10T23:00:00"
        assert rv._state_pid() == 12345
        # 缺失/损坏 pid → 0
        rv.save_state({"bobo": 1})
        assert rv._state_pid() == 0


# ── 3. venv 解释器解析 ──

class TestResolveRelayPython:
    def test_env_override(self, monkeypatch):
        """$RELAY_PYTHON 显式指定优先"""
        monkeypatch.setenv("RELAY_PYTHON", "/tmp/fake-python")
        assert om._resolve_relay_python() == "/tmp/fake-python"

    def test_venv_preferred(self, tmp_path, monkeypatch):
        """项目 .venv 存在 → 优先使用（病历修复：不再用框架 Python）"""
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        monkeypatch.delenv("RELAY_PYTHON", raising=False)
        venv_py = tmp_path / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True)
        venv_py.write_text("#!")
        venv_py.chmod(0o755)
        assert om._resolve_relay_python() == str(venv_py)

    def test_fallback_sys_executable(self, tmp_path, monkeypatch):
        """无 venv、无 env → 当前解释器兜底（绝不裸用 'python3'）"""
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        monkeypatch.delenv("RELAY_PYTHON", raising=False)
        assert om._resolve_relay_python() == sys.executable

    def test_launch_cmd_uses_venv(self, tmp_path, monkeypatch):
        """launch 命令：RELAY_SESSION + nohup + venv 解释器 + 绝对脚本路径"""
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        monkeypatch.delenv("RELAY_PYTHON", raising=False)
        venv_py = tmp_path / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True)
        venv_py.write_text("#!")
        venv_py.chmod(0o755)
        cmd = om._relay_launch_cmd("office_x")
        assert cmd.startswith("RELAY_SESSION=office_x nohup")
        assert str(venv_py) in cmd
        assert "team_relay_v2.py" in cmd
        assert "nohup" in cmd
        # 绝不裸用 'python3 tools/team_relay_v2.py'（病历）
        assert "python3 tools/team_relay_v2.py" not in cmd

    def test_launch_cmd_fallback_interpreter(self, tmp_path, monkeypatch):
        """无 venv → sys.executable 进入命令（不是裸 python3）"""
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        monkeypatch.delenv("RELAY_PYTHON", raising=False)
        cmd = om._relay_launch_cmd("office_y")
        assert sys.executable in cmd


# ── 4. teardown 定向停（不全量 pkill）──

class TestRelayStopScoped:
    def test_stop_uses_recorded_pid_and_session(self, monkeypatch):
        """台账 pid 存活 → kill pid + RELAY_SESSION 匹配，绝不全量 pkill"""
        monkeypatch.setattr(om, "_pid_alive", lambda pid: True)
        cmds = om._relay_stop_cmds("office_mine", 12345)
        joined = "\n".join(cmds)
        assert "kill 12345" in joined
        assert "RELAY_SESSION=office_mine" in joined
        assert "pkill -f 'team_relay_v2.py'" not in joined

    def test_stop_fallback_session_only(self, monkeypatch):
        """台账无 pid（或已死）→ 仅按 RELAY_SESSION 匹配兜底"""
        monkeypatch.setattr(om, "_pid_alive", lambda pid: False)
        cmds = om._relay_stop_cmds("office_y", None)
        joined = "\n".join(cmds)
        assert "RELAY_SESSION=office_y" in joined
        assert not any(c.startswith("kill ") for c in cmds)  # 无定向 kill
        assert "pkill -f 'team_relay_v2.py'" not in joined


# ── 5. office 侧 state pid 读写（teardown 释放单实例）──

class TestOfficeStatePid:
    def test_state_pid_helpers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        st = tmp_path / "data" / "relay_v2"
        st.mkdir(parents=True)
        (st / "relay.state").write_text('{"pid": 12345, "bobo": 2}')
        assert om._state_relay_pid() == 12345
        om._clear_state_pid()
        assert om._state_relay_pid() == 0

    def test_state_pid_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(om, "_ROOT", str(tmp_path))
        assert om._state_relay_pid() == 0
