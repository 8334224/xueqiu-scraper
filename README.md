# 雪球用户帖子抓取工具

自动抓取雪球网用户公开发帖，清洗过滤后生成本周精华汇总报告。

## 项目目标

- 抓取指定雪球用户的公开发帖
- 清洗数据并解析发布时间
- 过滤出最近7天的帖子
- 基于规则生成精华汇总（去重、分类、信息密度评分）
- 输出 Markdown 报告和 JSON 数据

## 安装依赖

```bash
# 进入项目目录
cd xueqiu-scraper

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器（首次运行需要）
playwright install chromium
```

## 如何运行

### 快速运行

```bash
python3 main.py
```

### 运行流程

1. **浏览器探针抓取** - 使用 Playwright 模拟真实浏览器访问
2. **HTTP 回退** - 浏览器失败时回退到 requests 请求
3. **数据清洗** - 解析时间格式，统一字段
4. **过滤** - 筛选最近7天的帖子
5. **生成汇总** - 去重、分类、提取精华观点

### 抓取指定用户

修改 `main.py` 中的 `user_id` 变量：

```python
user_id = "slowisquick"  # 改为目标用户ID
```

## 输出文件

运行后会在 `artifacts/` 目录生成以下文件：

| 文件 | 说明 |
|------|------|
| `raw_posts.json` | 原始抓取数据 |
| `clean_posts.json` | 清洗后的数据（最近7天） |
| `weekly_summary.md` | Markdown 格式精华报告 |
| `weekly_summary.json` | JSON 格式汇总数据 |
| `debug.html` | 调试用 HTML（抓取失败时） |
| `debug.png` | 调试用截图 |

## 项目结构

```
xueqiu-scraper/
├── main.py              # 主入口
├── fetcher.py           # HTTP 请求抓取
├── browser_fetcher.py   # 浏览器抓取（优先）
├── cleaner.py           # 数据清洗与时间解析
├── summarizer.py        # 规则汇总生成
├── utils.py             # 工具函数
├── requirements.txt     # 依赖列表
├── README.md            # 本文件
└── tests/               # 测试目录
    ├── test_cleaner.py
    └── test_summarizer.py
```

## 运行测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行单个测试文件
python3 -m pytest tests/test_cleaner.py -v
python3 -m pytest tests/test_summarizer.py -v
```

## 当前限制

1. **公开内容限制** - 只能抓取用户公开发布的内容，需要登录的私密内容无法获取
2. **反爬风险** - 频繁抓取可能触发雪球 WAF 或验证码
3. **时间解析** - 依赖页面显示的时间格式（"5分钟前"、"昨天"等），解析可能不完整
4. **单用户固定** - 当前版本 user_id 硬编码在 main.py 中
5. **无增量更新** - 每次运行全量抓取，不做本地缓存比对
6. **规则总结** - 基于关键词规则的总结，非 AI 生成，准确度有限

## 依赖环境

- Python 3.9+
- macOS / Linux / Windows
- Chrome/Chromium（Playwright 自动管理）

## License

MIT
