# -*- coding: utf-8 -*-
"""
fetcher.py - 雪球用户帖子抓取模块
"""
import requests
from bs4 import BeautifulSoup
from utils import logger, save_html


def fetch_user_posts(user_id: str) -> list:
    """
    抓取雪球用户公开页面的帖子列表
    
    Args:
        user_id: 雪球用户ID，如 "slowisquick"
    
    Returns:
        list: 帖子列表，每个帖子是一个字典
    """
    url = f"https://xueqiu.com/u/{user_id}"
    logger.info(f"开始抓取用户: {user_id}")
    logger.info(f"目标URL: {url}")
    
    # 设置请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        # 创建 session 以保持 cookies
        session = requests.Session()
        
        # 先访问首页获取必要的 cookies
        logger.info("访问雪球首页获取 cookies...")
        session.get('https://xueqiu.com/', headers=headers, timeout=30)
        
        # 访问用户页面
        logger.info(f"访问用户页面: {url}")
        response = session.get(url, headers=headers, timeout=30)
        
        logger.info(f"响应状态码: {response.status_code}")
        logger.info(f"响应内容长度: {len(response.text)} bytes")
        
        # 检查是否被反爬
        if response.status_code != 200:
            logger.error(f"请求失败，状态码: {response.status_code}")
            save_html(response.text, "debug.html")
            logger.info("已将响应 HTML 保存到 artifacts/debug.html")
            return []
        
        # 检查是否跳转到登录页
        if 'login' in response.url or 'passport' in response.url:
            logger.error("检测到重定向到登录页，需要登录才能访问")
            save_html(response.text, "debug.html")
            logger.info("已将响应 HTML 保存到 artifacts/debug.html")
            return []
        
        # 解析 HTML
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 尝试多种方式提取帖子数据
        posts = []
        
        # 方式1: 查找 article 标签（雪球文章结构）
        articles = soup.find_all('article', class_='timeline__item')
        logger.info(f"找到 {len(articles)} 个 timeline__item 文章")
        
        if articles:
            for article in articles:
                post = extract_post_from_article(article)
                if post:
                    posts.append(post)
        
        # 方式2: 如果没有找到，尝试其他选择器
        if not posts:
            # 尝试查找带有 data-id 的 div
            items = soup.find_all('div', attrs={'data-id': True})
            logger.info(f"尝试备选方案: 找到 {len(items)} 个带 data-id 的元素")
            
            for item in items:
                post = extract_post_from_div(item)
                if post:
                    posts.append(post)
        
        # 方式3: 尝试从 script 标签中提取 JSON 数据
        if not posts:
            logger.info("尝试从 script 标签提取数据...")
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'SNB.data' in script.string:
                    logger.info("找到包含 SNB.data 的 script 标签")
                    # 这里可以进一步解析 JSON 数据
                    break
        
        logger.info(f"成功解析到 {len(posts)} 条帖子")
        
        # 如果没有解析到任何帖子，保存 HTML 供分析
        if not posts:
            save_html(response.text, "debug.html")
            logger.info("未能解析到帖子，已将 HTML 保存到 artifacts/debug.html")
        
        return posts
        
    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求异常: {e}")
        return []
    except Exception as e:
        logger.error(f"解析异常: {e}")
        return []


def extract_post_from_article(article) -> dict:
    """从 article 标签提取帖子信息"""
    try:
        post = {}
        
        # 提取标题
        title_elem = article.find('a', class_='timeline__item__title')
        if title_elem:
            post['title'] = title_elem.get_text(strip=True)
            post['url'] = title_elem.get('href', '')
        
        # 提取内容
        content_elem = article.find('div', class_='timeline__item__content')
        if content_elem:
            post['content'] = content_elem.get_text(strip=True)
        
        # 提取时间
        time_elem = article.find('span', class_='timeline__item__time')
        if time_elem:
            post['time'] = time_elem.get_text(strip=True)
        
        # 提取文章ID
        article_id = article.get('data-id', '')
        if article_id:
            post['id'] = article_id
        
        return post if post.get('title') or post.get('content') else None
        
    except Exception as e:
        logger.warning(f"提取帖子信息失败: {e}")
        return None


def extract_post_from_div(div) -> dict:
    """从 div 标签提取帖子信息（备选方案）"""
    try:
        post = {}
        
        # 提取 ID
        post['id'] = div.get('data-id', '')
        
        # 尝试提取标题
        title_elem = div.find(['h1', 'h2', 'h3', 'a'], class_=lambda x: x and 'title' in str(x).lower())
        if title_elem:
            post['title'] = title_elem.get_text(strip=True)
        
        # 尝试提取内容
        content_elem = div.find(['div', 'p'], class_=lambda x: x and 'content' in str(x).lower())
        if content_elem:
            post['content'] = content_elem.get_text(strip=True)
        
        # 尝试提取时间
        time_elem = div.find(['span', 'time'], class_=lambda x: x and ('time' in str(x).lower() or 'date' in str(x).lower()))
        if time_elem:
            post['time'] = time_elem.get_text(strip=True)
        
        return post if post.get('title') or post.get('content') else None
        
    except Exception as e:
        logger.warning(f"从 div 提取帖子信息失败: {e}")
        return None
