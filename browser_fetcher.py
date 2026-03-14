# -*- coding: utf-8 -*-
"""
browser_fetcher.py - 浏览器抓取探针
使用 Playwright 模拟真实浏览器访问雪球页面
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from utils import logger, get_artifacts_dir

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    class PlaywrightError(Exception):
        """Fallback when Playwright is unavailable at import time."""


def fetch_posts_with_browser(user_id: str) -> tuple[list, bool]:
    """
    使用 Playwright 浏览器抓取用户帖子

    Args:
        user_id: 雪球用户ID

    Returns:
        tuple: (posts列表, 是否成功)
    """
    url = f"https://xueqiu.com/u/{user_id}"
    logger.info("=" * 50)
    logger.info("启动浏览器抓取探针")
    logger.info("=" * 50)
    logger.info(f"目标用户: {user_id}")
    logger.info(f"目标URL: {url}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright 未安装，请先运行: pip install playwright")
        logger.error("然后运行: playwright install chromium")
        return [], False

    posts = []
    page_content = ""
    network_payloads = []
    screenshot_path = None

    try:
        with sync_playwright() as p:
            logger.info("启动 Chromium 浏览器...")
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)

            page = context.new_page()
            page.on("response", lambda response: _capture_network_payload(response, network_payloads))

            logger.info("Step 1: 访问雪球首页获取 cookies...")
            page.goto('https://xueqiu.com/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            logger.info(f"Step 2: 访问用户页面: {url}")
            response = page.goto(url, wait_until='networkidle', timeout=30000)

            logger.info(f"页面响应状态: {response.status if response else 'Unknown'}")
            logger.info(f"当前URL: {page.url}")

            logger.info("Step 3: 等待页面稳定...")
            page.wait_for_timeout(3000)

            if 'login' in page.url or 'passport' in page.url:
                logger.error("❌ 检测到重定向到登录页，需要登录才能访问")
                page_content = page.content()
                save_debug_files(page_content, None)
                browser.close()
                return [], False

            page_title = page.title()
            logger.info(f"页面标题: {page_title}")

            if any(keyword in page_title.lower() for keyword in ['验证', '验证码', 'captcha', 'waf', '安全']):
                logger.error("❌ 检测到验证码或 WAF 拦截")
                page_content = page.content()
                save_debug_files(page_content, None)
                browser.close()
                return [], False

            logger.info("Step 4: 尝试提取帖子数据...")
            page_content = page.content()
            posts = extract_posts_from_page(page, page_content, network_payloads)

            try:
                artifacts_dir = get_artifacts_dir()
                screenshot_path = artifacts_dir / "debug.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info(f"截图已保存: {screenshot_path}")
            except Exception as e:
                logger.warning(f"截图失败: {e}")

            browser.close()

        if posts:
            logger.info(f"✅ 成功提取 {len(posts)} 条帖子")
            return posts, True

        logger.error("❌ 未能提取到任何帖子数据")
        save_debug_files(page_content, screenshot_path)
        return [], False

    except Exception as e:
        logger.error(f"❌ 浏览器抓取异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        if page_content:
            save_debug_files(page_content, None)
        return [], False


def extract_posts_from_page(page, html: str, network_payloads: Optional[list] = None) -> list:
    """
    从页面中提取帖子数据，优先走数据层，DOM 仅作为最后兜底
    """
    logger.info("优先尝试页面内嵌数据提取...")
    posts = _extract_posts_from_embedded_data(page, html)
    if posts:
        logger.info(f"页面内嵌数据提取成功: {len(posts)} 条帖子")
        return posts

    logger.info("尝试页面接口响应数据提取...")
    posts = _extract_posts_from_network_payloads(network_payloads or [])
    if posts:
        logger.info(f"接口响应数据提取成功: {len(posts)} 条帖子")
        return posts

    logger.info("回退到 DOM 提取策略...")
    return _extract_posts_from_dom(page)


def _extract_posts_from_embedded_data(page, html: str) -> list[dict]:
    """优先从页面变量和内嵌 JSON 脚本中提取帖子数据"""
    candidate_sources = []

    try:
        data_candidates = page.evaluate(
            """
            () => {
                const candidates = [];
                const tryPush = (label, value) => {
                    if (typeof value !== 'undefined' && value !== null) {
                        candidates.push({ label, data: value });
                    }
                };

                tryPush('window.SNB.data', window.SNB && window.SNB.data);
                tryPush('window.SNB', window.SNB);
                tryPush('window.__INITIAL_STATE__', window.__INITIAL_STATE__);
                tryPush('window.__DATA__', window.__DATA__);
                tryPush('window.__NEXT_DATA__', window.__NEXT_DATA__);
                return candidates;
            }
            """
        )
        if data_candidates:
            candidate_sources.extend(data_candidates)
    except Exception as e:
        logger.warning(f"读取页面变量失败: {e}")

    script_patterns = [
        ("__NEXT_DATA__", r'<script[^>]+id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>'),
        ("__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;'),
        ("__DATA__", r'window\.__DATA__\s*=\s*(\{.*?\})\s*;'),
        ("SNB.data", r'window\.SNB\.data\s*=\s*(\{.*?\})\s*;'),
    ]
    for label, pattern in script_patterns:
        for match in re.finditer(pattern, html, re.DOTALL):
            try:
                candidate_sources.append({"label": f"script:{label}", "data": json.loads(match.group(1))})
            except json.JSONDecodeError:
                continue

    for source in candidate_sources:
        posts = _collect_posts_from_data(source.get("data"))
        if posts:
            logger.info(f"页面数据源命中: {source.get('label', 'unknown')}")
            return posts

    return []


def _capture_network_payload(response, network_payloads: list):
    """被动收集时间线接口响应"""
    url = response.url.lower()
    status = getattr(response, "status", None)
    if status != 200:
        return

    interesting_keywords = [
        "user_timeline.json",
        "original/timeline.json",
        "statuses/show.json",
        "statuses/original/show.json",
    ]
    if not any(keyword in url for keyword in interesting_keywords):
        return

    try:
        payload = response.json()
        network_payloads.append({"url": response.url, "data": payload})
    except Exception as e:
        logger.warning(f"读取接口响应失败: {response.url} - {e}")


def _extract_posts_from_network_payloads(network_payloads: list) -> list[dict]:
    """从已捕获的接口响应中提取帖子数据"""
    for payload in network_payloads:
        posts = _collect_posts_from_data(payload.get("data"))
        if posts:
            logger.info(f"接口响应命中: {payload.get('url')}")
            return posts
    return []


def _extract_posts_from_dom(page) -> list[dict]:
    """DOM 兜底提取逻辑"""
    posts = []
    seen_ids = set()

    logger.info("尝试滚动页面加载动态内容...")
    try:
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(1500)
    except Exception as e:
        logger.warning(f"页面滚动失败: {e}")

    logger.info("尝试策略1: 查找 timeline__item 元素...")
    try:
        articles = page.query_selector_all('article.timeline__item, div.timeline__item, [class*="timeline"][class*="item"]')
        logger.info(f"找到 {len(articles)} 个 timeline 元素")

        if articles:
            try:
                first_html = articles[0].evaluate("el => el.outerHTML")
                logger.info(f"第一条帖子 HTML 片段 (前800字符): {first_html[:800] if first_html else 'None'}")
            except Exception as e:
                logger.warning(f"无法获取HTML片段: {e}")

        for i, article in enumerate(articles[:20]):
            try:
                post = extract_post_data(article, i)
                post_id = post.get('id') if post else None
                if post and (not post_id or post_id not in seen_ids):
                    if post_id:
                        seen_ids.add(post_id)
                    posts.append(post)
            except Exception as e:
                logger.warning(f"提取第 {i + 1} 条帖子失败: {e}")
    except Exception as e:
        logger.warning(f"策略1失败: {e}")

    if posts:
        return posts

    logger.info("尝试策略2: 查找其他文章容器...")
    selectors = [
        '[class*="timeline__item"]',
        '[data-id]',
        '.article-item',
        '.status-item',
    ]

    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
            if elements:
                logger.info(f"选择器 '{selector}' 找到 {len(elements)} 个元素")
                for i, elem in enumerate(elements[:20]):
                    try:
                        post = extract_post_data(elem, i)
                        post_id = post.get('id') if post else None
                        if post and (not post_id or post_id not in seen_ids):
                            if post_id:
                                seen_ids.add(post_id)
                            posts.append(post)
                    except Exception:
                        continue
                if posts:
                    break
        except Exception as e:
            logger.warning(f"选择器 '{selector}' 失败: {e}")

    return posts


def extract_post_data(element, index: int = 0) -> dict:
    """从单个元素提取帖子数据，包含增强的时间提取逻辑"""
    post = {}

    try:
        data_id = element.get_attribute('data-id')
        if data_id:
            post['id'] = data_id
    except (AttributeError, TypeError, PlaywrightError):
        pass

    title = None
    for selector in ['.timeline__item__title', '.article__title', 'a[title]', '.title', 'h1 a', 'h2 a', 'h3 a', 'h4 a', 'a.caption', '[class*="title"]']:
        try:
            title_elem = element.query_selector(selector)
            if title_elem:
                title_text = title_elem.inner_text().strip()
                if title_text and len(title_text) > 0:
                    title = title_text
                    post['title'] = title
                    href = title_elem.get_attribute('href')
                    if href:
                        post['url'] = href if href.startswith('http') else f"https://xueqiu.com{href}"
                    break
        except (AttributeError, TypeError, PlaywrightError):
            continue

    content = None
    for selector in ['.timeline__item__content', '.article__content', '.content', '.text', 'p', '[class*="content"]', '[class*="text"]', '.timeline__item__summary']:
        try:
            content_elem = element.query_selector(selector)
            if content_elem:
                content_text = content_elem.inner_text().strip()
                if content_text and len(content_text) > 0:
                    content = content_text[:500]
                    post['content'] = content
                    break
        except (AttributeError, TypeError, PlaywrightError):
            continue

    if not title and content:
        post['title'] = content[:50] + "..." if len(content) > 50 else content

    time_found = False
    time_selectors = [
        '.timeline__item__time',
        '.article__time',
        '.caption-info time',
        '.time',
        '.date',
        '[datetime]',
        '[class*="time"]',
        '[class*="date"]',
        'span[class*="time"]',
        'span[class*="date"]',
        'time',
    ]

    for selector in time_selectors:
        try:
            time_elem = element.query_selector(selector)
            if time_elem:
                time_text = time_elem.inner_text().strip()
                if time_text and len(time_text) < 50:
                    if any(keyword in time_text for keyword in ['分钟', '小时', '天', '昨天', '今天', '月', '年', '刚刚', ':', '-']):
                        post['time'] = time_text
                        time_found = True
                        break
                datetime_attr = time_elem.get_attribute('datetime')
                if datetime_attr:
                    post['datetime'] = datetime_attr
                    time_found = True
                    break
        except (AttributeError, TypeError, PlaywrightError):
            continue

    if not time_found:
        try:
            full_text = element.inner_text()
            time_patterns = [
                r'(\d+)分钟前',
                r'(\d+)小时前',
                r'刚刚',
                r'昨天\s*\d{1,2}:\d{2}',
                r'今天\s*\d{1,2}:\d{2}',
                r'\d{2}-\d{2}\s+\d{1,2}:\d{2}',
                r'\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}',
            ]
            for pattern in time_patterns:
                match = re.search(pattern, full_text)
                if match:
                    post['time'] = match.group(0)
                    time_found = True
                    break
        except (AttributeError, TypeError, PlaywrightError):
            pass

    if index < 3:
        if time_found:
            logger.info(f"  第{index + 1}条帖子时间提取成功: {post.get('time') or post.get('datetime')}")
        else:
            try:
                debug_text = element.inner_text()[:100] if hasattr(element, 'inner_text') else 'N/A'
                logger.info(f"  第{index + 1}条帖子未提取到时间，内容片段: {debug_text[:100]}...")
            except (AttributeError, TypeError, PlaywrightError):
                logger.info(f"  第{index + 1}条帖子未提取到时间")

    if post.get('time') and not post.get('datetime'):
        post['published_at_raw'] = post['time']
    elif post.get('datetime') and not post.get('time'):
        post['time'] = post['datetime']
        post['published_at_raw'] = post['datetime']
    elif post.get('time'):
        post['published_at_raw'] = post['time']

    return post if post.get('title') or post.get('content') else None


def _collect_posts_from_data(data) -> list[dict]:
    """从任意页面数据结构中提取帖子列表"""
    candidates = _find_post_item_lists(data)
    for items in candidates:
        posts = _normalize_posts(items)
        if posts:
            return posts
    return []


def _find_post_item_lists(data) -> list[list]:
    """在嵌套数据结构中定位可能的帖子列表"""
    results = []
    seen = set()

    def walk(node):
        if isinstance(node, list):
            if node and any(isinstance(item, dict) and _looks_like_post_item(item) for item in node):
                marker = id(node)
                if marker not in seen:
                    seen.add(marker)
                    results.append(node)
            for item in node:
                walk(item)
            return

        if isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(data)
    return results


def _looks_like_post_item(item: dict) -> bool:
    """判断字典是否像一条帖子数据"""
    if not isinstance(item, dict):
        return False

    if "description" in item and ("created_at" in item or "id" in item):
        return True

    if "text" in item and ("created_at" in item or "id" in item):
        return True

    return False


def _normalize_posts(items: list[dict]) -> list[dict]:
    """归一化帖子数据结构"""
    posts = []
    seen_ids = set()

    for item in items:
        post = _normalize_post_item(item)
        if not post:
            continue

        post_id = post.get("id")
        if post_id and post_id in seen_ids:
            continue
        if post_id:
            seen_ids.add(post_id)

        posts.append(post)

    return posts


def _normalize_post_item(item: dict) -> Optional[dict]:
    """把接口或页面数据中的单条记录转换为项目统一结构"""
    if not isinstance(item, dict):
        return None

    content = _strip_html(item.get("description") or item.get("text") or item.get("content") or "")
    title = (item.get("title") or "").strip()
    if not title and content:
        title = content[:50] + "..." if len(content) > 50 else content

    if not title and not content:
        return None

    post = {
        "id": str(item.get("id")) if item.get("id") is not None else None,
        "title": title,
        "content": content,
    }

    time_value = _format_created_at(item.get("created_at") or item.get("time"))
    if time_value:
        post["time"] = time_value
        post["published_at_raw"] = time_value

    url = _build_post_url(item)
    if url:
        post["url"] = url

    retweeted = item.get("retweeted_status")
    if isinstance(retweeted, dict) and retweeted.get("description") and not post["content"]:
        post["content"] = _strip_html(retweeted.get("description", ""))

    return post


def _build_post_url(item: dict) -> Optional[str]:
    """从数据层结构里尽量恢复帖子 URL"""
    direct_url = item.get("target") or item.get("url")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url if direct_url.startswith("http") else f"https://xueqiu.com{direct_url}"

    user = item.get("user")
    status_id = item.get("id")
    if not isinstance(user, dict) or not status_id:
        return None

    profile = user.get("profile")
    if isinstance(profile, str) and profile.strip():
        return f"https://xueqiu.com{profile}/{status_id}"

    domain = user.get("domain")
    if isinstance(domain, str) and domain.strip():
        return f"https://xueqiu.com/{domain}/{status_id}"

    return None


def _format_created_at(value) -> Optional[str]:
    """统一 created_at 为 cleaner 可解析的时间字符串"""
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            timestamp = int(stripped)
            timestamp = timestamp / 1000 if timestamp > 10**11 else timestamp
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        return stripped

    return None


def _strip_html(text: str) -> str:
    """移除接口返回文本中的 HTML 标签并收敛空白"""
    if not text:
        return ""

    cleaned = re.sub(r"<br\s*/?>", "\n", str(text), flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def save_posts_to_json(posts: list):
    """保存帖子到 JSON 文件"""
    artifacts_dir = get_artifacts_dir()
    file_path = artifacts_dir / "raw_posts.json"

    has_time = sum(1 for p in posts if p.get('time') or p.get('datetime') or p.get('published_at_raw'))
    logger.info(f"💾 保存 {len(posts)} 条帖子，其中 {has_time} 条有时间字段")

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 帖子数据已保存: {file_path}")


def save_debug_files(html_content: str, screenshot_path: Path):
    """保存调试文件"""
    artifacts_dir = get_artifacts_dir()

    html_path = artifacts_dir / "debug.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"调试 HTML 已保存: {html_path}")

    if screenshot_path:
        logger.info(f"调试截图已保存: {screenshot_path}")
