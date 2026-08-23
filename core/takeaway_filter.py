"""core/takeaway_filter.py — 沉淀预筛闸（E4c：从 engine 搬出，零 API 成本的价值判断）。

纯函数：判断本轮对话是否值得调用 LLM 提取 takeaways。
优先级：放行信号 > 跳过条件。放行信号命中任一即放行，跳过条件命中任一即跳过。
"""
import re

VALUE_KEYWORDS = re.compile(
    r'决定|以后|记住|偏好|喜欢|习惯|以后都|改成|不要再用|规则|流程|'
    r'选型|方案定|上线|部署|密码|密钥|配置'
)
CONFIRM_PATTERN = re.compile(
    r'^(好的|好|嗯|行|ok|OK|谢谢|继续|收到|对|是的?|可以的?)[。！!~\s]*$'
)


def takeaway_worthy(user_msg: str, asst_msg: str) -> bool:
    """纯本地预筛：True → 放行（值得调 LLM）；False → 跳过（零 API 成本）。"""
    user_stripped = user_msg.strip()
    asst_stripped = asst_msg.strip()

    # ── 放行信号（命中任一即放行，宁可多打不可漏记） ──
    if VALUE_KEYWORDS.search(user_stripped + asst_stripped):
        return True
    if len(user_stripped) > 100 or len(asst_stripped) > 300:
        return True

    # ── 跳过条件（命中任一即跳过） ──
    if len(user_stripped) < 40 and len(asst_stripped) < 40:
        return False
    if CONFIRM_PATTERN.match(user_stripped):
        return False
    if len(asst_stripped) < 60:
        return False
    return False
