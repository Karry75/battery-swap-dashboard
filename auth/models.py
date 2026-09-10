# -*- coding: utf-8 -*-
"""内置用户体系（SQLite）：用户/角色/权限

- 与业务数据库完全隔离，凭据互不关联
- 密码使用 werkzeug 哈希存储，禁止明文
- 角色：admin 管理员 / manager 客户经理（限定 oem 范围）/ viewer 查看者（只读）
- 支持自定义角色：roles 表持久化，权限点为菜单模块级可见性
"""
import json
import os
import re
import sqlite3
import threading
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

import config.settings as settings

DB_PATH = Path(__file__).resolve().parent.parent / "board.db"
_lock = threading.Lock()

# 系统内置角色默认权限（首次初始化写入 roles 表，之后以库中为准）
SYSTEM_ROLES = {
    "admin": {
        "name": "管理员",
        "permissions": [
            "overview:view", "user:view", "sales:view", "site:view", "asset:view",
            "coupon:view", "dashboard:view", "staff:view", "finance:view",
            "service:view", "analysis:view", "alarm:handle", "admin:user",
        ],
    },
    "manager": {
        "name": "客户经理",
        "permissions": ["overview:view", "dashboard:view", "alarm:handle"],
    },
    "viewer": {
        "name": "查看者",
        "permissions": ["overview:view", "dashboard:view"],
    },
}

# 菜单模块级权限点白名单（前端勾选 + 后端校验共用）
PERMISSIONS = [
    {"key": "overview:view", "name": "数据总览"},
    {"key": "user:view", "name": "用户看板"},
    {"key": "sales:view", "name": "销售看板"},
    {"key": "site:view", "name": "网点看板"},
    {"key": "asset:view", "name": "设备资产看板"},
    {"key": "coupon:view", "name": "优惠券看板"},
    {"key": "dashboard:view", "name": "运维看板"},
    {"key": "staff:view", "name": "人员看板"},
    {"key": "finance:view", "name": "财务看板"},
    {"key": "service:view", "name": "客服服务台"},
    {"key": "analysis:view", "name": "深度分析"},
    {"key": "alarm:handle", "name": "告警处理"},
    {"key": "admin:user", "name": "用户/角色管理"},
]

PERMISSION_KEYS = [p["key"] for p in PERMISSIONS]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表 + 初始管理员 + 系统角色（仅当为空）"""
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    oem_ids TEXT DEFAULT '',
                    display_name TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    permissions TEXT DEFAULT '[]',
                    is_system INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )"""
            )
            conn.commit()
            # 初始化系统角色
            cnt = conn.execute("SELECT COUNT(*) c FROM roles").fetchone()["c"]
            if cnt == 0:
                for key, meta in SYSTEM_ROLES.items():
                    conn.execute(
                        "INSERT INTO roles(key, name, permissions, is_system) VALUES (?,?,?,1)",
                        (key, meta["name"], json.dumps(meta["permissions"], ensure_ascii=False)),
                    )
                conn.commit()
            cnt = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
            if cnt == 0:
                conn.execute(
                    "INSERT INTO users(username, password_hash, role, display_name) VALUES (?,?,?,?)",
                    (settings.ADMIN_USER,
                     generate_password_hash(settings.ADMIN_PASSWORD),
                     "admin",
                     "系统管理员"),
                )
                conn.commit()
        finally:
            conn.close()


# ---------- 角色 ----------
def get_roles():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, key, name, permissions, is_system, created_at FROM roles ORDER BY is_system DESC, id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["permissions"] = json.loads(d["permissions"] or "[]")
            except (ValueError, TypeError):
                d["permissions"] = []
            out.append(d)
        return out
    finally:
        conn.close()


def get_role_by_key(key):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM roles WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["permissions"] = json.loads(d["permissions"] or "[]")
        except (ValueError, TypeError):
            d["permissions"] = []
        return d
    finally:
        conn.close()


