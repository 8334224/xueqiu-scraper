# 雪球用户帖子抓取工具

自动抓取雪球网用户公开发帖，清洗过滤后生成本周精华汇总报告。

## 项目目标

- 抓取指定雪球用户的公开发帖
- 清洗数据并解析发布时间
- 过滤出最近 N 天的帖子（默认 7 天）
- 基于规则生成精华汇总（去重、分类、信息密度评分）
- 输出 Markdown 报告、JSON 数据和清洗统计

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
python3 main.py slowisquick
python3 main.py --user-id slowisquick
python3 main.py --days 14
python3 main.py --source browser
python3 main.py --source http
python3 main.py --artifacts-dir ./artifacts_dev
python3 main.py --llm-report
OPENAI_API_KEY=your_key python3 main.py --llm-report --llm-model gpt-4o-mini
```

### 运行流程

1. **Browser 数据层优先抓取** - 优先从页面数据/接口响应提取，DOM 仅作兜底
2. **HTTP 回退** - 仅在 `--source auto` 且 browser 失败时回退到 requests 请求
3. **数据清洗** - 解析时间格式，统一字段
4. **按窗口过滤** - 默认筛选最近 7 天，可通过 `--days` 调整
5. **生成规则摘要** - 去重、分类、提取精华观点
6. **可选 LLM 深度报告** - 开启 `--llm-report` 后，基于 `clean_posts.json` 额外生成一份深度分析报告

### 抓取指定用户

通过位置参数或 `--user-id` 传入目标用户 ID：

```bash
python3 main.py <user_id>
python3 main.py --user-id <user_id>
```

### CLI 参数

```bash
python3 main.py [user_id] [--user-id USER_ID] [--days DAYS] [--source {auto,browser,http}] [--artifacts-dir DIR] [--llm-report] [--llm-model MODEL]
```

- `--user-id`：覆盖目标雪球用户，默认 `slowisquick`
- `--days`：清洗最近多少天的数据，默认 `7`
- `--source`：
  - `auto`：先 browser，再 HTTP
  - `browser`：只跑 browser
  - `http`：只跑 HTTP
- `--artifacts-dir`：自定义输出目录，默认项目内 `artifacts/`
- `--llm-report`：在规则摘要后额外生成 LLM 深度报告，默认关闭
- `--llm-model`：覆盖 LLM 模型名，默认使用代码内配置值

### 发言价值判断

- 清洗完成后，项目会新增一层“投资学习价值”判断
- 产出文件：`valued_posts.json`
- 每条帖子会补充：
  - `value_level`：`low` / `medium` / `high`
  - `value_score`：`0 ~ 100`
  - `value_reasons`：结构化打分理由
- 这层判断聚焦“是否有助于学习段永平的投资思维”，不是情绪分析
- 短内容不会天然低价值；如果短句体现了投资原则、判断标准或风险意识，仍可能是中高价值
- 规则摘要和 LLM 深度报告会优先消费高/中价值内容

### LLM 深度报告

- 默认不开启，不影响现有规则摘要链路
- 开启方式：`--llm-report`
- 当前实现使用 OpenAI-compatible Chat Completions 接口
- 需要环境变量：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`（可选，不填则默认 `https://api.openai.com/v1`）
- 启用后除了 `investment_thinking_report.md`，还会生成：
  - `llm_report_meta.json`
  - `llm_source_material.txt`
- 如果缺少 `OPENAI_API_KEY`，LLM 阶段会优雅降级：主流程继续完成，规则摘要和运行摘要仍会正常输出
- 这两个文件用于排查 LLM 阶段的输入与输出，不属于仓库静态源码文件
- 相关文件：
  - `llm_reporter.py`：LLM 报告模块
  - `llm_config.py`：LLM 配置
  - `prompts/duan_yongping_report.md`：提示词模板

## 输出文件

运行后会在 `artifacts/` 或你指定的 `--artifacts-dir` 目录生成以下文件：

| 文件 | 说明 |
|------|------|
| `raw_posts.json` | 原始抓取数据 |
| `clean_posts.json` | 清洗后的数据（窗口内保留） |
| `valued_posts.json` | 增加价值分级后的帖子数据，包含 `value_level` / `value_score` / `value_reasons` |
| `excluded_posts.json` | 被过滤掉的帖子及原因 |
| `cleaning_summary.json` | 清洗统计摘要与排除原因计数 |
| `final_report.md` | 本次运行的统一入口页，建议优先查看 |
| `weekly_summary.md` | Markdown 格式精华报告 |
| `weekly_summary.json` | JSON 格式汇总数据 |
| `investment_thinking_report.md` | 可选的 LLM 深度报告（开启 `--llm-report` 时生成） |
| `llm_report_meta.json` | LLM 阶段元数据与错误信息 |
| `llm_source_material.txt` | 发给模型前的整理材料，便于复盘 |
| `run_summary.json` | 程序化运行摘要，记录来源、数量、主结果文件等元数据 |
| `debug.html` | 调试用 HTML（抓取失败时） |
| `debug.png` | 调试用截图 |

## 如何查看输出结果

- 默认先看 `final_report.md`，它会告诉你这次运行最值得先看的结果文件
- 想快速浏览重点内容，看 `weekly_summary.md`
- 想看深入版分析，看 `investment_thinking_report.md`（仅在开启 `--llm-report` 且生成成功时存在）
- `run_summary.json` 和 `llm_report_meta.json` 更适合排查问题或程序化读取

## 项目结构

```
xueqiu-scraper/
├── main.py              # 主入口
├── fetcher.py           # HTTP 请求抓取
├── browser_fetcher.py   # 浏览器抓取（数据层优先）
├── cleaner.py           # 数据清洗、时间解析、过滤原因输出
├── llm_config.py        # LLM 配置
├── llm_reporter.py      # 可选 LLM 深度报告生成
├── final_reporter.py    # 最终总览页生成
├── prompts/             # LLM 提示词模板
├── summarizer.py        # 规则汇总生成
├── summary_config.py    # 总结规则配置
├── utils.py             # 工具函数
├── requirements.txt     # 依赖列表
├── README.md            # 本文件
└── tests/               # 测试目录
    ├── test_final_reporter.py
    ├── test_cleaner.py
    ├── test_main.py
    ├── test_llm_reporter.py
    └── test_summarizer.py
```

## 运行测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行单个测试文件
python3 -m pytest tests/test_cleaner.py -v
python3 -m pytest tests/test_main.py -v
python3 -m pytest tests/test_llm_reporter.py -v
python3 -m pytest tests/test_final_reporter.py -v
python3 -m pytest tests/test_summarizer.py -v
```

## 当前限制

1. **公开内容限制** - 只能抓取用户公开发布的内容，需要登录的私密内容无法获取
2. **反爬风险** - 频繁抓取可能触发雪球 WAF 或验证码
3. **时间解析** - 依赖页面显示的时间格式（"5分钟前"、"昨天"等），解析可能不完整
4. **单次单用户** - 每次运行只处理一个 user_id，如需切换目标用户需重新执行命令并传入新的参数
5. **无增量更新** - 每次运行全量抓取，不做本地缓存比对
6. **规则总结** - 基于关键词规则的总结，非 AI 生成，准确度有限

## 依赖环境

- Python 3.9+
- macOS / Linux / Windows
- Chrome/Chromium（Playwright 自动管理）

## License

MIT
