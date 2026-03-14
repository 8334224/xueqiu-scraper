# -*- coding: utf-8 -*-
"""
final_reporter.py - 最终总览页生成模块
"""
import json
from pathlib import Path
from typing import Optional

import llm_config
from utils import get_artifacts_dir


FINAL_REPORT_FILENAME = "final_report.md"


def _read_json_if_exists(path: Path) -> Optional[dict]:
    """读取存在的 JSON 文件"""
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_text_if_exists(path: Path) -> str:
    """读取存在的文本文件"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _extract_quick_view(summary_markdown: str, fallback_conclusion: str) -> list[str]:
    """
    从规则摘要中抽取适合快速浏览的片段。
    优先提取“重点观点”段落，否则回退到核心结论。
    """
    if not summary_markdown:
        return [fallback_conclusion or "本次运行未生成可展示的规则摘要内容。"]

    lines = [line.rstrip() for line in summary_markdown.splitlines()]
    bullet_lines = []
    in_highlights = False

    for line in lines:
        if line.startswith("## ") and "重点观点" in line:
            in_highlights = True
            continue
        if in_highlights and line.startswith("## "):
            break
        if in_highlights and line.strip().startswith("### "):
            bullet_lines.append(f"- {line.strip()[4:]}")
            continue
        if in_highlights and line.strip().startswith("> "):
            bullet_lines.append(f"  {line.strip()[2:]}")
            if len(bullet_lines) >= 4:
                break

    if bullet_lines:
        return bullet_lines

    if fallback_conclusion:
        return [f"- {fallback_conclusion}"]

    return ["- 本次无可提炼的快速结论。"]


def generate_final_report(run_summary: dict) -> Path:
    """
    生成最终总览页。
    该页面是导航和摘要整合页，不引入第三套分析逻辑。
    """
    artifacts_dir = get_artifacts_dir()
    weekly_summary_json = _read_json_if_exists(artifacts_dir / "weekly_summary.json") or {}
    weekly_summary_markdown = _read_text_if_exists(artifacts_dir / "weekly_summary.md")
    cleaning_summary = _read_json_if_exists(artifacts_dir / "cleaning_summary.json") or {}
    llm_meta = _read_json_if_exists(artifacts_dir / llm_config.LLM_REPORT_META_FILENAME) or {}
    llm_output_path = artifacts_dir / llm_config.LLM_REPORT_FILENAME
    llm_generated = llm_output_path.exists()

    quick_view_lines = _extract_quick_view(
        weekly_summary_markdown,
        weekly_summary_json.get("core_conclusion", ""),
    )

    lines = [
        "# 雪球发言周报总览",
        "",
        "这是本次运行的统一入口页。默认先看这里，再按需要进入规则摘要或 LLM 深度报告。",
        "",
        "## 本次运行信息",
        "",
        f"- user_id: `{run_summary.get('user_id')}`",
        f"- days: `{run_summary.get('days')}`",
        f"- source_mode: `{run_summary.get('source_mode')}`",
        f"- fetch_source_used: `{run_summary.get('fetch_source_used')}`",
        f"- raw / clean / excluded: `{run_summary.get('raw_count')}` / `{cleaning_summary.get('clean_count')}` / `{cleaning_summary.get('excluded_count')}`",
        f"- LLM 报告启用: `{'yes' if run_summary.get('llm_report_enabled') else 'no'}`",
        "",
        "## 快速结论",
        "",
        "先看规则摘要，这部分适合快速浏览：",
        "",
    ]

    lines.extend(quick_view_lines)
    lines.extend([
        "",
        f"规则摘要文件: `{artifacts_dir / 'weekly_summary.md'}`",
        "",
        "## 深度报告入口",
        "",
    ])

    if llm_generated:
        lines.extend([
            "已生成“投资思维提炼报告”，适合深入阅读：",
            "",
            f"- 深度报告文件: `{llm_output_path}`",
        ])
        if llm_meta.get("model"):
            lines.append(f"- 使用模型: `{llm_meta['model']}`")
        if llm_meta.get("source_material_file"):
            lines.append(f"- 输入材料文件: `{llm_meta['source_material_file']}`")
        lines.append("")
    else:
        lines.extend([
            "本次未生成 LLM 深度报告。默认请先查看规则摘要。",
            "",
        ])

    lines.extend([
        "## 本次输出文件清单",
        "",
        f"- `{artifacts_dir / FINAL_REPORT_FILENAME}`：统一入口页，建议优先阅读",
        f"- `{artifacts_dir / 'weekly_summary.md'}`：规则摘要，适合快速浏览",
        f"- `{artifacts_dir / 'weekly_summary.json'}`：规则摘要的结构化结果",
    ])

    if llm_generated:
        lines.append(f"- `{llm_output_path}`：LLM 深度报告，适合深入阅读")
        lines.append(f"- `{artifacts_dir / llm_config.LLM_REPORT_META_FILENAME}`：LLM 阶段元数据")
        lines.append(f"- `{artifacts_dir / llm_config.LLM_SOURCE_MATERIAL_FILENAME}`：发给模型前的整理材料")

    lines.extend([
        f"- `{artifacts_dir / 'run_summary.json'}`：运行元数据，适合程序化读取和排查",
        f"- `{artifacts_dir / 'cleaning_summary.json'}`：清洗统计与过滤原因",
        f"- `{artifacts_dir / 'valued_posts.json'}`：价值分级后的帖子结果，可用于复盘高/中/低价值判断",
        f"- `{artifacts_dir / 'clean_posts.json'}` / `{artifacts_dir / 'excluded_posts.json'}`：中间产物",
        "",
    ])

    output_path = artifacts_dir / FINAL_REPORT_FILENAME
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path
