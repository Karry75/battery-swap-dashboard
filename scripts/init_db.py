# -*- coding: utf-8 -*-
"""初始化脚本：初始化内置用户库并创建默认管理员

用法：python -m scripts.init_db
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import models as auth  # noqa: E402
import config.settings as settings  # noqa: E402

if __name__ == "__main__":
    auth.init_db()
    users = auth.list_users()
    print(f"内置用户库就绪: {auth.DB_PATH}")
    print(f"当前用户数: {len(users)}")
    print(f"默认管理员: {settings.ADMIN_USER}（密码来自 .env 的 ADMIN_PASSWORD，请登录后及时修改）")
