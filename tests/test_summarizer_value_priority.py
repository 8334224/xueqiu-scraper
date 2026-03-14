import json

import summarizer


def test_generate_weekly_summary_prefers_non_low_valued_posts(tmp_path, monkeypatch):
    monkeypatch.setattr(summarizer, "get_artifacts_dir", lambda: tmp_path)

    (tmp_path / "clean_posts.json").write_text(
        json.dumps(
            [
                {"title": "低价值", "content": "谢谢", "published_at": "2026-03-14T10:00:00", "url": "https://example.com/1"},
                {"title": "高价值", "content": "买股票就是买公司。", "published_at": "2026-03-14T11:00:00", "url": "https://example.com/2"},
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
                    "value_score": 88,
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

    _, _, summary = summarizer.generate_weekly_summary()

    assert summary["total_posts"] == 1
    assert summary["highlights"][0]["title"] == "高价值"
