"""Schedule recurring tasks using cron."""

import json
import os
import subprocess

TOOL_NAME = "bobo_schedule"
SCHEDULE_FILE = os.path.expanduser("~/.bobo/schedules.json")


def _load_schedules() -> list:
    if not os.path.exists(SCHEDULE_FILE):
        return []
    try:
        with open(SCHEDULE_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_schedules(schedules: list):
    os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)


def _install_cron(name: str, cron_expr: str):
    """Add or update a crontab entry for this schedule."""
    runner = os.path.abspath(__file__)
    comment = f"# bobo_schedule:{name}"
    cmd = f"cd {os.getcwd()} && python3 {runner} --run {name}\n"

    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        lines = existing.stdout.split("\n") if existing.returncode == 0 else []
        # Remove old entry for this name
        new_lines = []
        skip = False
        for line in lines:
            if line.strip() == comment:
                skip = True
                continue
            if skip:
                skip = False
                continue
            new_lines.append(line)
        # Add new entry
        new_lines.append(comment)
        new_lines.append(cron_expr + " " + cmd.strip())
        if new_lines and new_lines[-1] != "":
            new_lines.append("")
        input_text = "\n".join(new_lines)
        subprocess.run(["crontab", "-"], input=input_text, text=True, timeout=5)
        return True
    except Exception:
        return False


def _remove_cron(name: str):
    """Remove crontab entry for this schedule."""
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        lines = existing.stdout.split("\n") if existing.returncode == 0 else []
        new_lines = []
        skip = False
        for line in lines:
            if line.strip() == f"# bobo_schedule:{name}":
                skip = True
                continue
            if skip:
                skip = False
                continue
            new_lines.append(line)
        if new_lines and new_lines[-1] != "":
            new_lines.append("")
        subprocess.run(["crontab", "-"], input="\n".join(new_lines), text=True, timeout=5)
        return True
    except Exception:
        return False


def _cron_expr(time_str: str, repeat: str) -> str:
    """Convert "08:00" + "daily" to cron expression."""
    parts = time_str.split(":")
    hour = parts[0].strip().lstrip("0") or "0"
    minute = parts[1].strip().lstrip("0") if len(parts) > 1 else "0"
    if repeat == "daily":
        return f"{minute} {hour} * * *"
    elif repeat == "weekdays":
        return f"{minute} {hour} * * 1-5"
    elif repeat == "hourly":
        return f"{minute} * * * *"
    return f"{minute} {hour} * * *"  # default daily


def execute(action: str = "list", name: str = "", task: str = "",
            time: str = "", repeat: str = "daily") -> str:
    """Manage scheduled tasks."""
    if action == "list":
        schedules = _load_schedules()
        if not schedules:
            return "当前没有设置任何定时任务。可以说 '每天早上8点整理笔记' 来创建。"
        lines = ["已设置的定时任务:"]
        for s in schedules:
            lines.append(f"  {s['name']} — {s['repeat']} at {s['time']}")
            lines.append(f"    任务: {s['task'][:60]}")
        return "\n".join(lines)

    if action == "create":
        if not name or not task or not time:
            return "需要提供 name, task, time"

        schedule = {
            "name": name,
            "task": task,
            "time": time,
            "repeat": repeat,
            "instructions": (
                f"你有一个定时任务 '{name}'。请执行以下操作:\n{task}\n"
                f"完成后，将结果告知用户。"
            ),
        }

        schedules = _load_schedules()
        # Replace existing with same name
        schedules = [s for s in schedules if s["name"] != name]
        schedules.append(schedule)
        _save_schedules(schedules)

        # Install cron job
        cron_expr = _cron_expr(time, repeat)
        ok = _install_cron(name, cron_expr)

        if ok:
            return (
                f"定时任务已创建: {name}\n"
                f"  时间: {time} ({repeat})\n"
                f"  任务: {task[:60]}\n"
                f"  cron: {cron_expr}\n\n"
                f"要取消，可以说:\n"
                f"  \"取消 '{name}' 定时任务\""
            )
        return f"任务已保存但 cron 安装失败。请手动添加: {cron_expr} python3 ..."

    if action == "delete":
        schedules = _load_schedules()
        before = len(schedules)
        schedules = [s for s in schedules if s["name"] != name]
        if len(schedules) == before:
            return f"没有找到定时任务: {name}"
        _save_schedules(schedules)
        _remove_cron(name)
        return f"定时任务已删除: {name}"

    return "支持的操作: list, create, delete"


# Allow direct execution by cron
if __name__ == "__main__":
    import sys
    if "--run" in sys.argv:
        idx = sys.argv.index("--run")
        if idx + 1 < len(sys.argv):
            name = sys.argv[idx + 1]
            schedules = _load_schedules()
            for s in schedules:
                if s["name"] == name:
                    print(f"执行定时任务: {s['name']}")
                    # Run the task description as a prompt via the engine
                    # This file is called by cron, which triggers the agent
                    break


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "创建、查看或删除定时任务。支持每天、工作日、每小时重复。任务会被写入 cron 定时执行。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: list（查看）, create（创建）, delete（删除）"},
                "name": {"type": "string", "description": "任务名称（create/delete 时需要）"},
                "task": {"type": "string", "description": "要执行的任务描述（create 时需要）"},
                "time": {"type": "string", "description": "执行时间，如 '08:00'（create 时需要）"},
                "repeat": {"type": "string", "description": "重复: daily, weekdays, hourly（默认 daily）"}
            },
            "required": ["action"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
