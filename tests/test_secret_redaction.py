"""Tests for secret/key redaction in ToolRunnerMixin._redact_secrets.

Secrets that reach the LLM are a serious leak vector. These tests verify
every pattern in SECRET_PATTERNS catches its intended secret format.
"""

import pytest
from core.engine import Engine
from core.tool_executor import execute_tool


@pytest.fixture
def engine():
    from tests.mock_llm import MockLLMCaller, text_response
    caller = MockLLMCaller([text_response("ok")])
    return Engine(caller, execute_tool, test_mode=True)


class TestRedactionPatterns:
    """Each pattern in SECRET_PATTERNS should match at least one real-world example."""

    def test_deepseek_key(self, engine):
        result = engine._redact_secrets("My key is sk-d61a48af613245b3b22961dea846779e")
        assert "[REDACTED]" in result
        assert "sk-d61a48af" not in result

    def test_anthropic_key(self, engine):
        result = engine._redact_secrets("Key: sk-ant-api03-abc123def456ghijklmnopqrstuv")
        assert "[REDACTED]" in result
        assert "sk-ant-" not in result

    def test_github_pat_ghp(self, engine):
        result = engine._redact_secrets("Token: ghp_abcdefghijklmnopqrstuvwxyz1234")
        assert "[REDACTED]" in result
        assert "ghp_" not in result

    def test_github_pat_gho(self, engine):
        result = engine._redact_secrets("OAuth: gho_1234567890abcdefghijklmnop")
        assert "[REDACTED]" in result

    def test_github_pat_ghs(self, engine):
        result = engine._redact_secrets("Server: ghs_server_pat_abcdefghijklmnopqrst")
        assert "[REDACTED]" in result

    def test_github_pat_ghu(self, engine):
        result = engine._redact_secrets("User: ghu_user_token_abcdefghijklmnop")
        assert "[REDACTED]" in result

    def test_github_pat_ghf(self, engine):
        result = engine._redact_secrets("Fine: ghf_fine_grained_token_abcdefgh")
        assert "[REDACTED]" in result

    def test_aws_access_key(self, engine):
        result = engine._redact_secrets("AWS: AKIAIOSFODNN7EXAMPLE")  # example format
        assert "[REDACTED]" in result
        assert "AKIA" not in result

    def test_private_key_block(self, engine):
        key_block = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3...
-----END RSA PRIVATE KEY-----"""
        result = engine._redact_secrets(key_block)
        assert "[REDACTED]" in result

    def test_private_key_dsa(self, engine):
        result = engine._redact_secrets("Key: -----BEGIN DSA PRIVATE KEY----- abc")
        assert "[REDACTED]" in result

    def test_private_key_openssh(self, engine):
        result = engine._redact_secrets("Key: -----BEGIN OPENSSH PRIVATE KEY----- abc")
        assert "[REDACTED]" in result

    def test_env_var_style_snake_case(self, engine):
        result = engine._redact_secrets("API_KEY = sk-abcdefghijklmnopqrstuv")
        assert "[REDACTED]" in result

    def test_env_var_style_secret(self, engine):
        result = engine._redact_secrets("SECRET_TOKEN = super-secret-value-12345")
        assert "[REDACTED]" in result

    def test_env_var_style_password(self, engine):
        result = engine._redact_secrets("PASSWORD = hunter2abc")
        assert "[REDACTED]" in result

    def test_bearer_token(self, engine):
        result = engine._redact_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop")
        assert "[REDACTED]" in result

    def test_password_colon_style(self, engine):
        result = engine._redact_secrets("password: hunter2secret")
        assert "[REDACTED]" in result

    def test_pwd_equals_style(self, engine):
        result = engine._redact_secrets("pwd = mypassword123")
        assert "[REDACTED]" in result

    def test_multiple_secrets_in_one_string(self, engine):
        text = "Key1: sk-deepseekkey1234567890abc, Key2: ghp_githubtoken1234567890"
        result = engine._redact_secrets(text)
        assert "sk-deepseek" not in result
        assert "ghp_github" not in result
        # Should have at least one [REDACTED], potentially two
        assert "[REDACTED]" in result


class TestNoFalsePositives:
    """Ensure redaction doesn't eat legitimate content."""

    def test_normal_text_passes_through(self, engine):
        text = "Hello World! The weather is nice today."
        assert engine._redact_secrets(text) == text

    def test_code_snippet_not_redacted(self, engine):
        code = """
def my_function():
    api = "https://example.com"
    key = "not-a-real-key"
    return api + key
"""
        result = engine._redact_secrets(code)
        assert "https://example.com" in result
        assert "not-a-real-key" in result

    def test_short_values_not_falsely_redacted(self, engine):
        # Short values (< 8 chars after =) should NOT be redacted
        text = "key = short"
        result = engine._redact_secrets(text)
        assert "[REDACTED]" not in result

    def test_partial_match_not_overly_greedy(self, engine):
        # "sk-" alone without enough trailing chars should not be redacted
        text = "prefix sk- short"
        result = engine._redact_secrets(text)
        # "sk-" with only "short" (5 chars) doesn't meet the 20-char minimum
        assert "sk-" in result
