# -*- coding: utf-8 -*-
"""
main.py - 雪球抓取入口
优先使用浏览器探针，失败则回退到 HTTP 方式
"""
import json
from fetcher import fetch_user_posts
from browser_fetcher import fetch_posts_with_browser
from utils import logger, save_to_json, get_artifacts_dir
from cleaner import clean_and_filter_posts
from summarizer import generate_weekly_summary


def main():
    """主入口函数"""
    user_id = "slowisquick"
    
    print("\n" + "=" * 60)
    print("雪球用户帖子抓取工具")
    print("=" * 60)
    print(f"目标用户: {user_id}")
    print("=" * 60)
    
    # Step 1: 尝试浏览器探针
    print("\n📌 Step 1: 尝试浏览器抓取探针...")
    posts, browser_success = fetch_posts_with_browser(user_id)
    
    if browser_success and posts:
        print("\n" + "=" * 60)
        print("✅ 抓取成功 - 使用浏览器探针")
        print("=" * 60)
        print(f"抓取帖子数量: {len(posts)}")
        print("\n前3条帖子:")
        print("-" * 60)
        
        for i, post in enumerate(posts[:3], 1):
            title = post.get('title', '无标题')
            content = post.get('content', '')
            # 如果标题为空，取内容前50字
            if not title and content:
                title = content[:50] + "..." if len(content) > 50 else content
            time_str = post.get('time', '未知时间')
            print(f"{i}. {title}")
            print(f"   时间: {time_str}")
            if post.get('url'):
                print(f"   链接: {post.get('url')}")
            print()
        
        print("=" * 60)
        logger.info("浏览器探针抓取完成")
        
        # 运行数据清洗和过滤
        print("\n📌 Step 2: 数据清洗与过滤...")
        try:
            clean_and_filter_posts()
            
            # 生成本周总结
            print("\n📌 Step 3: 生成本周精华汇总...")
            generate_weekly_summary()
        except Exception as e:
            logger.error(f"数据清洗失败: {e}")
        
        return
    
    # Step 2: 浏览器失败，回退到 HTTP
    print("\n📌 Step 3: 浏览器探针未成功，回退到 HTTP 请求...")
    posts = fetch_user_posts(user_id)
    
    if posts:
        # 保存原始数据
        output_path = save_to_json(posts, "raw_posts.json")
        
        print("\n" + "=" * 60)
        print("✅ 抓取成功 - 使用 HTTP 请求")
        print("=" * 60)
        print(f"抓取帖子数量: {len(posts)}")
        print(f"保存路径: {output_path}")
        print("\n前3条帖子标题:")
        print("-" * 60)
        
        for i, post in enumerate(posts[:3], 1):
            title = post.get('title', '无标题')
            content = post.get('content', '')
            if not title and content:
                title = content[:50] + "..." if len(content) > 50 else content
            print(f"{i}. {title}")
        
        print("=" * 60)
        logger.info("HTTP 方式抓取完成")
        
        # 运行数据清洗和过滤
        print("\n📌 Step 4: 数据清洗与过滤...")
        try:
            output_path, total, parsed, filtered, excluded = clean_and_filter_posts()
            
            # 显示 clean_posts 样本
            clean_posts_path = get_artifacts_dir() / "clean_posts.json"
            if clean_posts_path.exists():
                with open(clean_posts_path, 'r', encoding='utf-8') as f:
                    clean_posts = json.load(f)
                if clean_posts:
                    print("\n📋 clean_posts.json 前3条样本:")
                    print("-" * 60)
                    for i, post in enumerate(clean_posts[:3], 1):
                        title = post.get('title', '无标题')[:40]
                        pub_time = post.get('published_at', '未解析')
                        print(f"{i}. {title}...")
                        print(f"   发布时间: {pub_time}")
                        print()
                    print("-" * 60)
            
            # 生成本周总结
            print("\n📌 Step 5: 生成本周精华汇总...")
            generate_weekly_summary()
            
        except Exception as e:
            logger.error(f"数据清洗失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n" + "=" * 60)
        print("❌ 抓取结果: 失败 - 两种方式均未获取到帖子数据")
        print("=" * 60)
        print("可能原因:")
        print("  1. 需要登录才能访问")
        print("  2. 被 WAF 或验证码拦截")
        print("  3. 页面结构发生变化")
        print("  4. 网络连接问题")
        print("\n请检查 artifacts/debug.html 和 artifacts/debug.png 获取详情")
        print("=" * 60)
        logger.error("抓取失败 - 所有方式均失败")


if __name__ == "__main__":
    main()