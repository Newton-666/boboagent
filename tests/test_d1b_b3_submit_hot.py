"""D-1b B3 回归测试：setup.submit 写 .env 后，setup.status 立即返回 provider_configured:true。

Kimi 终审验收标准：submit 后 status 立即 configured，不许要求重启。
修复：handle_setup_submit 写 .env 后同步刷新 os.environ + config 缓存（config.refresh_config_cache）。
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _env_backup():
    import config
    env_file = config.BOBO_DATA_DIR / ".env"
    return env_file, (env_file.read_text() if env_file.exists() else None)


def _env_restore(env_file, backup):
    if backup is not None:
        env_file.write_text(backup)
    else:
        env_file.unlink(missing_ok=True)
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("BOBO_PROVIDER", None)


def test_setup_submit_then_status_configured():
    env_file, backup = _env_backup()
    try:
        # 前置态：清成"未配置"
        if env_file.exists():
            lines = [
                l for l in env_file.read_text().split("\n")
                if not l.startswith("DEEPSEEK_API_KEY=")
            ]
            env_file.write_text("\n".join(lines))
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("BOBO_PROVIDER", None)

        import config
        config.refresh_config_cache()  # 终审修复：清 provider 缓存，防全量跑时前序测试污染前置态

        import importlib
        from bobo_tui_gateway.handlers import configs
        importlib.reload(configs)

        before = configs.handle_setup_status({}, "r1")
        assert before["result"]["provider_configured"] is False, "前置态应为未配置"

        resp = configs.handle_setup_submit(
            {"provider": "deepseek", "api_key": "sk-test-d1b-12345"}, "r2"
        )
        assert resp["result"]["ok"] is True, f"submit 应成功: {resp}"

        after = configs.handle_setup_status({}, "r3")
        assert after["result"]["provider_configured"] is True, \
            "B3 FAIL: submit 后 status 应立即 configured:true（不许重启）"
        assert os.environ.get("DEEPSEEK_API_KEY") == "sk-test-d1b-12345", \
            "os.environ 未同步刷新"
    finally:
        _env_restore(env_file, backup)


def test_config_refresh_cache_resets_provider():
    """config.refresh_config_cache() 应重置 provider 缓存（B3 热生效的基础设施）。"""
    import config
    config._provider_cache = {"name": "stale"}
    config.refresh_config_cache()
    assert config._provider_cache is None, "refresh 后缓存应为 None（下次访问重新 resolve）"
