import json
from pathlib import Path

import main


def test_main_stops_after_browser_success(monkeypatch):
    calls = []

    def fake_browser_fetch(user_id):
        calls.append(("browser", user_id))
        return ([{"title": "browser post"}], True)

    def fake_http_fetch(user_id):
        calls.append(("http", user_id))
        return [{"title": "http post"}]

    def fake_post_processing(posts, method_label, days, llm_report_enabled=False, llm_model=None):
        calls.append(("post_process", method_label, len(posts), days))
        return {
            "value_result": (Path("/tmp/artifacts/valued_posts.json"), {"high_count": 1, "medium_count": 0, "low_count": 0}),
            "llm_report_result": {"generated": False, "output_path": None, "error_message": None},
        }

    monkeypatch.setattr(main, "fetch_posts_with_browser", fake_browser_fetch)
    monkeypatch.setattr(main, "fetch_user_posts", fake_http_fetch)
    monkeypatch.setattr(main, "run_post_processing", fake_post_processing)
    monkeypatch.setattr(main, "build_success_run_summary", lambda **kwargs: kwargs)
    monkeypatch.setattr(main, "generate_final_report", lambda summary: Path("/tmp/artifacts/final_report.md"))
    monkeypatch.setattr(main, "write_run_summary", lambda summary: calls.append(("summary", summary)) or "/tmp/artifacts/run_summary.json")
    monkeypatch.setattr(main, "print_run_summary", lambda summary, path: calls.append(("summary_print", summary["fetch_source_used"], path)))
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: Path("/tmp/artifacts"))
    main.main("target_user")

    assert calls == [
        ("browser", "target_user"),
        ("post_process", "浏览器探针", 1, 7),
        ("summary", {
            "user_id": "target_user",
            "days": 7,
            "source_mode": "auto",
            "fetch_source_used": "browser",
            "fallback_used": False,
            "raw_count": 1,
            "llm_report_enabled": False,
            "llm_report_path": None,
            "llm_report_generated": False,
            "llm_model": None,
            "llm_error_message": None,
            "primary_report_file": "/tmp/artifacts/final_report.md",
            "secondary_report_file": "/tmp/artifacts/weekly_summary.md",
            "files_generated": [],
        }),
        ("summary_print", "browser", "/tmp/artifacts/run_summary.json"),
    ]


def test_main_falls_back_to_http_once(monkeypatch):
    calls = []

    def fake_browser_fetch(user_id):
        calls.append(("browser", user_id))
        return ([], False)

    def fake_http_fetch(user_id):
        calls.append(("http", user_id))
        return [{"title": "http post"}]

    def fake_post_processing(posts, method_label, days, llm_report_enabled=False, llm_model=None):
        calls.append(("post_process", method_label, len(posts), days))
        return {
            "value_result": (Path("/tmp/artifacts/valued_posts.json"), {"high_count": 1, "medium_count": 0, "low_count": 0}),
            "llm_report_result": {"generated": False, "output_path": None, "error_message": None},
        }

    monkeypatch.setattr(main, "fetch_posts_with_browser", fake_browser_fetch)
    monkeypatch.setattr(main, "fetch_user_posts", fake_http_fetch)
    monkeypatch.setattr(main, "run_post_processing", fake_post_processing)
    monkeypatch.setattr(main, "build_success_run_summary", lambda **kwargs: kwargs)
    monkeypatch.setattr(main, "generate_final_report", lambda summary: Path("/tmp/artifacts/final_report.md"))
    monkeypatch.setattr(main, "write_run_summary", lambda summary: calls.append(("summary", summary)) or "/tmp/artifacts/run_summary.json")
    monkeypatch.setattr(main, "print_run_summary", lambda summary, path: calls.append(("summary_print", summary["fetch_source_used"], path)))
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: Path("/tmp/artifacts"))
    main.main("target_user")

    assert calls == [
        ("browser", "target_user"),
        ("http", "target_user"),
        ("post_process", "HTTP 请求", 1, 7),
        ("summary", {
            "user_id": "target_user",
            "days": 7,
            "source_mode": "auto",
            "fetch_source_used": "http",
            "fallback_used": True,
            "raw_count": 1,
            "llm_report_enabled": False,
            "llm_report_path": None,
            "llm_report_generated": False,
            "llm_model": None,
            "llm_error_message": None,
            "primary_report_file": "/tmp/artifacts/final_report.md",
            "secondary_report_file": "/tmp/artifacts/weekly_summary.md",
            "files_generated": [],
        }),
        ("summary_print", "http", "/tmp/artifacts/run_summary.json"),
    ]


