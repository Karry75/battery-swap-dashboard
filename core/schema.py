# -*- coding: utf-8 -*-
"""逻辑表名 -> 物理表名 运行期映射

- 代码与配置中仅出现逻辑表名（如 t_exchange_order），不暴露真实库表结构
- 真实物理表名由本地 config/schema.local.yaml 注入（已列入 .gitignore）
- 未提供映射文件时 identity 直通，按逻辑表名执行，便于他人对接自己的库表
"""
import re

import config.settings as settings

_MAP = {k: v for k, v in (settings.SCHEMA_MAP or {}).items() if k and v and k != v}

if _MAP:
    _RX = re.compile(r"\b(" + "|".join(sorted((re.escape(k) for k in _MAP), key=len, reverse=True)) + r")\b")
else:
    _RX = None


def translate(sql: str) -> str:
    """将 SQL 中的逻辑表名替换为物理表名；无映射时原样返回"""
    if not _RX or not sql:
        return sql
    return _RX.sub(lambda m: _MAP[m.group(1)], sql)


def logical_names():
    """当前已配置的逻辑表名列表（用于自检/文档）"""
    return sorted(_MAP)
