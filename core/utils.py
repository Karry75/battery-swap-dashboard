# -*- coding: utf-8 -*-
"""通用工具：时间戳转换等"""
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def ts_to_str(ts):
    """毫秒时间戳 -> 'YYYY-MM-DD HH:mm:ss'（东八区）；非法返回原值"""
    if ts in (None, "", 0):
        return ""
    try:
        ts = int(ts)
        return datetime.fromtimestamp(ts / 1000, CST).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return str(ts)


def safe_float(v, default=None):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return default
