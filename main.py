# -*- coding: utf-8 -*-
"""
main.py - 雪球抓取入口
优先使用浏览器探针，失败则回退到 HTTP 方式
"""
import argparse
import json
from pathlib import Path
from typing import Optional
from fetcher import fetch_user_posts
from browser_fetcher import fetch_posts_with_browser
from utils import logger, save_to_json, get_artifacts_dir, set_artifacts_dir
from cleaner import clean_and_filter_posts
from value_scorer import score_clean_posts
from summarizer import generate_weekly_summary
from llm_reporter import generate_llm_report
from final_reporter import generate_final_report, FINAL_REPORT_FILENAME
import llm_config


DEFAULT_USER_ID = "slowisquick"
DEFAULT_DAYS = 7
DEFAULT_SOURCE = "auto"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="抓取雪球用户公开帖子并生成本周汇总")
    parser.add_argument(
        "user_id_positional",
        nargs="?",
        default=None,
        help="目标雪球用户ID（兼容旧用法）",
    )
    parser.add_argument("--user-id", dest="user_id", default=None, help=f"目标雪球用户ID，默认: {DEFAULT_USER_ID}")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"清洗最近多少天的数据，默认: {DEFAULT_DAYS}")
    parser.add_argument(
        "--source",
        choices=["auto", "browser", "http"],
        default=DEFAULT_SOURCE,
        help=f"抓取来源策略，默认: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="自定义输出目录，默认使用项目内 artifacts/",
    )
    parser.add_argument(
        "--llm-report",
        action="store_true",
        help="在规则摘要之后额外生成 LLM 深度报告（默认关闭）",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help=f"覆盖 LLM 模型名，默认: {llm_config.LLM_DEFAULT_MODEL}",
    )
    return parser.parse_args()


def resolve_cli_options(args) -> tuple[str, int, str, Optional[Path], bool, Optional[str]]:
    """统一解析 CLI 参数"""
    user_id = args.user_id or args.user_id_positional or DEFAULT_USER_ID
    if args.days <= 0:
        raise ValueError("--days 必须是正整数")
    return user_id, args.days, args.source, args.artifacts_dir, args.llm_report, args.llm_model


def print_banner(user_id: str):
    """打印程序横幅"""
    print("\n" + "=" * 60)
    print("雪球用户帖子抓取工具")
    print("=" * 60)
    print(f"目标用户: {user_id}")
    print("=" * 60)


def print_fetch_success(posts: list, method_label: str, raw_output_path: Path):
    """打印抓取成功信息"""
    print("\n" + "=" * 60)
    print(f"✅ 抓取成功 - 使用 {method_label}")
    print("=" * 60)
    print(f"抓取帖子数量: {len(posts)}")
    print(f"保存路径: {raw_output_path}")
    print("\n前3条帖子:")
    print("-" * 60)

    for i, post in enumerate(posts[:3], 1):
        title = post.get("title", "无标题")
        content = post.get("content", "")
        if not title and content:
            title = content[:50] + "..." if len(content) > 50 else content

        print(f"{i}. {title}")

        time_str = post.get("time") or post.get("datetime") or post.get("published_at_raw")
        if time_str:
            print(f"   时间: {time_str}")

        if post.get("url"):
            print(f"   链接: {post.get('url')}")

        print()

    print("=" * 60)


def print_clean_posts_sample():
    """打印清洗后帖子样本"""
    clean_posts_path = get_artifacts_dir() / "clean_posts.json"
    if not clean_posts_path.exists():
        return

    with open(clean_posts_path, "r", encoding="utf-8") as f:
        clean_posts = json.load(f)

    if not clean_posts:
        return

    print("\n📋 clean_posts.json 前3条样本:")
    print("-" * 60)
    for i, post in enumerate(clean_posts[:3], 1):
        title = post.get("title", "无标题")[:40]
        pub_time = post.get("published_at", "未解析")
        print(f"{i}. {title}...")
        print(f"   发布时间: {pub_time}")
        print()
    print("-" * 60)


def _read_json_if_exists(path: Path) -> Optional[dict]:
    """读取存在的 JSON 文件"""
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_run_summary(summary: dict) -> Path:
    """写入运行摘要"""
    summary_path = get_artifacts_dir() / "run_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary_path


