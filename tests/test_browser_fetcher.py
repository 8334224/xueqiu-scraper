from typing import Optional

from browser_fetcher import extract_post_data


class _FakeTitleElement:
    def __init__(self, text: Optional[str] = None, href: Optional[str] = None, error: Optional[Exception] = None):
        self._text = text
        self._href = href
        self._error = error

    def inner_text(self):
        if self._error:
            raise self._error
        return self._text

    def get_attribute(self, name):
        if name == "href":
            return self._href
        return None


class _FakePostElement:
    def get_attribute(self, name):
        raise AttributeError(name)

    def query_selector(self, selector):
        if selector == ".timeline__item__title":
            return _FakeTitleElement(error=TypeError("transient title failure"))
        if selector == ".article__title":
            return _FakeTitleElement(text="Test title", href="/p/1")
        return None

    def inner_text(self):
        return "正文内容"


def test_extract_post_data_handles_supported_selector_errors():
    post = extract_post_data(_FakePostElement())

    assert post is not None
    assert post["title"] == "Test title"
    assert post["url"] == "https://xueqiu.com/p/1"
