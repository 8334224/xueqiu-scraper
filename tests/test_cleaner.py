# -*- coding: utf-8 -*-
"""
test_cleaner.py - cleaner 模块测试
测试时间解析功能
"""
import pytest
from datetime import datetime, timedelta
from cleaner import parse_xueqiu_time


class TestParseXueqiuTime:
    """测试雪球时间字符串解析"""
    
    def test_parse_just_now(self):
        """测试解析'刚刚'"""
        result = parse_xueqiu_time("刚刚")
        assert result is not None
        # 结果应该在当前时间附近（10秒内）
        now = datetime.now()
        assert abs((result - now).total_seconds()) < 10
    
    def test_parse_minutes_ago(self):
        """测试解析'X分钟前'"""
        result = parse_xueqiu_time("5分钟前")
        assert result is not None
        expected = datetime.now() - timedelta(minutes=5)
        # 允许1秒误差
        assert abs((result - expected).total_seconds()) < 1
    
    def test_parse_hours_ago(self):
        """测试解析'X小时前'"""
        result = parse_xueqiu_time("2小时前")
        assert result is not None
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 1
    
    def test_parse_yesterday(self):
        """测试解析'昨天 HH:MM'"""
        result = parse_xueqiu_time("昨天 09:30")
        assert result is not None
        yesterday = datetime.now() - timedelta(days=1)
        assert result.day == yesterday.day
        assert result.hour == 9
        assert result.minute == 30
    
    def test_parse_today(self):
        """测试解析'今天 HH:MM'"""
        result = parse_xueqiu_time("今天 14:30")
        assert result is not None
        assert result.day == datetime.now().day
        assert result.hour == 14
        assert result.minute == 30
    
    def test_parse_month_day_format(self):
        """测试解析'MM-DD HH:MM'格式"""
        result = parse_xueqiu_time("03-14 10:30")
        assert result is not None
        assert result.month == 3
        assert result.day == 14
        assert result.hour == 10
        assert result.minute == 30
    
    def test_parse_full_datetime(self):
        """测试解析'YYYY-MM-DD HH:MM'格式"""
        result = parse_xueqiu_time("2024-03-14 09:30")
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 14
        assert result.hour == 9
        assert result.minute == 30
    
    def test_parse_date_only(self):
        """测试解析'YYYY-MM-DD'格式"""
        result = parse_xueqiu_time("2024-03-14")
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 14
    
    def test_parse_none(self):
        """测试解析 None"""
        result = parse_xueqiu_time(None)
        assert result is None
    
    def test_parse_empty_string(self):
        """测试解析空字符串"""
        result = parse_xueqiu_time("")
        assert result is None
    
    def test_parse_whitespace(self):
        """测试解析空白字符串"""
        result = parse_xueqiu_time("   ")
        assert result is None
    
    def test_parse_invalid_format(self):
        """测试解析无效格式"""
        result = parse_xueqiu_time("不是时间格式")
        assert result is None
    
    def test_parse_invalid_date(self):
        """测试解析无效日期"""
        # 2月30日不存在
        result = parse_xueqiu_time("02-30 10:00")
        assert result is None


class TestParseEdgeCases:
    """测试边界情况"""
    
    def test_parse_large_minutes(self):
        """测试解析大分钟数"""
        result = parse_xueqiu_time("1440分钟前")  # 24小时
        assert result is not None
        expected = datetime.now() - timedelta(minutes=1440)
        assert abs((result - expected).total_seconds()) < 1
    
    def test_parse_large_hours(self):
        """测试解析大小时数"""
        result = parse_xueqiu_time("168小时前")  # 7天
        assert result is not None
        expected = datetime.now() - timedelta(hours=168)
        assert abs((result - expected).total_seconds()) < 1
    
    def test_parse_with_spaces(self):
        """测试带空格的时间字符串"""
        result = parse_xueqiu_time("  5分钟前  ")
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