def get_role_by_id(role_id):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["permissions"] = json.loads(d["permissions"] or "[]")
        except (ValueError, TypeError):
            d["permissions"] = []
        return d
    finally:
        conn.close()


def role_permissions(role_key):
    """返回角色权限点列表；角色不存在时回退 viewer"""
    role = get_role_by_key(role_key)
    if role and role.get("permissions"):
        return role["permissions"]
    return SYSTEM_ROLES.get(role_key, SYSTEM_ROLES["viewer"])["permissions"]


def create_role(key, name, permissions):
    key = (key or "").strip()
    name = (name or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_]{2,32}", key):
        return False, "角色标识需为2-32位字母/数字/下划线"
    if not name:
        return False, "角色名称必填"
    perms = [p for p in (permissions or []) if p in PERMISSION_KEYS]
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO roles(key, name, permissions, is_system) VALUES (?,?,?,0)",
                (key, name, json.dumps(perms, ensure_ascii=False)),
            )
            conn.commit()
            return True, "ok"
        except sqlite3.IntegrityError:
            return False, "角色标识已存在"
        finally:
            conn.close()


def update_role(role_id, name=None, permissions=None):
    with _lock:
        conn = _conn()
        try:
            sets, params = [], []
            if name is not None:
                sets.append("name=?")
                params.append(name.strip())
            if permissions is not None:
                perms = [p for p in permissions if p in PERMISSION_KEYS]
                sets.append("permissions=?")
                params.append(json.dumps(perms, ensure_ascii=False))
            if not sets:
                return False, "没有可更新的字段"
            params.append(role_id)
            conn.execute(f"UPDATE roles SET {','.join(sets)} WHERE id=?", params)
            conn.commit()
            return True, "ok"
        finally:
            conn.close()


def delete_role(role_id):
    role = get_role_by_id(role_id)
    if not role:
        return False, "角色不存在"
    if role["is_system"]:
        return False, "系统内置角色不可删除"
    with _lock:
        conn = _conn()
        try:
            used = conn.execute("SELECT COUNT(*) c FROM users WHERE role=?", (role["key"],)).fetchone()["c"]
            if used:
                return False, f"仍有 {used} 个用户使用该角色，无法删除"
            conn.execute("DELETE FROM roles WHERE id=?", (role_id,))
            conn.commit()
            return True, "ok"
        finally:
            conn.close()


# ---------- 用户 ----------
def create_user(username, password, role="viewer", oem_ids=None, display_name=""):
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, oem_ids, display_name) VALUES (?,?,?,?,?)",
                (username, generate_password_hash(password), role,
                 ",".join(str(x) for x in (oem_ids or [])), display_name),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


def update_user(user_id, password=None, role=None, oem_ids=None, display_name=None):
    with _lock:
        conn = _conn()
        try:
            sets, params = [], []
            if password:
                sets.append("password_hash=?")
                params.append(generate_password_hash(password))
            if role:
                sets.append("role=?")
                params.append(role)
            if oem_ids is not None:
                sets.append("oem_ids=?")
                params.append(",".join(str(x) for x in oem_ids))
            if display_name is not None:
                sets.append("display_name=?")
                params.append(display_name)
            if not sets:
                return False
            params.append(user_id)
            conn.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", params)
            conn.commit()
            return True
        finally:
            conn.close()


def delete_user(user_id):
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def list_users():
    conn = _conn()
    try:
        rows = conn.execute("SELECT id, username, role, oem_ids, display_name, created_at FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user(user_id):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_by_username(username):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_login(username, password):
    user = find_by_username(username)
    if not user:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return user


def user_oem_ids(user):
    """用户的 oem 范围；admin 返回 None（全部）"""
    if user.get("role") == "admin":
        return None
    raw = user.get("oem_ids") or ""
    return [int(x) for x in raw.split(",") if x.strip().isdigit()] or None


def user_permissions(user):
    return role_permissions(user.get("role") or "viewer")
