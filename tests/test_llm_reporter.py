import json

import llm_reporter
import llm_config


def test_build_llm_source_material_deduplicates_posts():
    clean_posts = [
        {"title": "重复标题", "content": "重复内容", "published_at": "2026-03-14T10:00:00", "url": "https://example.com/1"},
        {"title": "重复标题", "content": "重复内容", "published_at": "2026-03-13T10:00:00", "url": "https://example.com/2"},
        {"title": "不同标题", "content": "不同内容", "published_at": "2026-03-12T10:00:00", "url": "https://example.com/3"},
    ]

    material = llm_reporter.build_llm_source_material(clean_posts, max_posts=5, max_chars=2000)

    assert material.count("重复标题") == 1
    assert "不同标题" in material


def test_prepare_llm_source_material_marks_truncated():
    clean_posts = [
        {"title": f"帖子{i}", "content": "长内容" * 80, "published_at": f"2026-03-{14 - i:02d}T10:00:00", "url": f"https://example.com/{i}"}
        for i in range(3)
    ]

    prepared = llm_reporter.prepare_llm_source_material(clean_posts, max_posts=3, max_chars=260)

    assert prepared["truncated"] is True
    assert prepared["input_post_count"] >= 1
    assert prepared["input_char_count"] <= len(prepared["source_material"])


def test_generate_llm_report_writes_markdown_and_meta(tmp_path, monkeypatch):
    clean_posts_path = tmp_path / "clean_posts.json"
    clean_posts_path.write_text(
        json.dumps(
            [
                {
                    "title": "测试标题",
                    "content": "测试内容",
                    "published_at": "2026-03-14T10:00:00",
                    "url": "https://example.com/1",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(llm_reporter, "get_artifacts_dir", lambda: tmp_path)
    monkeypatch.setattr(llm_reporter, "load_prompt_template", lambda template_path=None: "测试提示词")
    monkeypatch.setattr(
        llm_reporter,
        "call_openai_compatible_chat_completion",
        lambda prompt_template, source_material, model: ("# 报告\n\n测试报告正文", {"usage": {"total_tokens": 123}}),
    )

    output_path, metadata = llm_reporter.generate_llm_report(clean_posts_path=clean_posts_path, model_override="demo-model")
    meta_path = tmp_path / llm_config.LLM_REPORT_META_FILENAME
    source_material_path = tmp_path / llm_config.LLM_SOURCE_MATERIAL_FILENAME

    assert output_path == tmp_path / llm_config.LLM_REPORT_FILENAME
    assert output_path.read_text(encoding="utf-8").startswith("# 报告")
    assert metadata["model"] == "demo-model"
    assert metadata["usage"] == {"total_tokens": 123}
    assert metadata["llm_report_generated"] is True
    assert meta_path.exists()
    assert source_material_path.exists()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["llm_report_enabled"] is True
    assert meta["llm_report_generated"] is True
    assert meta["output_file"] == str(output_path)
    assert meta["source_material_file"] == str(source_material_path)


def test_generate_llm_report_writes_failure_meta(tmp_path, monkeypatch):
    clean_posts_path = tmp_path / "clean_posts.json"
    clean_posts_path.write_text(
        json.dumps(
            [
                {
                    "title": "测试标题",
                    "content": "测试内容",
                    "published_at": "2026-03-14T10:00:00",
                    "url": "https://example.com/1",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(llm_reporter, "get_artifacts_dir", lambda: tmp_path)
    monkeypatch.setattr(llm_reporter, "load_prompt_template", lambda template_path=None: "测试提示词")

    def raise_error(prompt_template, source_material, model):
        raise RuntimeError("mock llm error")

    monkeypatch.setattr(llm_reporter, "call_openai_compatible_chat_completion", raise_error)

    try:
        llm_reporter.generate_llm_report(clean_posts_path=clean_posts_path, model_override="demo-model")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert str(e) == "mock llm error"

    meta = json.loads((tmp_path / llm_config.LLM_REPORT_META_FILENAME).read_text(encoding="utf-8"))
    assert meta["llm_report_generated"] is False
    assert meta["error_message"] == "mock llm error"


def test_generate_llm_report_prefers_valued_posts(tmp_path, monkeypatch):
    clean_posts_path = tmp_path / "clean_posts.json"
    clean_posts_path.write_text(
        json.dumps(
            [
                {"title": "低价值", "content": "谢谢", "published_at": "2026-03-14T10:00:00", "url": "https://example.com/1"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "valued_posts.json").write_text(
        json.dumps(
            [
                {
                    "title": "高价值",
                    "content": "买股票就是买公司。",
                    "published_at": "2026-03-14T11:00:00",
                    "url": "https://example.com/2",
                    "value_level": "high",
                    "value_score": 90,
                    "value_reasons": ["contains_investment_principle"],
                },
                {
                    "title": "低价值",
                    "content": "谢谢",
                    "published_at": "2026-03-14T10:00:00",
                    "url": "https://example.com/1",
                    "value_level": "low",
                    "value_score": 5,
                    "value_reasons": ["pure_greeting_or_acknowledgement"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}

    monkeypatch.setattr(llm_reporter, "get_artifacts_dir", lambda: tmp_path)
    monkeypatch.setattr(llm_reporter, "load_prompt_template", lambda template_path=None: "测试提示词")

    def fake_call(prompt_template, source_material, model):
        captured["source_material"] = source_material
        return "# 报告\n\n正文", {"usage": {}}

    monkeypatch.setattr(llm_reporter, "call_openai_compatible_chat_completion", fake_call)

    llm_reporter.generate_llm_report(clean_posts_path=clean_posts_path, model_override="demo-model")

    assert "高价值" in captured["source_material"]
    assert "低价值" not in captured["source_material"]
