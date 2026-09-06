"""
配置加载器（YAML + 环境变量合并）

加载顺序：
1. config/default.yaml（默认值）
2. config/{env}.yaml（环境覆盖）
3. 环境变量（仅密钥类）
4. Pydantic 校验
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from agent.config.schema import AppConfig


def load_config(
    env: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> AppConfig:
    """
    加载配置。

    Args:
        env: 环境标识 (dev/prod)，默认从环境变量 ENV 读取
        config_dir: 配置文件目录，默认为项目根目录下的 config/

    Returns:
        校验后的 AppConfig 实例
    """
    # 加载 .env
    load_dotenv()

    env = env or os.getenv("ENV", "dev")

    # 确定配置目录
    if config_dir is None:
        # 从当前文件向上找到项目根目录
        project_root = Path(__file__).parent.parent.parent.parent
        config_dir = str(project_root / "config")

    config_path = Path(config_dir)
    merged: dict = {}

    # 1. 加载 default.yaml
    default_file = config_path / "default.yaml"
    if default_file.exists():
        with open(default_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, data)

    # 2. 加载环境覆盖
    env_file = config_path / f"{env}.yaml"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, data)

    # 3. 设置环境标识
    merged["env"] = env

    # 4. Pydantic 校验
    return AppConfig(**merged)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
