# -*- coding: utf-8 -*-
"""
value_scorer.py - 基于投资学习价值的帖子评分模块
"""
import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from utils import get_artifacts_dir, logger


VALUED_POSTS_FILENAME = "valued_posts.json"

LOW_SIGNAL_PATTERNS = [
    r"^(嗯|嗯嗯|是的|好的|好|赞同|同意|谢谢|感谢|哈哈|哈哈哈|厉害|学习了|收到)$",
    r"^(顶|赞|支持|膜拜|牛|牛啊|说得好)$",
]

EMOTION_ONLY_PATTERNS = [
    r"^[\W_]+$",
    r"^(哈哈|呵呵|唉|哎|汗|哭|笑死)$",
]

PRINCIPLE_KEYWORDS = [
    "投资", "原则", "能力圈", "长期", "长期主义", "风险", "安全边际", "估值",
    "买公司", "商业模式", "护城河", "竞争优势", "管理层", "现金流", "资本配置",
    "ROE", "回报", "赔率", "仓位", "判断标准",
]

TRANSFERABLE_PATTERNS = [
    r"最重要的是", r"关键是", r"我一般", r"我通常", r"判断.*标准",
    r"不要只看", r"买股票就是买公司", r"投资就是", r"如果.*就",
]

BUSINESS_QUALITY_KEYWORDS = [
    "商业模式", "护城河", "品牌", "渠道", "复购", "竞争优势", "成本", "效率",
    "现金流", "利润", "盈利", "市场份额", "定价权", "管理层", "资本配置",
]

RISK_VALUATION_KEYWORDS = [
    "风险", "估值", "安全边际", "下行", "赔率", "仓位", "波动", "价格",
]

ANALYSIS_KEYWORDS = [
    "因为", "所以", "意味着", "说明", "逻辑", "判断", "认为", "结论",
]


def _normalize_text(value) -> str:
    """统一处理文本字段"""
    if value is None:
        return ""
    return str(value).strip()


def _build_text(post: dict) -> str:
    """拼接标题和正文"""
    title = _normalize_text(post.get("title"))
    content = _normalize_text(post.get("content"))
    return f"{title} {content}".strip()


def _has_any_keyword(text: str, keywords: list[str]) -> bool:
    """检测关键词命中"""
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _is_low_signal_short_reply(text: str) -> bool:
    """识别低信息量短回复"""
    compact = re.sub(r"\s+", "", text)
    if len(compact) > 12:
        return False
    return any(re.fullmatch(pattern, compact, re.IGNORECASE) for pattern in LOW_SIGNAL_PATTERNS)


