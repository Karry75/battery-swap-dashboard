# -*- coding: utf-8 -*-
"""客户（OEM）维度：客户列表与名称映射"""
from core import db
import config.settings as settings

_t = settings.get("database.tables", {})
OEM_TABLE = _t.get("oem", "sys_oem")


def get_customers():
    """返回全部启用客户列表 [{id, code, name, status}]"""
    rows = db.query(
        f"SELECT id, code, name, status FROM {OEM_TABLE} WHERE is_del=0 AND status='on' ORDER BY id",
        database=settings.DB_BASE,
    )
    return rows


def get_customer_map():
    """oem_id -> 客户名称（含已停用，保证设备归属可解析）"""
    rows = db.query(
        f"SELECT id, name FROM {OEM_TABLE} WHERE is_del=0",
        database=settings.DB_BASE,
    )
    return {str(r["id"]): r["name"] for r in rows}
