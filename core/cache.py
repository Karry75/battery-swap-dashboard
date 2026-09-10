# -*- coding: utf-8 -*-
"""本地查询结果缓存（SQLite）

用途：业务库断连时，将最近一次成功查询的结果回放，保证看板仍有数据可用。
- 所有写操作幂等 upsert，key 为查询指纹（sql+params+database）
- 限制最大条数，超出自动清理最旧记录
- 与业务库、用户库完全隔离，独立文件 board_cache.db
"""
import datetime
import decimal
import hashlib
import json
import re
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "board_cache.db"
MAX_ITEMS = 3000
_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _default(o):
    if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
        return o.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(o, decimal.Decimal):
        return float(o)
    return str(o)


def _init():
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )"""
            )
            conn.commit()
        finally:
            conn.close()


# 毫秒时间戳字面量：13 位数字、首位 1-4（约覆盖 2001-2126 年），
# 业务 SQL 中"今日/近N天"窗口均会拼入实时毫秒时间戳（如 create_time>{today_ms}），
# 直接以完整 SQL 做指纹会导致 key 每次变化、断库时缓存永远无法命中。
_TS_LITERAL_RE = re.compile(r"(?<!\d)[1-4]\d{12}(?!\d)")


def _normalize_key(raw: str) -> str:
    """将 SQL 文本/参数中的毫秒时间戳字面量替换为固定占位，使同一业务查询
    在不同时刻生成稳定缓存 key，从而在离线时可命中最后一次成功数据。"""
    return _TS_LITERAL_RE.sub("TS", raw)


def key_for(sql, params=None, database=None):
    raw = f"{database or ''}|{sql}|{repr(params or ())}"
    return hashlib.sha1(_normalize_key(raw).encode("utf-8")).hexdigest()


def set(key, data):
    _init()
    payload = json.dumps(data, ensure_ascii=False, default=_default)
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO cache(key, payload, created_at) VALUES (?,?,datetime('now','localtime')) "
                "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, created_at=excluded.created_at",
                (key, payload),
            )
            # 超限清理最旧
            conn.execute(
                "DELETE FROM cache WHERE key IN ("
                "SELECT key FROM cache ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
                (MAX_ITEMS,),
            )
            conn.commit()
        finally:
            conn.close()


def get(key):
    """返回 (data, created_at)；无缓存返回 (None, None)"""
    _init()
    conn = _conn()
    try:
        row = conn.execute("SELECT payload, created_at FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None, None
        return json.loads(row["payload"]), row["created_at"]
    finally:
        conn.close()