def score_post_value(post: dict) -> tuple[int, list[str]]:
    """
    基于“学习投资思维”的价值对单条帖子打分。
    短内容不会天然被判为低价值，长度仅作为弱信号。
    """
    if not isinstance(post, dict):
        return 0, ["invalid_post"]

    text = _build_text(post)
    compact_text = re.sub(r"\s+", "", text)
    reasons = []
    score = 20 if compact_text else 0

    if not compact_text:
        return 0, ["empty_content"]

    if _is_low_signal_short_reply(compact_text):
        score -= 45
        reasons.append("pure_greeting_or_acknowledgement")

    if any(re.fullmatch(pattern, compact_text, re.IGNORECASE) for pattern in EMOTION_ONLY_PATTERNS):
        score -= 35
        reasons.append("pure_emotion_or_attitude")

    if "回复@" in text and len(compact_text) <= 30 and not _has_any_keyword(text, PRINCIPLE_KEYWORDS):
        score -= 18
        reasons.append("context_dependent_reply")

    if text.count("//@") >= 1 and not _has_any_keyword(text, PRINCIPLE_KEYWORDS + BUSINESS_QUALITY_KEYWORDS):
        score -= 15
        reasons.append("mostly_repeats_or_forwards")

    if _has_any_keyword(text, PRINCIPLE_KEYWORDS):
        score += 30
        reasons.append("contains_investment_principle")

    if any(re.search(pattern, text) for pattern in TRANSFERABLE_PATTERNS):
        score += 20
        reasons.append("has_transferable_methodology")

    if _has_any_keyword(text, BUSINESS_QUALITY_KEYWORDS):
        score += 18
        reasons.append("discusses_business_quality")

    if _has_any_keyword(text, RISK_VALUATION_KEYWORDS):
        score += 16
        reasons.append("shows_risk_or_valuation_awareness")

    if _has_any_keyword(text, ANALYSIS_KEYWORDS) and _has_any_keyword(text, BUSINESS_QUALITY_KEYWORDS + PRINCIPLE_KEYWORDS):
        score += 12
        reasons.append("provides_logical_analysis")

    if len(compact_text) >= 18 and "回复@" not in text:
        score += 6
        reasons.append("independently_readable")
    elif _has_any_keyword(text, PRINCIPLE_KEYWORDS) and "回复@" not in text:
        score += 6
        reasons.append("independently_readable")

    if re.search(r"\d", text) or "%" in text:
        score += 6
        reasons.append("has_supporting_details")

    if len(compact_text) < 6 and not _has_any_keyword(text, PRINCIPLE_KEYWORDS):
        score -= 10
        reasons.append("low_information_density")
    elif len(compact_text) > 180:
        score += 4
        reasons.append("has_substantive_detail")

    score = max(0, min(100, score))
    reasons = list(dict.fromkeys(reasons))
    return score, reasons


def _score_to_level(score: int) -> str:
    """根据分数映射价值等级"""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def value_post(post: dict) -> dict:
    """为帖子补充价值评分字段"""
    score, reasons = score_post_value(post)
    enriched = dict(post)
    enriched["value_score"] = score
    enriched["value_level"] = _score_to_level(score)
    enriched["value_reasons"] = reasons
    return enriched


def value_posts(posts: list[dict]) -> list[dict]:
    """批量计算帖子价值"""
    valued = [value_post(post) for post in posts]
    valued.sort(
        key=lambda post: (
            {"high": 2, "medium": 1, "low": 0}.get(post.get("value_level"), 0),
            post.get("value_score", 0),
            post.get("published_at", ""),
        ),
        reverse=True,
    )
    return valued


def _write_json(path: Path, data):
    """写入 JSON 文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def score_clean_posts(clean_posts_path: Optional[Path] = None) -> tuple[Path, dict]:
    """读取 clean_posts.json 并生成 valued_posts.json"""
    if clean_posts_path is None:
        clean_posts_path = get_artifacts_dir() / "clean_posts.json"

    if not clean_posts_path.exists():
        raise FileNotFoundError(f"clean_posts.json 不存在: {clean_posts_path}")

    with open(clean_posts_path, "r", encoding="utf-8") as f:
        clean_posts = json.load(f)

    valued_posts = value_posts(clean_posts)
    output_path = get_artifacts_dir() / VALUED_POSTS_FILENAME
    _write_json(output_path, valued_posts)

    level_counter = Counter(post.get("value_level", "low") for post in valued_posts)
    summary = {
        "total_posts": len(valued_posts),
        "high_count": level_counter.get("high", 0),
        "medium_count": level_counter.get("medium", 0),
        "low_count": level_counter.get("low", 0),
    }

    print("\n📌 Step 3: 发言价值判断...")
    print(f"价值判断输出: {output_path}")
    print(
        f"价值分布: high={summary['high_count']}, "
        f"medium={summary['medium_count']}, "
        f"low={summary['low_count']}"
    )
    logger.info(
        "价值判断完成: 总计%s条, high=%s, medium=%s, low=%s",
        summary["total_posts"],
        summary["high_count"],
        summary["medium_count"],
        summary["low_count"],
    )
    return output_path, summary