def test_main_browser_source_does_not_fallback(monkeypatch):
    calls = []

    def fake_browser_fetch(user_id):
        calls.append(("browser", user_id))
        return ([], False)

    def fake_http_fetch(user_id):
        calls.append(("http", user_id))
        return [{"title": "http post"}]

    monkeypatch.setattr(main, "fetch_posts_with_browser", fake_browser_fetch)
    monkeypatch.setattr(main, "fetch_user_posts", fake_http_fetch)
    monkeypatch.setattr(
        main,
        "build_failure_run_summary",
        lambda **kwargs: {**kwargs, "primary_report_file": None, "secondary_report_file": None},
    )
    monkeypatch.setattr(main, "write_run_summary", lambda summary: calls.append(("summary", summary)) or "/tmp/artifacts/run_summary.json")
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: Path("/tmp/artifacts"))

    main.main("target_user", source="browser")

    assert calls == [
        ("browser", "target_user"),
        ("summary", {
            "user_id": "target_user",
            "days": 7,
            "source_mode": "browser",
            "error_message": "browser 未获取到帖子数据",
            "fetch_source_used": "browser",
            "fallback_used": False,
            "llm_report_enabled": False,
            "llm_report_generated": False,
            "llm_model": None,
            "llm_error_message": None,
            "primary_report_file": None,
            "secondary_report_file": None,
        }),
    ]


def test_main_http_source_skips_browser(monkeypatch):
    calls = []

    def fake_browser_fetch(user_id):
        calls.append(("browser", user_id))
        return ([{"title": "browser post"}], True)

    def fake_http_fetch(user_id):
        calls.append(("http", user_id))
        return [{"title": "http post"}]

    def fake_post_processing(posts, method_label, days, llm_report_enabled=False, llm_model=None):
        calls.append(("post_process", method_label, len(posts), days))
        return {
            "value_result": (Path("/tmp/artifacts/valued_posts.json"), {"high_count": 1, "medium_count": 0, "low_count": 0}),
            "llm_report_result": {"generated": False, "output_path": None, "error_message": None},
        }

    monkeypatch.setattr(main, "fetch_posts_with_browser", fake_browser_fetch)
    monkeypatch.setattr(main, "fetch_user_posts", fake_http_fetch)
    monkeypatch.setattr(main, "run_post_processing", fake_post_processing)
    monkeypatch.setattr(main, "build_success_run_summary", lambda **kwargs: kwargs)
    monkeypatch.setattr(main, "generate_final_report", lambda summary: Path("/tmp/artifacts/final_report.md"))
    monkeypatch.setattr(main, "write_run_summary", lambda summary: calls.append(("summary", summary)) or "/tmp/artifacts/run_summary.json")
    monkeypatch.setattr(main, "print_run_summary", lambda summary, path: calls.append(("summary_print", summary["fetch_source_used"], path)))
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: Path("/tmp/artifacts"))

    main.main("target_user", source="http", days=14)

    assert calls == [
        ("http", "target_user"),
        ("post_process", "HTTP 请求", 1, 14),
        ("summary", {
            "user_id": "target_user",
            "days": 14,
            "source_mode": "http",
            "fetch_source_used": "http",
            "fallback_used": False,
            "raw_count": 1,
            "llm_report_enabled": False,
            "llm_report_path": None,
            "llm_report_generated": False,
            "llm_model": None,
            "llm_error_message": None,
            "primary_report_file": "/tmp/artifacts/final_report.md",
            "secondary_report_file": "/tmp/artifacts/weekly_summary.md",
            "files_generated": [],
        }),
        ("summary_print", "http", "/tmp/artifacts/run_summary.json"),
    ]


def test_write_run_summary_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: tmp_path)

    summary_path = main.write_run_summary({"run_success": True, "source_mode": "auto"})

    assert summary_path == tmp_path / "run_summary.json"
    assert json.loads(summary_path.read_text(encoding="utf-8")) == {
        "run_success": True,
        "source_mode": "auto",
    }


def test_build_success_run_summary_contains_primary_report_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "get_artifacts_dir", lambda: tmp_path)
    (tmp_path / "cleaning_summary.json").write_text(
        json.dumps({"clean_count": 8, "excluded_count": 2, "excluded_by_reason": {"older_than_window": 2}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "weekly_summary.json").write_text(json.dumps({"core_conclusion": "结论"}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "weekly_summary.md").write_text("# 周报", encoding="utf-8")

    summary = main.build_success_run_summary(
        user_id="slowisquick",
        days=7,
        source_mode="auto",
        fetch_source_used="browser",
        fallback_used=False,
        raw_count=10,
    )
    summary["primary_report_file"] = str(tmp_path / "final_report.md")
    summary["secondary_report_file"] = str(tmp_path / "weekly_summary.md")

    assert summary["primary_report_file"] == str(tmp_path / "final_report.md")
    assert summary["secondary_report_file"] == str(tmp_path / "weekly_summary.md")
