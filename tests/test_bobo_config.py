'''bobo_config.py 单元测试 — view/set/register'''

from unittest.mock import patch, MagicMock
import os

import pytest

from tools import bobo_config


class TestBoboConfig:
    '''bobo_config.execute() — view 和 set 动作'''

    def test_view_shows_config(self):
        with patch.dict(os.environ, {
            "BOBO_PROVIDER": "test-provider",
            "API_MODEL_NAME": "test-model",
            "DEEPSEEK_API_KEY": "sk-xxx",
            "OBSIDIAN_VAULT": "/tmp/obsidian",
        }, clear=False):
            result = bobo_config.execute(action="view")
            assert "test-provider" in result
            assert "已配置" in result

    def test_view_shows_key_not_configured(self):
        with patch.dict(os.environ, {
            "BOBO_PROVIDER": "deepseek",
            "API_MODEL_NAME": "some-model",
        }, clear=True):
            result = bobo_config.execute(action="view")
            assert "未配置" in result

    def test_set_updates_env_and_file(self):
        with patch("tools.bobo_config.os.environ") as mock_env:
            with patch("tools.bobo_config.os.path.exists", return_value=False):
                with patch("tools.bobo_config.os.makedirs"):
                    with patch("builtins.open") as mock_open:
                        mock_file = MagicMock()
                        mock_open.return_value.__enter__.return_value = mock_file
                        result = bobo_config.execute(action="set", key="TEST_KEY", value="test_val")
                        assert "已更新" in result
                        mock_file.write.assert_called_once()

    def test_set_appends_to_existing_file(self):
        with patch("tools.bobo_config.os.path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_read = MagicMock()
                mock_read.__enter__.return_value.__iter__.return_value = iter([
                    "OTHER_KEY=old\n"
                ])
                mock_open.side_effect = [mock_read, MagicMock()]
                with patch("tools.bobo_config.os.environ") as mock_env:
                    result = bobo_config.execute(
                        action="set", key="TEST_KEY", value="new_val"
                    )
                    assert "已更新" in result

    def test_set_updates_existing_key(self):
        with patch("tools.bobo_config.os.path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_read = MagicMock()
                mock_read.__enter__.return_value.__iter__.return_value = iter([
                    "TEST_KEY=old\n",
                    "OTHER_KEY=val\n",
                ])
                mock_write = MagicMock()
                mock_open.side_effect = [mock_read, mock_write]
                with patch("tools.bobo_config.os.environ") as mock_env:
                    result = bobo_config.execute(
                        action="set", key="TEST_KEY", value="new_val"
                    )
                    assert "已更新" in result

    def test_set_no_key_value(self):
        result = bobo_config.execute(action="set")
        assert "请提供 key 和 value" in result

    def test_invalid_action(self):
        result = bobo_config.execute(action="invalid")
        assert "支持的操作" in result

    def test_register_schema(self):
        registry = {}
        bobo_config.register(lambda n, f, s: registry.update({n: (f, s)}))
        assert "bobo_config" in registry
        schema = registry["bobo_config"][1]
        props = schema["function"]["parameters"]["properties"]
        assert "action" in props
        assert "key" in props
        assert "value" in props
