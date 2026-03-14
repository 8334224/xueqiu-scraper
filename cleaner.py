# -*- coding: utf-8 -*-
"""
cleaner.py - 帖子数据清洗与过滤模块
"""
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from utils import logger, get_artifacts_dir


def parse_xueqiu_time(time_str: Optional[str]) -> Optional[datetime]:
    """
    解析雪球网时间字符串为 datetime 对象
    
    支持格式:
    - "刚刚" -> 当前时间
    - "5分钟前" -> 5分钟前
    - "2小时前" -> 2小时前
    - "昨天 09:30" -> 昨天
    - "今天 10:30" -> 今天
    - "03-14 10:30" -> 今年3月14日
    - "2024-03-14 10:30" -> 指定日期
    - "2024-03-14" -> 指定日期
    """
    if not time_str:
        return None
    
    time_str = time_str.strip()
    now = datetime.now()
    
    # "刚刚"
    if time_str == "刚刚":
        return now
    
    # "X分钟前"
    match = re.match(r'^(\d+)\s*分钟前', time_str)
    if match:
        minutes = int(match.group(1))
        return now - timedelta(minutes=minutes)
    
    # "X小时前"
    match = re.match(r'^(\d+)\s*小时前', time_str)
    if match:
        hours = int(match.group(1))
        return now - timedelta(hours=hours)
    
    # "昨天 HH:MM"
    match = re.match(r'^昨天\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        yesterday = now - timedelta(days=1)
        hour = int(match.group(1))
        minute = int(match.group(2))
        return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # "今天 HH:MM"
    match = re.match(r'^今天\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # "MM-DD HH:MM" 格式 (雪球常见)
    match = re.match(r'^(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})', time_str)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        hour = int(match.group(3))
        minute = int(match.group(4))
        try:
            # 假设是当前年份
            return now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return None
    
    # "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD HH:MM:SS"
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})', time_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        try:
            return datetime(year, month, day, hour, minute, 0)
        except ValueError:
            return None
    
    # "YYYY-MM-DD"
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', time_str)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return datetime(year, month, day, 0, 0, 0)
        except ValueError:
            return None
    
    return None


def clean_post(raw_post: dict, collected_at: str) -> dict:
    """
    清洗单条帖子数据，统一字段格式
    """
    # 基础字段提取
    title = raw_post.get('title', '')
    content = raw_post.get('content', '')
    url = raw_post.get('url', '')
    
    # 尝试多种时间字段来源
    time_raw = None
    for key in ['time', 'datetime', 'publish_time', 'created_at', 'date']:
        if key in raw_post and raw_post[key]:
            time_raw = str(raw_post[key]).strip()
            break
    
    # 解析时间
    published_at = None
    time_parse_status = "missing_time"
    if time_raw:
        parsed = parse_xueqiu_time(time_raw)
        if parsed:
            published_at = parsed.isoformat()
            time_parse_status = "parsed"
        else:
            time_parse_status = "time_parse_failed"

    # 构建清洗后的数据结构
    clean_post = {
        "title": title,
        "content": content,
        "url": url,
        "published_at_raw": time_raw,
        "published_at": published_at,
        "collected_at": collected_at,
        "_time_parse_status": time_parse_status,
    }
    
    return clean_post


def _normalize_text(value) -> str:
    """统一处理文本字段"""
    if value is None:
        return ""
    return str(value).strip()


def _get_exclusion_reasons(post: dict, seven_days_ago: datetime) -> list[str]:
    """判断帖子被排除的原因"""
    reasons = []

    if not isinstance(post, dict):
        return ["invalid_post"]

    title = _normalize_text(post.get("title"))
    content = _normalize_text(post.get("content"))
    if not title and not content:
        reasons.append("empty_content")

    time_parse_status = post.get("_time_parse_status")
    published_at_str = post.get("published_at")
    published_at_raw = _normalize_text(post.get("published_at_raw"))

    if not published_at_str:
        if time_parse_status == "time_parse_failed":
            reasons.append("time_parse_failed")
        elif not published_at_raw:
            reasons.append("missing_time")
        else:
            reasons.append("missing_time")
    else:
        try:
            published_at = datetime.fromisoformat(published_at_str)
            if published_at < seven_days_ago:
                reasons.append("older_than_window")
        except (ValueError, TypeError):
            reasons.append("time_parse_failed")

    if not reasons:
        return []

    return list(dict.fromkeys(reasons))


