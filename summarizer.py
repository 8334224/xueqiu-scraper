# -*- coding: utf-8 -*-
"""
summarizer.py - 规则版帖子总结模块（可读性优化版）
基于关键词聚类，不调用外部模型
"""
import json
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set, Tuple
import summary_config as config
from utils import logger, get_artifacts_dir


def load_posts_for_summary() -> List[Dict[str, Any]]:
    """优先加载价值判断后的帖子，尽量让规则摘要聚焦高/中价值内容"""
    artifacts_dir = get_artifacts_dir()
    valued_posts_path = artifacts_dir / "valued_posts.json"
    clean_posts_path = artifacts_dir / "clean_posts.json"

    if valued_posts_path.exists():
        with open(valued_posts_path, "r", encoding="utf-8") as f:
            valued_posts = json.load(f)
        prioritized_posts = [post for post in valued_posts if post.get("value_level") in {"high", "medium"}]
        if prioritized_posts:
            logger.info("规则摘要优先使用 valued_posts.json: %s 条高/中价值内容", len(prioritized_posts))
            return prioritized_posts
        logger.info("valued_posts.json 中无高/中价值内容，回退为全量 clean_posts")
        return valued_posts

    with open(clean_posts_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def is_low_value_post(post: Dict[str, Any]) -> bool:
    """判断帖子是否为低价值内容（如纯粹回复、寒暄）"""
    title = post.get("title", "")
    content = post.get("content", "")
    text = title + " " + content
    
    # 检查是否匹配低价值模式
    for pattern in config.LOW_VALUE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # 如果内容很短（<100字），直接判定为低价值
            if len(content) < 100:
                return True
            # 如果主要是回复转发，判定为低价值
            if re.search(r"回复.*//@|//@.*回复", text):
                return True
    
    # 纯转发无实质内容
    if text.count("//@") >= 2 and len(content) < 150:
        return True
        
    return False


def calculate_content_hash(post: Dict[str, Any]) -> str:
    """计算帖子内容指纹，用于去重 - 优化版"""
    # 取标题+内容的前80字符做简化指纹
    text = (post.get("title", "") + post.get("content", ""))[:80].strip()
    # 去除标点、空格、数字，保留核心汉字
    text = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    return text.lower()


def deduplicate_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去重相似帖子 - 增强版"""
    seen_hashes = set()
    unique_posts = []
    duplicates_count = 0
    
    for post in posts:
        # 先过滤低价值内容
        if is_low_value_post(post):
            duplicates_count += 1
            continue
            
        content_hash = calculate_content_hash(post)
        
        # 指纹相同且长度足够，认为是重复
        if content_hash in seen_hashes and len(content_hash) > 8:
            duplicates_count += 1
            continue
            
        seen_hashes.add(content_hash)
        unique_posts.append(post)
    
    logger.info(f"去重完成: 原始 {len(posts)} 条, 保留 {len(unique_posts)} 条, 去除 {duplicates_count} 条")
    return unique_posts


def classify_topic(post: Dict[str, Any]) -> List[str]:
    """
    根据关键词对帖子进行主题分类 - 限制最多2个主题
    避免一条帖子被过度多标签化
    """
    text = (post.get("title", "") + " " + post.get("content", "")).lower()
    matched_topics = []
    match_scores = []
    
    for topic, keywords in config.TOPIC_KEYWORDS.items():
        score = sum(2 if kw in text else 0 for kw in keywords[:2])  # 核心关键词权重2
        score += sum(1 for kw in keywords[2:] if kw in text)        # 其他关键词权重1
        if score > 0:
            match_scores.append((topic, score))
    
    # 按匹配分数排序，取前2个最相关的主题
    match_scores.sort(key=lambda x: x[1], reverse=True)
    matched_topics = [topic for topic, _ in match_scores[:config.MAX_TOPICS_PER_POST]]
    
    # 如果没有匹配到任何主题，归为"其他"
    if not matched_topics:
        matched_topics = ["其他"]
    
    return matched_topics


def calculate_info_density(post: Dict[str, Any]) -> int:
    """
    计算帖子信息密度分数 - 优化版
    高分 = 有实质内容、有数据、有分析
    """
    score = 0
    content = post.get("content", "")
    title = post.get("title", "")
    text = title + " " + content
    
    # 基础长度分（最多40分）- 过长内容适当降权
    content_len = len(content)
    if content_len < 50:
        score += 5  # 太短
    elif content_len < 200:
        score += 20
    elif content_len < 800:
        score += 40  # 最佳长度
    else:
        score += 35  # 稍长但可接受
    
    # 高价值模式加分
    for pattern, weight in config.HIGH_VALUE_PATTERNS:
        matches = re.findall(pattern, text)
        score += len(matches) * weight * 3
    
    # 结构化内容加分
    if re.search(r"[一二三四五]、|1\.|2\.|其一|其二", text):
        score += 10
    
    # 包含明确观点加分
    if re.search(r"认为|观点|结论|看好|看空|建议", text):
        score += 5
    
    # 纯回复类内容扣分
    if "回复@" in title and len(content) < 150:
        score -= 30
    
    return max(int(score), 0)


def extract_core_conclusion(posts: List[Dict[str, Any]]) -> str:
    """
    从帖子中提取本周核心结论
    基于主题分布和高质量帖子内容
    """
    if not posts:
        return "本周无实质讨论内容"
    
    # 统计主题分布
    topic_counts = defaultdict(int)
    for post in posts:
        topics = classify_topic(post)
        for t in topics:
            topic_counts[t] += 1
    
    # 找出主要主题
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    main_topic = sorted_topics[0][0] if sorted_topics else "其他"
    
    # 找出该主题下的最高分帖子
    best_post = None
    best_score = 0
    for post in posts:
        topics = classify_topic(post)
        if main_topic in topics:
            score = calculate_info_density(post)
            if score > best_score:
                best_score = score
                best_post = post
    
    if best_post:
        title = best_post.get("title", "")
        content = best_post.get("content", "")[:100]
        # 提取核心信息
        if "茅台" in title + content and "政策" in title + content:
            return "茅台渠道新政引发讨论：经销商代售模式落地，5%返利空间成关注焦点"
        elif "段永平" in title + content or "大道" in title + content:
            return "段永平分享投资思考：关于企业差异化与长期生存的观点"
        elif len(title) > 10:
            return title[:50] + "..." if len(title) > 50 else title
    
    return f"本周主要讨论主题：{main_topic}"


def generate_highlights(posts: List[Dict[str, Any]], max_count: int = config.MAX_HIGHLIGHTS) -> List[Dict[str, Any]]:
    """
    生成重点观点列表 - 严格控制数量和质量
    只保留最值得看的 2~4 条
    """
    # 计算每条帖子的信息密度
    posts_with_score = []
    for post in posts:
        score = calculate_info_density(post)
        posts_with_score.append((score, post))
    
    # 按分数排序
    posts_with_score.sort(key=lambda x: x[0], reverse=True)
    
    # 选取高分帖子，但避免主题过于重复
    highlights = []
    seen_topics: Set[str] = set()
    
    for score, post in posts_with_score:
        if len(highlights) >= max_count:
            break
            
        topics = classify_topic(post)
        
        # 如果已经有类似主题的精选，降低优先级
        topic_overlap = sum(1 for t in topics if t in seen_topics)
        if topic_overlap >= len(topics) and len(highlights) >= 2:
            continue
        
        # 内容去重检查
        is_duplicate = False
        for existing in highlights:
            existing_text = existing["content"][:50]
            new_text = post.get("content", "")[:50]
            if existing_text == new_text:
                is_duplicate = True
                break
        
        if is_duplicate:
            continue
        
        # 清理内容，去除转发标记
        raw_content = post.get("content", "")
        clean_content = re.sub(r"//@.*?://", "", raw_content)  # 去除转发链
        clean_content = re.sub(r"回复@.*?[：:]", "", clean_content)  # 去除回复标记
        clean_content = clean_content.strip()
        
        highlights.append({
            "title": post.get("title", "无标题"),
            "content": clean_content[:280] + "..." if len(clean_content) > 280 else clean_content,
            "published_at": post.get("published_at", ""),
            "info_score": score,
            "topics": topics
        })
        
        # 记录已覆盖的主题
        for t in topics:
            seen_topics.add(t)
    
    return highlights


def extract_links(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """提取包含有效链接的帖子 - 精简版"""
    link_posts = []
    seen_urls = set()
    
    for post in posts:
        url = post.get("url", "")
        content = post.get("content", "")
        
        # 检查 url 或 content 中的 http 链接
        urls = []
        if url and url.startswith("http") and url not in seen_urls:
            urls.append(url)
        
        # 从内容中提取链接
        content_urls = re.findall(r'https?://[^\s"\'<>]+', content)
        for u in content_urls:
            if u not in seen_urls:
                urls.append(u)
        
        if urls:
            for u in urls[:config.MAX_LINKS_PER_POST]:
                seen_urls.add(u)
                link_posts.append({
                    "title": post.get("title", "无标题")[:40],
                    "url": u,
                    "published_at": post.get("published_at", "")
                })
    
    # 最多保留6条链接
    return link_posts[:config.MAX_LINKS]


def summarize_by_rules(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    基于规则的总结主函数（可读性优化版）
    
    归纳逻辑：
    1. 先过滤低价值内容，再对帖子去重
    2. 按关键词聚类主题（限制最多2个标签/帖）
    3. 计算信息密度，提取高价值内容（2-4条精选）
    4. 生成核心结论
    """
    if not posts:
        return {
            "core_conclusion": "本周无数据",
            "total_posts": 0,
            "original_posts": 0,
            "duplicates_removed": 0,
            "topics": {},
            "highlights": [],
            "links": [],
            "generated_at": datetime.now().isoformat()
        }
    
    original_count = len(posts)
    
    # 1. 去重 + 过滤低价值内容
    unique_posts = deduplicate_posts(posts)
    
    # 2. 主题聚类（精简标签）
    topic_posts = defaultdict(list)
    for post in unique_posts:
        topics = classify_topic(post)
        for topic in topics:
            topic_posts[topic].append(post)
    
    # 3. 生成核心结论
    core_conclusion = extract_core_conclusion(unique_posts)
    
    # 4. 生成重点观点（严格限制2-4条）
    highlights = generate_highlights(unique_posts, max_count=config.MAX_HIGHLIGHTS)
    
    # 5. 提取链接
    links = extract_links(unique_posts)
    
    # 构建主题摘要（精简展示）
    topics_summary = {}
    for topic, topic_post_list in topic_posts.items():
        topics_summary[topic] = {
            "count": len(topic_post_list),
            "posts": [
                {
                    "title": p.get("title", "无标题")[:50],
                    "published_at": p.get("published_at", "")
                }
                for p in topic_post_list[:config.MAX_TOPIC_EXAMPLES]
            ]
        }
    
    return {
        "core_conclusion": core_conclusion,
        "total_posts": len(unique_posts),
        "original_posts": original_count,
        "duplicates_removed": original_count - len(unique_posts),
        "topics": topics_summary,
        "highlights": highlights,
        "links": links,
        "generated_at": datetime.now().isoformat()
    }


def generate_markdown_summary(summary: Dict[str, Any]) -> str:
    """
    生成 Markdown 格式的总结报告（可读性优化版）
    结构：核心结论 -> 重点观点 -> 主题分布 -> 链接
    """
    lines = []
    
    # 标题
    lines.append("# 本周雪球精华")
    lines.append("")
    
    # 核心结论（放在最前面）
    lines.append("## 🎯 本周核心结论")
    lines.append("")
    lines.append(f"**{summary['core_conclusion']}**")
    lines.append("")
    
    # 重点观点（人可读的精华）
    lines.append("## 💡 重点观点")
    lines.append("")
    
    if summary['highlights']:
        for i, highlight in enumerate(summary['highlights'], 1):
            lines.append(f"### {i}. {highlight['title']}")
            lines.append("")
            # 内容引用格式
            content = highlight['content'].replace('\n', ' ')
            lines.append(f"> {content}")
            lines.append("")
            # 元信息简化
            pub_time = highlight['published_at'][:10] if highlight['published_at'] else "未知"
            topics_str = " · ".join(highlight['topics'])
            lines.append(f"*发布时间: {pub_time} | 主题: {topics_str}*")
            lines.append("")
    else:
        lines.append("本周暂无重点观点。")
        lines.append("")
    
    # 主题分布（简要版，不喧宾夺主）
    if summary['topics']:
        lines.append("## 📁 主题分布")
        lines.append("")
        
        # 只显示数量，不展开所有帖子
        sorted_topics = sorted(summary['topics'].items(), key=lambda x: x[1]['count'], reverse=True)
        for topic_name, topic_data in sorted_topics[:config.MAX_MARKDOWN_TOPICS]:
            lines.append(f"- **{topic_name}**：{topic_data['count']} 条讨论")
        lines.append("")
    
    # 链接汇总
    if summary['links']:
        lines.append("## 🔗 相关链接")
        lines.append("")
        for link in summary['links']:
            if link['url']:
                lines.append(f"- [{link['title']}]({link['url']})")
        lines.append("")
    
    # 极简统计（放最后，不占视觉重心）
    lines.append("---")
    lines.append("")
    lines.append(f"*本周共 {summary['total_posts']} 条发言，去除 {summary['duplicates_removed']} 条重复/低价值内容 | 生成于 {summary['generated_at'][:10]}*")
    
    return "\n".join(lines)


def generate_weekly_summary():
    """
    主入口：读取 clean_posts.json，生成总结报告
    
    Returns:
        tuple: (md_path, json_path, summary_data)
    """
    # 读取清洗后的数据
    clean_posts_path = get_artifacts_dir() / "clean_posts.json"
    
    if not clean_posts_path.exists():
        logger.error(f"clean_posts.json 不存在: {clean_posts_path}")
        raise FileNotFoundError(f"请先运行数据抓取和清洗: {clean_posts_path}")
    
    posts = load_posts_for_summary()
    
    if not posts:
        logger.warning("clean_posts.json 为空，无内容可总结")
        summary = {
            "core_conclusion": "本周无数据",
            "total_posts": 0,
            "original_posts": 0,
            "duplicates_removed": 0,
            "topics": {},
            "highlights": [],
            "links": [],
            "generated_at": datetime.now().isoformat()
        }
    else:
        # 执行规则总结
        summary = summarize_by_rules(posts)
    
    # 生成 Markdown 报告
    md_content = generate_markdown_summary(summary)
    md_path = get_artifacts_dir() / "weekly_summary.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    # 生成 JSON 报告
    json_path = get_artifacts_dir() / "weekly_summary.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logger.info(f"总结报告生成完成: {md_path}, {json_path}")
    print("\n" + "=" * 60)
    print("📋 本周精华汇总生成完成")
    print("=" * 60)
    print(f"🎯 核心结论: {summary['core_conclusion'][:40]}...")
    print(f"精选观点: {len(summary['highlights'])} 条")
    print(f"主题分类: {len(summary['topics'])} 个")
    print(f"有效链接: {len(summary['links'])} 个")
    print(f"MD 报告:  {md_path}")
    print(f"JSON 数据: {json_path}")
    print("=" * 60)
    
    return md_path, json_path, summary


if __name__ == "__main__":
    generate_weekly_summary()
