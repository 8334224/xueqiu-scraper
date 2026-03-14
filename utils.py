# -*- coding: utf-8 -*-
"""
utils.py - 辅助工具函数
"""
import os
import sys
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.absolute()


def get_artifacts_dir() -> Path:
    """获取 artifacts 目录路径"""
    artifacts_dir = get_project_root() / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    return artifacts_dir


def save_to_json(data, filename: str) -> Path:
    """将数据保存为 JSON 文件"""
    import json
    artifacts_dir = get_artifacts_dir()
    file_path = artifacts_dir / filename
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return file_path


def save_html(html_content: str, filename: str) -> Path:
    """保存 HTML 内容到文件（调试用）"""
    artifacts_dir = get_artifacts_dir()
    file_path = artifacts_dir / filename
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return file_path
