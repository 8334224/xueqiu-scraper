import json

import final_reporter
import llm_config


def test_generate_final_report_contains_run_info(tmp_path, monkeypatch):
    monkeypatch.setattr(final_reporter, "get_artifacts_dir", lambda: tmp_path)

    (tmp_path / "weekly_summary.md").write_text(
        "# 本周雪球精华\n\n## 💡 重点观点\n\n### 1. 规则观点\n\n> 这是快速浏览内容\n",
        encoding="utf-8",
    )
    (tmp_path / "weekly_summary.json").write_text(
        json.dumps({"core_conclusion": "核心结论"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "cleaning_summary.json").write_text(
        json.dumps({"clean_count": 8, "excluded_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )

    run_summary = {
        "user_id": "slowisquick",
        "days": 7,
        "source_mode": "auto",
        "fetch_source_used": "browser",
        "raw_count": 10,
        "llm_report_enabled": False,
    }

    output_path = final_reporter.generate_final_report(run_summary)
    content = output_path.read_text(encoding="utf-8")

    assert output_path == tmp_path / final_reporter.FINAL_REPORT_FILENAME
    assert "user_id: `slowisquick`" in content
    assert "raw / clean / excluded: `10` / `8` / `2`" in content
    assert "规则摘要文件" in content


def test_generate_final_report_without_llm_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(final_reporter, "get_artifacts_dir", lambda: tmp_path)

    (tmp_path / "weekly_summary.md").write_text(
        "# 本周雪球精华\n\n## 🎯 本周核心结论\n\n**规则版结论**\n",
        encoding="utf-8",
    )
    (tmp_path / "weekly_summary.json").write_text(
        json.dumps({"core_conclusion": "规则版结论"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "cleaning_summary.json").write_text(
        json.dumps({"clean_count": 3, "excluded_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )

    output_path = final_reporter.generate_final_report(
        {
            "user_id": "slowisquick",
            "days": 7,
            "source_mode": "http",
            "fetch_source_used": "http",
            "raw_count": 4,
            "llm_report_enabled": False,
        }
    )

    content = output_path.read_text(encoding="utf-8")
    assert "本次未生成 LLM 深度报告" in content
    assert "规则摘要，适合快速浏览" in content


def test_generate_final_report_with_llm_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(final_reporter, "get_artifacts_dir", lambda: tmp_path)

    (tmp_path / "weekly_summary.md").write_text(
        "# 本周雪球精华\n\n## 💡 重点观点\n\n### 1. 规则观点\n\n> 这是快速浏览内容\n",
        encoding="utf-8",
    )
    (tmp_path / "weekly_summary.json").write_text(
        json.dumps({"core_conclusion": "核心结论"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "cleaning_summary.json").write_text(
        json.dumps({"clean_count": 8, "excluded_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / llm_config.LLM_REPORT_FILENAME).write_text("# 深度报告", encoding="utf-8")
    (tmp_path / llm_config.LLM_REPORT_META_FILENAME).write_text(
        json.dumps(
            {
                "model": "gpt-4o-mini",
                "source_material_file": str(tmp_path / llm_config.LLM_SOURCE_MATERIAL_FILENAME),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / llm_config.LLM_SOURCE_MATERIAL_FILENAME).write_text("材料", encoding="utf-8")

    output_path = final_reporter.generate_final_report(
        {
            "user_id": "slowisquick",
            "days": 7,
            "source_mode": "auto",
            "fetch_source_used": "browser",
            "raw_count": 10,
            "llm_report_enabled": True,
        }
    )

    content = output_path.read_text(encoding="utf-8")
    assert "投资思维提炼报告" in content
    assert llm_config.LLM_REPORT_FILENAME in content
    assert "使用模型: `gpt-4o-mini`" in content
