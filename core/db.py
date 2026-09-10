# -*- coding: utf-8 -*-
"""多库兼容只读访问层

- 当前目标库为阿里云 AnalyticDB for MySQL（MySQL 协议），使用 pymysql
- 后续如需切换 PostgreSQL / SQL Server / SQLite，只需新增 driver 分支，接口不变
- 统一只读：所有查询必须走 query()，上层禁止执行写语句
"""
import logging
import time

import pymysql

import config.settings as settings
from core import cache

logger = logging.getLogger("board.db")

# 最近一次查询是否走了缓存回退（用于接口层附带降级标记）
FALLBACK = False
FALLBACK_TIME = None

# 熔断：连接失败后短时间内不再重复建连（避免断库时每次请求都等超时）
_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_TIMEOUT = 60  # 秒


def _connect(database: str = None):
    global _CIRCUIT_OPEN_UNTIL
    if time.time() < _CIRCUIT_OPEN_UNTIL:
        raise ConnectionError("数据库熔断中，跳过建连")
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=database or settings.DB_NAME,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
    )


def query(sql: str, params=None, database: str = None):
    """执行只读 SELECT，返回 dict 列表。禁止传入非 SELECT 语句。

    容灾：查询成功时将结果写入本地缓存；业务库不可达时回退到最近一次成功结果，
    并通过 FALLBACK / FALLBACK_TIME 标记本次降级。
    """
    global FALLBACK, FALLBACK_TIME, _CIRCUIT_OPEN_UNTIL
    sql = sql.strip().lstrip("(")
    if not sql.lower().startswith("select") and not sql.lower().startswith("with"):
        raise ValueError("只允许执行 SELECT 查询")
    ckey = cache.key_for(sql, params, database)
    try:
        conn = _connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
        finally:
            conn.close()
        cache.set(ckey, rows)
        FALLBACK = False
        FALLBACK_TIME = None
        _CIRCUIT_OPEN_UNTIL = 0.0
        return rows
    except Exception as e:  # noqa: BLE001
        _CIRCUIT_OPEN_UNTIL = time.time() + _CIRCUIT_TIMEOUT
        rows, created_at = cache.get(ckey)
        if rows is None:
            raise
        FALLBACK = True
        FALLBACK_TIME = created_at
        logger.warning("db.query 降级使用缓存 key=%s err=%s", ckey[:16], e)
        return rows


def query_one(sql: str, params=None, database: str = None):
    rows = query(sql, params, database)
    return rows[0] if rows else None


def table_names(database: str = None):
    """列出指定库所有表名（供映射校验/辅助）"""
    rows = query(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
        (database or settings.DB_NAME,),
        database="information_schema",
    )
    return [r["TABLE_NAME"] for r in rows]


def health():
    """连通性检查，返回 dict"""
    try:
        row = query_one("SELECT 1 AS ok")
        return {"ok": True, "detail": "database connected" if row else "empty"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}
