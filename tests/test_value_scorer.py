import json

import value_scorer


def test_short_principle_post_can_be_high_value():
    post = {
        "title": "",
        "content": "买股票就是买公司。",
        "published_at": "2026-03-14T10:00:00",
        "url": "https://example.com/1",
    }

    valued = value_scorer.value_post(post)

    assert valued["value_level"] in {"medium", "high"}
    assert "contains_investment_principle" in valued["value_reasons"]
    assert valued["value_score"] >= 40


def test_greeting_post_is_low_value():
    post = {
        "title": "",
        "content": "谢谢",
        "published_at": "2026-03-14T10:00:00",
        "url": "https://example.com/1",
    }

    valued = value_scorer.value_post(post)

    assert valued["value_level"] == "low"
    assert "pure_greeting_or_acknowledgement" in valued["value_reasons"]


def test_score_clean_posts_writes_valued_posts(tmp_path, monkeypatch):
    clean_posts_path = tmp_path / "clean_posts.json"
    clean_posts_path.write_text(
        json.dumps(
            [
                {
                    "title": "原则",
                    "content": "最重要的是别做自己不懂的生意。",
                    "published_at": "2026-03-14T10:00:00",
                    "url": "https://example.com/1",
                },
                {
                    "title": "",
                    "content": "哈哈",
                    "published_at": "2026-03-14T11:00:00",
                    "url": "https://example.com/2",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(value_scorer, "get_artifacts_dir", lambda: tmp_path)

    output_path, summary = value_scorer.score_clean_posts(clean_posts_path)
    valued_posts = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path == tmp_path / value_scorer.VALUED_POSTS_FILENAME
    assert len(valued_posts) == 2
    assert all("value_level" in post and "value_score" in post and "value_reasons" in post for post in valued_posts)
    assert summary["high_count"] + summary["medium_count"] + summary["low_count"] == 2
