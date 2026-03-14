# -*- coding: utf-8 -*-
"""
llm_config.py - LLM 报告配置
"""
import os


LLM_PROVIDER = "openai_compatible"
LLM_DEFAULT_MODEL = "gpt-4o-mini"
LLM_API_KEY_ENV = "OPENAI_API_KEY"
LLM_BASE_URL_ENV = "OPENAI_BASE_URL"
LLM_DEFAULT_BASE_URL = "https://api.openai.com/v1"
LLM_MAX_INPUT_POSTS = 20
LLM_MAX_INPUT_CHARS = 16000
LLM_MAX_COMPLETION_TOKENS = 1800
LLM_REPORT_FILENAME = "investment_thinking_report.md"
LLM_REPORT_META_FILENAME = "llm_report_meta.json"
LLM_SOURCE_MATERIAL_FILENAME = "llm_source_material.txt"
LLM_PROMPT_TEMPLATE = "prompts/duan_yongping_report.md"


def get_api_key() -> str:
    """从环境变量读取 API Key"""
    return os.getenv(LLM_API_KEY_ENV, "").strip()


def get_base_url() -> str:
    """从环境变量读取 Base URL"""
    return os.getenv(LLM_BASE_URL_ENV, LLM_DEFAULT_BASE_URL).rstrip("/")
