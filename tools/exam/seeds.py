"""tools/exam/seeds.py — 埋点池（出题人：Kimi；考生 bobo 永不可见答案结构）

三类埋点（TICKET-GC1 框架，不许擅改）：
  ① fact   事实型：随机代号/数字/颜色物品（如「灯塔-47」）
  ② pref   偏好型：指令性陈述（如「以后周报要英文」）
  ③ detail 细节型：限定词陷阱（如「猫是领养的不是买的」，专杀模糊记忆）

铁律：
  - 答案现场随机生成，绝不出现/推理自任何既有文档、笔记、训练常识；
  - 埋点以"随口一说"的自然口吻注入，考生不知道哪句是考点（暗牌原则）；
  - 两次生成不得重复（有单测保证）。
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field


@dataclass
class Seed:
    """一条埋点考题。"""
    kind: str                      # fact / pref / detail
    inject: str                    # 注入语（考试中"用户随口说"的话）
    question: str                  # 到点提问
    must_have: list[str]           # 答卷必须包含的要点
    traps: list[str] = field(default_factory=list)  # 陷阱词（无否定语境出现即细节错）
    seed_id: str = ""


# ── 随机素材库（组合空间足够大，防背诵；与真实文档零关联）──

_CODENAME_PREFIX = ["灯塔", "猎户", "琥珀", "雪线", "熔炉", "回声", "断崖", "季风", "石墨", "萤火"]
_CODENAME_SUFFIX = ["计划", "工程", "行动", "项目"]
_FAKE_NUMBERS = [47, 63, 89, 125, 238, 371, 512, 666, 804, 977]

_PET_NAMES = ["年糕", "煤球", "豆包", "布丁", "栗子", "抹布", "警长", "汤圆", "花生", "可乐"]
_DETAIL_SUBJECTS = [
    ("猫", "领养的", "买的"),
    ("咖啡机", "朋友送的", "自己买的"),
    ("吉他", "二手淘的", "新买的"),
    ("自行车", "组装起来的", "整车买的"),
    ("相机", "叔叔留下来的", "店里买的"),
]

_PREF_TOPICS = [
    ("周报", "要用英文"),
    ("会议纪要", "只要三点式列表"),
    ("每日复盘", "放在早上 6 点半发"),
    ("代码评审意见", "先讲风险再讲优点"),
    ("进度汇报", "不许用「大概」「可能」这类词"),
]

_COLORS = ["墨绿色", "哑光黑", "米白色", "藏蓝色", "焦糖色"]
_ITEMS = ["机械键盘", "背包", "水杯", "台灯", "耳机"]


def _rand_id(rng: random.Random) -> str:
    return "".join(rng.choices(string.ascii_lowercase + string.digits, k=6))


def gen_fact_seed(rng: random.Random) -> Seed:
    """① 事实型：随机项目代号。"""
    name = rng.choice(_CODENAME_PREFIX) + "-" + str(rng.choice(_FAKE_NUMBERS))
    kind = rng.choice(_CODENAME_SUFFIX)
    return Seed(
        kind="fact",
        inject=f"对了顺便说一句，我们内部把新东西定名叫「{name}」{kind}，你记一下，之后可能会提到。",
        question="我之前跟你提过一个内部代号，叫什么？把全名说出来。",
        must_have=[name],
        seed_id=_rand_id(rng),
    )


def gen_color_seed(rng: random.Random) -> Seed:
    """① 事实型变体：随机颜色+物品（纯随机配对，无常识可依）。"""
    color = rng.choice(_COLORS)
    item = rng.choice(_ITEMS)
    return Seed(
        kind="fact",
        inject=f"我昨天刚换了个{color}的{item}，挺满意的，随口跟你说一声。",
        question=f"我昨天新换的那个{item}，是什么颜色的？",
        must_have=[color],  # 提问已点名物品，答卷只需答对颜色
        seed_id=_rand_id(rng),
    )


def gen_pref_seed(rng: random.Random) -> Seed:
    """② 偏好型：指令性陈述。"""
    topic, rule = rng.choice(_PREF_TOPICS)
    return Seed(
        kind="pref",
        inject=f"跟你定个规矩：以后我的{topic}{rule}，别搞错了。",
        question="我之前给你定过一个关于日常汇报或文档的规矩，内容是什么？",
        must_have=[topic, rule],
        seed_id=_rand_id(rng),
    )


def gen_detail_seed(rng: random.Random) -> Seed:
    """③ 细节型：限定词陷阱。"""
    subj, truth, trap = rng.choice(_DETAIL_SUBJECTS)
    name = rng.choice(_PET_NAMES)
    return Seed(
        kind="detail",
        inject=f"我家{subj}叫{name}，是{truth}，不是{trap}的，这点你记清楚。",
        question=f"我家那个{subj}，叫什么名字？它是怎么来的？",
        must_have=[name, truth],
        traps=[trap],
        seed_id=_rand_id(rng),
    )


def make_exam_set(rng: random.Random | None = None) -> list[Seed]:
    """生成一套完整考卷埋点（4 题：fact×2 + pref×1 + detail×1）。"""
    rng = rng or random.Random()
    seeds = [gen_fact_seed(rng), gen_pref_seed(rng), gen_detail_seed(rng), gen_color_seed(rng)]
    assert len({s.seed_id for s in seeds}) == len(seeds)
    return seeds


# ── 杂谈话题池（填满上下文用；严禁与埋点内容相关）──

_FILLER_TOPICS = [
    "跟我聊聊为什么天空是蓝色的。",
    "你觉得跑步和游泳哪个对膝盖更友好？",
    "帮我分析一下速溶咖啡和手冲的成本差异。",
    "说说睡眠周期是怎么回事。",
    "为什么飞机餐总被人说难吃？",
    "聊聊比特币挖矿到底在算什么。",
    "帮我比较一下租房和买房的现金流差异。",
    "为什么冬天静电特别多？",
    "说说记忆宫殿这种记忆法的原理。",
    "你觉得电子书会完全取代纸质书吗？",
    "聊聊台风是怎么形成和命名的。",
    "为什么镜子里的字是左右反的而不是上下反的？",
    "说说人体为什么需要补充盐分。",
    "帮我解释一下什么是机会成本。",
    "为什么蚊子专叮某些人？",
    "聊聊深海鱼为什么长得那么奇怪。",
    "说说 5G 和 4G 的本质区别是什么。",
    "为什么下雨天睡得特别香？",
    "帮我分析一下定期存款和货币基金的区别。",
    "聊聊植物晚上到底睡不睡觉。",
]


def filler_prompts(rng: random.Random, n: int) -> list[str]:
    """取 n 条杂谈话题（不放回抽样，避免同轮重复）。"""
    return rng.sample(_FILLER_TOPICS, min(n, len(_FILLER_TOPICS)))
