"""emoji_cleaner.py — 移除 LLM 回复中的 emoji 字符。"""


def remove_emojis(text: str) -> str:
    emojis = ['😊', '🎉', '✅', '❌', '👍', '👋', '🙏', '💡', '📝', '🔍', '📂', '🏷️', '⚙️', '🔧', '📧', '📅', '⏰', '💾', '🔄', '✨', '🔥', '💪', '🤔', '🧠', '💭']
    for em in emojis:
        text = text.replace(em, '')
    return text
