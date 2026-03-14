# -*- coding: utf-8 -*-
"""
llm_reporter.py - 可选的 LLM 深度报告生成模块
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

import llm_config
from utils import get_artifacts_dir, logger


def load_posts_for_llm(clean_posts_path: Optional[Path] = None) -> list[dict]:
    """优先使用价值判断后的高/中价值内容，为 LLM 阶段压缩更有学习价值的材料"""
    artifacts_dir = get_artifacts_dir()
    valued_posts_path = artifacts_dir / "valued_posts.json"

    if valued_posts_path.exists():
        with open(valued_posts_path, "r", encoding="utf-8") as f:
            valued_posts = json.load(f)
        prioritized_posts = [post for post in valued_posts if post.get("value_level") in {"high", "medium"}]
        if prioritized_posts:
            logger.info("LLM 报告优先使用 valued_posts.json: %s 条高/中价值内容", len(prioritized_posts))
            return prioritized_posts
        return valued_posts

    if clean_posts_path is None:
        clean_posts_path = artifacts_dir / "clean_posts.json"

    with open(clean_posts_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template(template_path: Optional[Path] = None) -> str:
    """加载报告提示词模板"""
    if template_path is None:
        template_path = Path(__file__).parent / llm_config.LLM_PROMPT_TEMPLATE

    return template_path.read_text(encoding="utf-8").strip()


def _normalize_text(value: Optional[str]) -> str:
    """统一处理文本字段"""
    return str(value or "").strip()


def _normalize_for_dedup(post: dict) -> str:
    """构造轻量去重指纹，避免把明显重复内容重复送给模型"""
    title = _normalize_text(post.get("title"))
    content = _normalize_text(post.get("content"))
    combined = f"{title} {content}".lower()
    combined = re.sub(r"\s+", "", combined)
    combined = re.sub(r"[^\u4e00-\u9fa5a-z0-9]", "", combined)
    return combined[:200]


def _parse_post_time(post: dict) -> datetime:
    """解析帖子时间，用于稳定排序；无法解析时回落到最早时间"""
    published_at = _normalize_text(post.get("published_at"))
    if not published_at:
        return datetime.min

    try:
        return datetime.fromisoformat(published_at)
    except ValueError:
        return datetime.min


def _estimate_post_value(post: dict) -> tuple[int, datetime]:
    """
    轻量评估帖子保留优先级。
    优先保留正文更充实、含数字或结构化表达、时间更近的帖子。
    """
    content = _normalize_text(post.get("content"))
    title = _normalize_text(post.get("title"))
    text = f"{title} {content}"
    score = min(len(content), 800)
    if re.search(r"\d", text):
        score += 80
    if re.search(r"认为|观点|结论|逻辑|商业模式|护城河|现金流|长期|差异化", text):
        score += 120
    if re.search(r"[一二三四五]、|1\.|2\.|其一|其二", text):
        score += 60
    return score, _parse_post_time(post)


def dedupe_and_rank_posts(clean_posts: list[dict]) -> list[dict]:
    """
    先去重，再按“价值优先、时间次优先”排序。
    最终顺序固定为：优先级高的帖子在前，优先级相同时较新的帖子在前。
    """
    unique_posts = []
    seen = set()

    for post in clean_posts:
        fingerprint = _normalize_for_dedup(post)
        if not fingerprint:
            continue
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_posts.append(post)

    unique_posts.sort(key=lambda post: _estimate_post_value(post), reverse=True)
    return unique_posts


def _build_post_entry(post: dict, index: int) -> str:
    """将单条帖子整理成给模型的稳定输入格式"""
    title = _normalize_text(post.get("title")) or "无标题"
    content = _normalize_text(post.get("content")) or "无正文"
    published_at = _normalize_text(post.get("published_at")) or "未知时间"
    url = _normalize_text(post.get("url")) or "无"
    entry = [
        f"## 帖子 {index}",
        f"- 发布时间: {published_at}",
        f"- 标题: {title}",
        f"- 链接: {url}",
        "- 内容:",
        content,
        "",
    ]
    return "\n".join(entry)


def build_llm_source_material(clean_posts: list[dict], max_posts: int, max_chars: int) -> str:
    """整理送给模型的帖子材料，避免直接整包 JSON 输入"""
    prepared = prepare_llm_source_material(clean_posts, max_posts=max_posts, max_chars=max_chars)
    return prepared["source_material"]


def prepare_llm_source_material(clean_posts: list[dict], max_posts: int, max_chars: int) -> dict:
    """
    整理 LLM 输入材料。
    1. 对标题+正文做轻量去重
    2. 按信息密度和时间稳定排序
    3. 按 max_posts 和 max_chars 做明确截断
    """
    ranked_posts = dedupe_and_rank_posts(clean_posts)
    selected_posts = ranked_posts[:max_posts]
    lines = [
        "以下是清洗后的雪球发言材料，请仅基于这些材料进行分析。",
        "",
    ]
    input_post_count = 0
    truncated = len(ranked_posts) > max_posts

    for post in selected_posts:
        entry_text = _build_post_entry(post, input_post_count + 1)
        current_material = "\n".join(lines + [entry_text]).strip()

        if len(current_material) > max_chars:
            remaining_chars = max_chars - len("\n".join(lines).strip())
            if remaining_chars <= 0:
                truncated = True
                break

            shortened_entry = entry_text[:remaining_chars].rstrip()
            if shortened_entry:
                lines.append(shortened_entry)
                input_post_count += 1
            truncated = True
            break

        lines.append(entry_text)
        input_post_count += 1

    summary_line = (
        "材料整理说明："
        f"原始清洗帖子 {len(clean_posts)} 条，"
        f"去重后 {len(ranked_posts)} 条，"
        f"本次纳入 {input_post_count} 条，"
        f"最大帖子数 {max_posts}，"
        f"最大字符数 {max_chars}，"
        f"是否截断: {'是' if truncated else '否'}。"
    )
    lines.append(summary_line)
    source_material = "\n".join(lines).strip()

    return {
        "source_material": source_material,
        "input_post_count": input_post_count,
        "input_char_count": len(source_material),
        "deduped_post_count": len(ranked_posts),
        "truncated": truncated,
    }


def write_llm_source_material(source_material: str) -> Path:
    """落盘模型输入材料，便于复盘"""
    output_path = get_artifacts_dir() / llm_config.LLM_SOURCE_MATERIAL_FILENAME
    output_path.write_text(source_material + "\n", encoding="utf-8")
    return output_path


def write_llm_report_meta(metadata: dict) -> Path:
    """落盘 LLM 阶段元数据"""
    output_path = get_artifacts_dir() / llm_config.LLM_REPORT_META_FILENAME
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def call_openai_compatible_chat_completion(
    prompt_template: str,
    source_material: str,
    model: str,
) -> tuple[str, dict]:
    """调用 OpenAI-compatible Chat Completions 接口"""
    api_key = llm_config.get_api_key()
    if not api_key:
        raise ValueError(f"缺少环境变量 {llm_config.LLM_API_KEY_ENV}，无法生成 LLM 报告")

    base_url = llm_config.get_base_url()
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt_template},
            {"role": "user", "content": source_material},
        ],
        "temperature": 0.3,
        "max_completion_tokens": llm_config.LLM_MAX_COMPLETION_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(endpoint, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("LLM 返回结果为空")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        report_text = content.strip()
    elif isinstance(content, list):
        report_text = "\n".join(
            item.get("text", "").strip()
            for item in content
            if isinstance(item, dict) and item.get("text")
        ).strip()
    else:
        report_text = ""

    if not report_text:
        raise ValueError("LLM 未返回可用文本内容")

    return report_text, data


def generate_llm_report(
    clean_posts_path: Optional[Path] = None,
    model_override: Optional[str] = None,
    max_posts: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> tuple[Optional[Path], dict]:
    """读取 clean_posts.json，生成 LLM 深度报告与阶段元数据"""
    if clean_posts_path is None:
        clean_posts_path = get_artifacts_dir() / "clean_posts.json"

    if not clean_posts_path.exists():
        raise FileNotFoundError(f"clean_posts.json 不存在: {clean_posts_path}")

    clean_posts = load_posts_for_llm(clean_posts_path)

    prompt_template_path = Path(__file__).parent / llm_config.LLM_PROMPT_TEMPLATE
    prompt_template = load_prompt_template(prompt_template_path)
    max_posts = max_posts or llm_config.LLM_MAX_INPUT_POSTS
    max_chars = max_chars or llm_config.LLM_MAX_INPUT_CHARS
    model = model_override or llm_config.LLM_DEFAULT_MODEL

    prepared = prepare_llm_source_material(clean_posts, max_posts=max_posts, max_chars=max_chars)
    source_material = prepared["source_material"]
    source_material_path = write_llm_source_material(source_material)

    metadata = {
        "llm_report_enabled": True,
        "llm_report_generated": False,
        "provider": llm_config.LLM_PROVIDER,
        "model": model,
        "prompt_template": str(prompt_template_path),
        "input_post_count": prepared["input_post_count"],
        "input_char_count": prepared["input_char_count"],
        "deduped_post_count": prepared["deduped_post_count"],
        "truncated": prepared["truncated"],
        "output_file": None,
        "source_material_file": str(source_material_path),
        "error_message": None,
        "usage": {},
    }

    try:
        report_text, raw_response = call_openai_compatible_chat_completion(
            prompt_template=prompt_template,
            source_material=source_material,
            model=model,
        )
        output_path = get_artifacts_dir() / llm_config.LLM_REPORT_FILENAME
        output_path.write_text(report_text + "\n", encoding="utf-8")
        metadata["llm_report_generated"] = True
        metadata["output_file"] = str(output_path)
        metadata["usage"] = raw_response.get("usage", {})
        write_llm_report_meta(metadata)
        logger.info("LLM 报告生成完成: %s", output_path)
        return output_path, metadata
    except Exception as e:
        metadata["error_message"] = str(e)
        write_llm_report_meta(metadata)
        raise