def print_run_summary(summary: dict, summary_path: Path):
    """打印最终运行摘要"""
    print(
        "运行完成："
        f"source_mode={summary['source_mode']}, "
        f"fetch_source_used={summary.get('fetch_source_used')}, "
        f"raw={summary.get('raw_count')}, "
        f"clean={summary.get('clean_count')}, "
        f"excluded={summary.get('excluded_count')}, "
        f"llm_report_generated={summary.get('llm_report_generated')}"
    )
    if summary.get("primary_report_file"):
        print(f"主结果：{summary['primary_report_file']}")
    print(f"运行摘要：{summary_path}")


def build_success_run_summary(
    user_id: str,
    days: int,
    source_mode: str,
    fetch_source_used: str,
    fallback_used: bool,
    raw_count: int,
    llm_report_enabled: bool = False,
    llm_report_path: Optional[Path] = None,
    llm_report_generated: bool = False,
    llm_model: Optional[str] = None,
    llm_error_message: Optional[str] = None,
) -> dict:
    """构建成功运行摘要"""
    artifacts_dir = get_artifacts_dir()
    cleaning_summary = _read_json_if_exists(artifacts_dir / "cleaning_summary.json") or {}
    weekly_summary_path = artifacts_dir / "weekly_summary.json"
    summary_generated = weekly_summary_path.exists()

    files_generated = []
    for filename in [
        "raw_posts.json",
        "clean_posts.json",
        "valued_posts.json",
        "excluded_posts.json",
        "cleaning_summary.json",
        "weekly_summary.md",
        "weekly_summary.json",
        FINAL_REPORT_FILENAME,
        llm_config.LLM_REPORT_FILENAME,
        llm_config.LLM_REPORT_META_FILENAME,
        llm_config.LLM_SOURCE_MATERIAL_FILENAME,
        "debug.html",
        "debug.png",
    ]:
        file_path = artifacts_dir / filename
        if file_path.exists():
            files_generated.append(str(file_path))

    return {
        "user_id": user_id,
        "days": days,
        "source_mode": source_mode,
        "fetch_source_used": fetch_source_used,
        "fallback_used": fallback_used,
        "raw_count": raw_count,
        "clean_count": cleaning_summary.get("clean_count"),
        "excluded_count": cleaning_summary.get("excluded_count"),
        "excluded_by_reason": cleaning_summary.get("excluded_by_reason", {}),
        "summary_generated": summary_generated,
        "llm_report_enabled": llm_report_enabled,
        "llm_report_generated": llm_report_generated,
        "llm_report_path": str(llm_report_path) if llm_report_path else None,
        "llm_model": llm_model,
        "llm_output_file": str(llm_report_path) if llm_report_path else None,
        "llm_error_message": llm_error_message,
        "primary_report_file": None,
        "secondary_report_file": None,
        "artifacts_dir": str(artifacts_dir),
        "files_generated": files_generated,
        "run_success": True,
        "error_message": None,
    }


def build_failure_run_summary(
    user_id: str,
    days: int,
    source_mode: str,
    error_message: str,
    fetch_source_used: Optional[str] = None,
    fallback_used: bool = False,
    llm_report_enabled: bool = False,
    llm_report_generated: bool = False,
    llm_model: Optional[str] = None,
    llm_error_message: Optional[str] = None,
) -> dict:
    """构建失败运行摘要"""
    artifacts_dir = get_artifacts_dir()
    files_generated = []
    for filename in [
        "raw_posts.json",
        "clean_posts.json",
        "valued_posts.json",
        "excluded_posts.json",
        "cleaning_summary.json",
        "weekly_summary.md",
        "weekly_summary.json",
        FINAL_REPORT_FILENAME,
        llm_config.LLM_REPORT_FILENAME,
        llm_config.LLM_REPORT_META_FILENAME,
        llm_config.LLM_SOURCE_MATERIAL_FILENAME,
        "debug.html",
        "debug.png",
    ]:
        file_path = artifacts_dir / filename
        if file_path.exists():
            files_generated.append(str(file_path))

    return {
        "user_id": user_id,
        "days": days,
        "source_mode": source_mode,
        "fetch_source_used": fetch_source_used,
        "fallback_used": fallback_used,
        "raw_count": None,
        "clean_count": None,
        "excluded_count": None,
        "excluded_by_reason": {},
        "summary_generated": False,
        "llm_report_enabled": llm_report_enabled,
        "llm_report_generated": llm_report_generated,
        "llm_report_path": None,
        "llm_model": llm_model,
        "llm_output_file": None,
        "llm_error_message": llm_error_message,
        "primary_report_file": None,
        "secondary_report_file": None,
        "artifacts_dir": str(artifacts_dir),
        "files_generated": files_generated,
        "run_success": False,
        "error_message": error_message,
    }


