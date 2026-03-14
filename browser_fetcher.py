# -*- coding: utf-8 -*-
"""
browser_fetcher.py - 浏览器抓取探针
使用 Playwright 模拟真实浏览器访问雪球页面
"""
import json
import re
from pathlib import Path
from utils import logger, get_artifacts_dir


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
    
    try:
        with sync_playwright() as p:
            # 启动浏览器（使用 chromium，无头模式）
            logger.info("启动 Chromium 浏览器...")
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            # 创建新页面
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # 注入脚本隐藏 webdriver 标志
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
            
            page = context.new_page()
            
            # 先访问首页
            logger.info("Step 1: 访问雪球首页获取 cookies...")
            page.goto('https://xueqiu.com/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)
            
            # 访问目标用户页面
            logger.info(f"Step 2: 访问用户页面: {url}")
            response = page.goto(url, wait_until='networkidle', timeout=30000)
            
            logger.info(f"页面响应状态: {response.status if response else 'Unknown'}")
            logger.info(f"当前URL: {page.url}")
            
            # 等待页面加载
            logger.info("Step 3: 等待页面稳定...")
            page.wait_for_timeout(3000)
            
            # 检查是否被重定向到登录页
            if 'login' in page.url or 'passport' in page.url:
                logger.error("❌ 检测到重定向到登录页，需要登录才能访问")
                page_content = page.content()
                save_debug_files(page_content, None)
                browser.close()
                return [], False
            
            # 检查是否有验证码或 WAF
            page_title = page.title()
            logger.info(f"页面标题: {page_title}")
            
            if any(keyword in page_title.lower() for keyword in ['验证', '验证码', 'captcha', 'waf', '安全']):
                logger.error("❌ 检测到验证码或 WAF 拦截")
                page_content = page.content()
                save_debug_files(page_content, None)
                browser.close()
                return [], False
            
            # 尝试提取帖子数据
            logger.info("Step 4: 尝试提取帖子数据...")
            posts = extract_posts_from_page(page)
            
            # 保存页面内容用于调试
            page_content = page.content()
            
            # 截图用于调试
            screenshot_path = None
            try:
                artifacts_dir = get_artifacts_dir()
                screenshot_path = artifacts_dir / "debug.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info(f"截图已保存: {screenshot_path}")
            except Exception as e:
                logger.warning(f"截图失败: {e}")
            
            browser.close()
        
        # 根据结果保存文件
        if posts:
            logger.info(f"✅ 成功提取 {len(posts)} 条帖子")
            save_posts_to_json(posts)
            return posts, True
        else:
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


def extract_posts_from_page(page) -> list:
    """
    从页面中提取帖子数据
    尝试多种选择器策略
    """
    posts = []
    seen_ids = set()  # 用于去重
    
    # 首先滚动页面以加载更多动态内容
    logger.info("尝试滚动页面加载动态内容...")
    try:
        for _ in range(3):  # 滚动3次
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(1500)
    except Exception as e:
        logger.warning(f"页面滚动失败: {e}")
    
    # 策略1: 查找 timeline__item 元素（包括 article 和 div）
    logger.info("尝试策略1: 查找 timeline__item 元素...")
    try:
        # 使用宽松选择器匹配所有 timeline 相关元素
        articles = page.query_selector_all('article.timeline__item, div.timeline__item, [class*="timeline"][class*="item"]')
        logger.info(f"找到 {len(articles)} 个 timeline 元素")
        
        # 调试：打印第一个元素的HTML结构
        if articles:
            try:
                first_html = articles[0].evaluate("el => el.outerHTML")
                logger.info(f"第一条帖子 HTML 片段 (前800字符): {first_html[:800] if first_html else 'None'}")
            except Exception as e:
                logger.warning(f"无法获取HTML片段: {e}")
        
        for i, article in enumerate(articles[:20]):  # 限制前20条
            try:
                post = extract_post_data(article, i)
                # 使用 id 去重
                post_id = post.get('id') if post else None
                if post and (not post_id or post_id not in seen_ids):
                    if post_id:
                        seen_ids.add(post_id)
                    posts.append(post)
            except Exception as e:
                logger.warning(f"提取第 {i+1} 条帖子失败: {e}")
    except Exception as e:
        logger.warning(f"策略1失败: {e}")
    
    # 策略2: 如果策略1没拿到数据，尝试其他选择器
    if not posts:
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
                        except Exception as e:
                            continue
                    if posts:
                        break
            except Exception as e:
                continue
    
    # 策略3: 尝试从页面 JavaScript 变量中提取
    if not posts:
        logger.info("尝试策略3: 从页面 JS 变量提取...")
        try:
            posts = extract_from_page_js(page)
        except Exception as e:
            logger.warning(f"策略3失败: {e}")
    
    return posts


def extract_post_data(element, index: int = 0) -> dict:
    """从单个元素提取帖子数据，包含增强的时间提取逻辑"""
    post = {}
    
    try:
        # 提取 data-id
        data_id = element.get_attribute('data-id')
        if data_id:
            post['id'] = data_id
    except:
        pass
    
    # 提取标题 - 增强选择器
    title = None
    for selector in ['.timeline__item__title', '.article__title', 'a[title]', '.title', 'h1 a', 'h2 a', 'h3 a', 'h4 a', 'a.caption', '[class*="title"]']:
        try:
            title_elem = element.query_selector(selector)
            if title_elem:
                title_text = title_elem.inner_text().strip()
                if title_text and len(title_text) > 0:
                    title = title_text
                    post['title'] = title
                    # 提取链接
                    href = title_elem.get_attribute('href')
                    if href:
                        post['url'] = href if href.startswith('http') else f"https://xueqiu.com{href}"
                    break
        except:
            continue
    
    # 提取内容
    content = None
    for selector in ['.timeline__item__content', '.article__content', '.content', '.text', 'p', '[class*="content"]', '[class*="text"]', '.timeline__item__summary']:
        try:
            content_elem = element.query_selector(selector)
            if content_elem:
                content_text = content_elem.inner_text().strip()
                if content_text and len(content_text) > 0:
                    content = content_text[:500]  # 限制长度
                    post['content'] = content
                    break
        except:
            continue
    
    # 如果没有标题但有内容，用内容前50字作为标题
    if not title and content:
        post['title'] = content[:50] + "..." if len(content) > 50 else content
    
    # ============ 提取时间 - 增强选择器逻辑 ============
    time_found = False
    
    # 1. 首先尝试各种时间选择器
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
                # 过滤掉太长的时间文本（可能是误提取的内容）
                if time_text and len(time_text) < 50:
                    # 确保是时间格式（包含数字和常用时间关键词）
                    if any(keyword in time_text for keyword in ['分钟', '小时', '天', '昨天', '今天', '月', '年', '刚刚', ':', '-']):
                        post['time'] = time_text
                        time_found = True
                        break
                # 尝试获取 datetime 属性
                datetime_attr = time_elem.get_attribute('datetime')
                if datetime_attr:
                    post['datetime'] = datetime_attr
                    time_found = True
                    break
        except:
            continue
    
    # 2. 如果还是没找到时间，尝试通过正则表达式从完整文本中提取
    if not time_found:
        try:
            full_text = element.inner_text()
            # 匹配雪球常见时间格式
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
        except:
            pass
    
    # 3. 调试输出（仅前3条）
    if index < 3:
        if time_found:
            logger.info(f"  第{index+1}条帖子时间提取成功: {post.get('time') or post.get('datetime')}")
        else:
            # 尝试获取一些调试信息
            try:
                debug_text = element.inner_text()[:100] if hasattr(element, 'inner_text') else 'N/A'
                logger.info(f"  第{index+1}条帖子未提取到时间，内容片段: {debug_text[:100]}...")
            except:
                logger.info(f"  第{index+1}条帖子未提取到时间")
    
    # 统一时间字段名
    if post.get('time') and not post.get('datetime'):
        post['published_at_raw'] = post['time']
    elif post.get('datetime') and not post.get('time'):
        post['time'] = post['datetime']
        post['published_at_raw'] = post['datetime']
    elif post.get('time'):
        post['published_at_raw'] = post['time']
    
    return post if post.get('title') or post.get('content') else None


def extract_from_page_js(page) -> list:
    """尝试从页面 JavaScript 变量中提取帖子数据"""
    posts = []
    
    try:
        # 尝试读取 SNB.data 或其他可能的数据变量
        data_vars = [
            'SNB.data',
            'window.SNB',
            '__INITIAL_STATE__',
            '__DATA__',
        ]
        
        for var_name in data_vars:
            try:
                data = page.evaluate(f'() => typeof {var_name} !== "undefined" ? {var_name} : null')
                if data:
                    logger.info(f"找到页面变量: {var_name}")
                    # 这里可以进一步解析数据结构
                    break
            except:
                continue
    except Exception as e:
        logger.warning(f"读取页面 JS 变量失败: {e}")
    
    return posts


def save_posts_to_json(posts: list):
    """保存帖子到 JSON 文件"""
    artifacts_dir = get_artifacts_dir()
    file_path = artifacts_dir / "raw_posts.json"
    
    # 统计时间字段提取情况
    has_time = sum(1 for p in posts if p.get('time') or p.get('datetime') or p.get('published_at_raw'))
    logger.info(f"💾 保存 {len(posts)} 条帖子，其中 {has_time} 条有时间字段")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 帖子数据已保存: {file_path}")


def save_debug_files(html_content: str, screenshot_path: Path):
    """保存调试文件"""
    artifacts_dir = get_artifacts_dir()
    
    # 保存 HTML
    html_path = artifacts_dir / "debug.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"调试 HTML 已保存: {html_path}")
    
    # 截图路径已在调用处打印
    if screenshot_path:
        logger.info(f"调试截图已保存: {screenshot_path}")
