import re

from browser_fetcher import (
    _extract_posts_from_embedded_data,
    _extract_posts_from_network_payloads,
)


class _FakePage:
    def __init__(self, evaluated_result):
        self._evaluated_result = evaluated_result

    def evaluate(self, _script):
        return self._evaluated_result


def test_extract_posts_from_embedded_data_prefers_window_data():
    page = _FakePage([
        {
            "label": "window.__INITIAL_STATE__",
            "data": {
                "statuses": [
                    {
                        "id": 123,
                        "title": "",
                        "description": "第一条帖子内容",
                        "created_at": 1773446924000,
                        "user": {"profile": "/slowisquick"},
                    }
                ]
            },
        }
    ])

    posts = _extract_posts_from_embedded_data(page, "<html></html>")

    assert len(posts) == 1
    assert posts[0]["id"] == "123"
    assert posts[0]["content"] == "第一条帖子内容"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", posts[0]["time"])
    assert posts[0]["url"] == "https://xueqiu.com/slowisquick/123"


def test_extract_posts_from_embedded_data_reads_json_script():
    page = _FakePage([])
    html = """
    <html>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"statuses":[{"id":456,"description":"<b>脚本里帖子</b>","created_at":"1773446924000"}]}}}
      </script>
    </html>
    """

    posts = _extract_posts_from_embedded_data(page, html)

    assert len(posts) == 1
    assert posts[0]["id"] == "456"
    assert posts[0]["content"] == "脚本里帖子"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", posts[0]["time"])


def test_extract_posts_from_network_payloads_uses_timeline_response():
    payloads = [
        {
            "url": "https://xueqiu.com/v4/statuses/user_timeline.json?page=1&user_id=1",
            "data": {
                "count": 1,
                "statuses": [
                    {
                        "id": 789,
                        "description": "接口返回内容",
                        "created_at": 1773446924000,
                        "user": {"domain": "slowisquick"},
                    }
                ],
            },
        }
    ]

    posts = _extract_posts_from_network_payloads(payloads)

    assert len(posts) == 1
    assert posts[0]["id"] == "789"
    assert posts[0]["content"] == "接口返回内容"
    assert posts[0]["url"] == "https://xueqiu.com/slowisquick/789"