def run_post_processing(
    posts: list,
    method_label: str,
    days: int,
    llm_report_enabled: bool = False,
    llm_model: Optional[str] = None,
):
    """统一处理保存原始数据、清洗过滤和生成总结"""
    raw_output_path = save_to_json(posts, "raw_posts.json")
    print_fetch_success(posts, method_label, raw_output_path)
    logger.info(f"{method_label}抓取完成")

    print("\n📌 Step 2: 数据清洗与过滤...")
    clean_result = clean_and_filter_posts(raw_output_path, days=days)
    print_clean_posts_sample()

    value_result = score_clean_posts(get_artifacts_dir() / "clean_posts.json")

    print("\n📌 Step 4: 生成规则摘要...")
    summary_result = generate_weekly_summary()
    llm_report_result = {
        "enabled": llm_report_enabled,
        "generated": False,
        "output_path": None,
        "metadata": None,
        "error_message": None,
    }

    if llm_report_enabled:
        print("\n📌 Step 5: 生成 LLM 深度报告...")
        try:
            llm_report_path, llm_metadata = generate_llm_report(
                clean_posts_path=get_artifacts_dir() / "clean_posts.json",
                model_override=llm_model,
            )
            llm_report_result = {
                "enabled": True,
                "generated": True,
                "output_path": str(llm_report_path),
                "metadata": llm_metadata,
                "error_message": None,
            }
            print(f"LLM 报告: {llm_report_path}")
        except Exception as e:
            llm_report_result = {
                "enabled": True,
                "generated": False,
                "output_path": None,
                "error_message": str(e),
            }
            logger.warning("LLM 报告生成失败: %s", e)
            print(f"LLM 报告未生成: {e}")

    return {
        "raw_output_path": raw_output_path,
        "clean_result": clean_result,
        "value_result": value_result,
        "summary_result": summary_result,
        "llm_report_result": llm_report_result,
    }


def print_fetch_failure(source: str):
    """打印抓取失败信息"""
    print("\n" + "=" * 60)
    if source == "auto":
        print("❌ 抓取结果: 失败 - browser 和 HTTP 均未获取到帖子数据")
    elif source == "browser":
        print("❌ 抓取结果: 失败 - browser 未获取到帖子数据")
    else:
        print("❌ 抓取结果: 失败 - HTTP 未获取到帖子数据")
    print("=" * 60)
    print("可能原因:")
    print("  1. 需要登录才能访问")
    print("  2. 被 WAF 或验证码拦截")
    print("  3. 页面结构发生变化")
    print("  4. 网络连接问题")
    print(f"\n请检查 {get_artifacts_dir()}/debug.html 和 {get_artifacts_dir()}/debug.png 获取详情")
    print("=" * 60)
    logger.error("抓取失败 - source=%s", source)


