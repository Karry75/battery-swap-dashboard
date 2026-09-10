# -*- coding: utf-8 -*-
"""配置加载：.env 凭据 + config.yaml 业务配置"""
import os
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    """轻量解析 .env 文件（key=value，支持 # 注释），注入 os.environ（不覆盖已存在值）"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")

# ---- 数据库连接（仅内存使用，禁止写入日志/前端） ----
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "")
DB_BASE = os.environ.get("DB_BASE", "")

# ---- 看板服务 ----
BOARD_HOST = os.environ.get("BOARD_HOST", "0.0.0.0")
BOARD_PORT = int(os.environ.get("BOARD_PORT", "8092"))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

# ---- 初始管理员 ----
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change_me_before_deploy")

# ---- 业务配置 ----
_config_path = BASE_DIR / "config" / "config.yaml"
with open(_config_path, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f) or {}


def get(path: str, default=None):
    """按 'a.b.c' 路径读取业务配置"""
    node = CONFIG
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node