def _build_excluded_post_record(post: dict, reasons: list[str]) -> dict:
    """构建排除帖子记录"""
    record = {
        "title": post.get("title", ""),
        "content": post.get("content", ""),
        "url": post.get("url", ""),
        "published_at_raw": post.get("published_at_raw"),
        "published_at": post.get("published_at"),
        "collected_at": post.get("collected_at"),
        "reasons": reasons,
    }
    return record


def _write_json_file(path: Path, data):
    """写入 JSON 文件"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_cleaning_summary(raw_count: int, clean_count: int, excluded_posts: list[dict]) -> dict:
    """构建清洗汇总统计"""
    reason_counter = Counter()
    for post in excluded_posts:
        reason_counter.update(post.get("reasons", []))

    return {
        "raw_count": raw_count,
        "clean_count": clean_count,
        "excluded_count": len(excluded_posts),
        "excluded_by_reason": dict(sorted(reason_counter.items())),
    }


def filter_last_7_days(posts: list, days: int = 7) -> tuple[list, list]:
    """
    过滤出最近 N 天的帖子
    
    Returns:
        tuple: (符合条件的帖子列表, 被排除的帖子列表)
    """
    now = datetime.now()
    window_start = now - timedelta(days=days)
    
    filtered = []
    excluded = []
    
    for post in posts:
        reasons = _get_exclusion_reasons(post, window_start)
        if reasons:
            excluded.append(_build_excluded_post_record(post, reasons))
        else:
            filtered.append(post)
    
    return filtered, excluded


def clean_and_filter_posts(raw_posts_path: Optional[Path] = None, days: int = 7) -> tuple[Path, int, int, int, int]:
    """
    主入口：读取原始数据，清洗过滤，输出 clean_posts.json
    
    Returns:
        输出文件路径
    """
    # 确定输入文件路径
    if raw_posts_path is None:
        raw_posts_path = get_artifacts_dir() / "raw_posts.json"
    
    # 读取原始数据
    if not raw_posts_path.exists():
        raise FileNotFoundError(f"原始数据文件不存在: {raw_posts_path}")
    
    with open(raw_posts_path, 'r', encoding='utf-8') as f:
        raw_posts = json.load(f)
    
    # 记录收集时间
    collected_at = datetime.now().isoformat()
    
    # 清洗所有帖子
    clean_posts = []
    parse_success_count = 0
    
    for raw_post in raw_posts:
        cleaned = clean_post(raw_post, collected_at)
        if cleaned['published_at']:
            parse_success_count += 1
        clean_posts.append(cleaned)
    
    # 过滤最近 N 天
    filtered_posts, excluded_posts = filter_last_7_days(clean_posts, days=days)
    
    artifacts_dir = get_artifacts_dir()

    # 保存清洗后的数据
    output_path = artifacts_dir / "clean_posts.json"
    _write_json_file(output_path, filtered_posts)

    excluded_output_path = artifacts_dir / "excluded_posts.json"
    _write_json_file(excluded_output_path, excluded_posts)

    cleaning_summary = _build_cleaning_summary(len(raw_posts), len(filtered_posts), excluded_posts)
    cleaning_summary_path = artifacts_dir / "cleaning_summary.json"
    _write_json_file(cleaning_summary_path, cleaning_summary)

    # 打印统计信息
    print("\n" + "=" * 60)
    print("📊 数据清洗与过滤统计")
    print("=" * 60)
    print(f"原始帖子总数: {len(raw_posts)}")
    print(f"成功解析时间: {parse_success_count}")
    print(f"时间解析失败: {len(raw_posts) - parse_success_count}")
    print(f"最近{days}天帖子: {len(filtered_posts)}")
    print(f"被排除帖子: {len(excluded_posts)}")
    if cleaning_summary["excluded_by_reason"]:
        print("排除原因统计:")
        for reason, count in cleaning_summary["excluded_by_reason"].items():
            print(f"  - {reason}: {count}")
    print(f"输出文件: {output_path}")
    print(f"排除明细: {excluded_output_path}")
    print(f"统计汇总: {cleaning_summary_path}")
    print("=" * 60)
    
    logger.info(
        "清洗完成: 原始%s条, 解析成功%s条, %s天内%s条, 排除%s条",
        len(raw_posts),
        parse_success_count,
        days,
        len(filtered_posts),
        len(excluded_posts),
    )
    
    return output_path, len(raw_posts), parse_success_count, len(filtered_posts), len(excluded_posts)


if __name__ == "__main__":
    clean_and_filter_posts()
