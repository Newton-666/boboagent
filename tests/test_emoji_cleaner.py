"""Unit tests for core/emoji_cleaner.py — remove_emojis function."""

import pytest
from core.emoji_cleaner import remove_emojis

# The 25 hardcoded emojis from the source, listed for verification
ALL_EMOJIS = [
    '😊', '🎉', '✅', '❌', '👍', '👋', '🙏', '💡', '📝', '🔍',
    '📂', '🏷️', '⚙️', '🔧', '📧', '📅', '⏰', '💾', '🔄', '✨',
    '🔥', '💪', '🤔', '🧠', '💭',
]


def test_removes_known_emojis():
    """A known emoji between words is removed, leaving the surrounding spaces."""
    result = remove_emojis("hello 😊 world")
    # 😊 is stripped; the spaces on either side remain → "hello  world"
    assert result == "hello  world"


def test_preserves_non_emoji():
    """Plain text with no emoji characters is returned unchanged."""
    text = "普通文本 123"
    assert remove_emojis(text) == text


def test_handles_empty_string():
    """An empty string is returned as-is."""
    assert remove_emojis("") == ""


def test_removes_all_25_emojis():
    """Every emoji in the hardcoded list is individually removed."""
    for emoji in ALL_EMOJIS:
        test_str = f"pre{emoji}post"
        result = remove_emojis(test_str)
        assert emoji not in result, f"Emoji {repr(emoji)} was not removed"
        assert result == "prepost", f"Expected 'prepost', got {repr(result)}"