def main(
    user_id: Optional[str] = None,
    days: int = DEFAULT_DAYS,
    source: str = DEFAULT_SOURCE,
    artifacts_dir: Optional[Path] = None,
    llm_report: bool = False,
    llm_model: Optional[str] = None,
):
    """主入口函数"""
    if user_id is None:
        args = parse_args()
        user_id, days, source, artifacts_dir, llm_report, llm_model = resolve_cli_options(args)

    set_artifacts_dir(artifacts_dir)

    print_banner(user_id)
    print(f"抓取策略: {source}")
    print(f"时间窗口: 最近 {days} 天")
    print(f"输出目录: {get_artifacts_dir()}")
    print(f"LLM 报告: {'开启' if llm_report else '关闭'}")
    fallback_used = False

    if source in {"auto", "browser"}:
        print("\n📌 Step 1: 尝试浏览器抓取探针...")
        posts, browser_success = fetch_posts_with_browser(user_id)

        if browser_success and posts:
            try:
                processing_result = run_post_processing(posts, "浏览器探针", days, llm_report_enabled=llm_report, llm_model=llm_model)
                run_summary = build_success_run_summary(
                    user_id=user_id,
                    days=days,
                    source_mode=source,
                    fetch_source_used="browser",
                    fallback_used=False,
                    raw_count=len(posts),
                    llm_report_enabled=llm_report,
                    llm_report_path=Path(processing_result["llm_report_result"]["output_path"]) if processing_result["llm_report_result"]["output_path"] else None,
                    llm_report_generated=processing_result["llm_report_result"]["generated"],
                    llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
                    llm_error_message=processing_result["llm_report_result"]["error_message"],
                )
                final_report_path = generate_final_report(run_summary)
                run_summary["primary_report_file"] = str(final_report_path)
                run_summary["secondary_report_file"] = (
                    processing_result["llm_report_result"]["output_path"]
                    if processing_result["llm_report_result"]["generated"]
                    else str(get_artifacts_dir() / "weekly_summary.md")
                )
                run_summary.setdefault("files_generated", [])
                if final_report_path.exists() and str(final_report_path) not in run_summary["files_generated"]:
                    run_summary["files_generated"].append(str(final_report_path))
                summary_path = write_run_summary(run_summary)
                print_run_summary(run_summary, summary_path)
            except Exception as e:
                logger.error(f"后处理失败: {e}")
                failure_summary = build_failure_run_summary(
                    user_id=user_id,
                    days=days,
                    source_mode=source,
                    error_message=str(e),
                    fetch_source_used="browser",
                    fallback_used=False,
                    llm_report_enabled=llm_report,
                    llm_report_generated=False,
                    llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
                    llm_error_message=str(e) if llm_report else None,
                )
                write_run_summary(failure_summary)
            return

        if source == "browser":
            failure_summary = build_failure_run_summary(
                user_id=user_id,
                days=days,
                source_mode=source,
                error_message="browser 未获取到帖子数据",
                fetch_source_used="browser",
                fallback_used=False,
                llm_report_enabled=llm_report,
                llm_report_generated=False,
                llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
                llm_error_message=None,
            )
            write_run_summary(failure_summary)
            print_fetch_failure(source)
            return

    if source == "auto":
        print("\n📌 Step 2: 浏览器探针未成功，回退到 HTTP 请求...")
        fallback_used = True
    elif source == "http":
        print("\n📌 Step 1: 直接使用 HTTP 请求...")

    posts = fetch_user_posts(user_id)

    if posts:
        try:
            processing_result = run_post_processing(posts, "HTTP 请求", days, llm_report_enabled=llm_report, llm_model=llm_model)
            run_summary = build_success_run_summary(
                user_id=user_id,
                days=days,
                source_mode=source,
                fetch_source_used="http",
                fallback_used=fallback_used,
                raw_count=len(posts),
                llm_report_enabled=llm_report,
                llm_report_path=Path(processing_result["llm_report_result"]["output_path"]) if processing_result["llm_report_result"]["output_path"] else None,
                llm_report_generated=processing_result["llm_report_result"]["generated"],
                llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
                llm_error_message=processing_result["llm_report_result"]["error_message"],
            )
            final_report_path = generate_final_report(run_summary)
            run_summary["primary_report_file"] = str(final_report_path)
            run_summary["secondary_report_file"] = (
                processing_result["llm_report_result"]["output_path"]
                if processing_result["llm_report_result"]["generated"]
                else str(get_artifacts_dir() / "weekly_summary.md")
            )
            run_summary.setdefault("files_generated", [])
            if final_report_path.exists() and str(final_report_path) not in run_summary["files_generated"]:
                run_summary["files_generated"].append(str(final_report_path))
            summary_path = write_run_summary(run_summary)
            print_run_summary(run_summary, summary_path)
        except Exception as e:
            logger.error(f"后处理失败: {e}")
            failure_summary = build_failure_run_summary(
                user_id=user_id,
                days=days,
                source_mode=source,
                error_message=str(e),
                fetch_source_used="http",
                fallback_used=fallback_used,
                llm_report_enabled=llm_report,
                llm_report_generated=False,
                llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
                llm_error_message=str(e) if llm_report else None,
            )
            write_run_summary(failure_summary)
        return

    failure_message = "auto 模式下 browser 和 HTTP 均未获取到帖子数据" if source == "auto" else f"{source} 未获取到帖子数据"
    failure_summary = build_failure_run_summary(
        user_id=user_id,
        days=days,
        source_mode=source,
        error_message=failure_message,
        fetch_source_used="http" if source in {"auto", "http"} else "browser",
        fallback_used=fallback_used,
        llm_report_enabled=llm_report,
        llm_report_generated=False,
        llm_model=(llm_model or llm_config.LLM_DEFAULT_MODEL) if llm_report else None,
        llm_error_message=None,
    )
    write_run_summary(failure_summary)
    print_fetch_failure(source)


if __name__ == "__main__":
    main()
