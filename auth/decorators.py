# -*- coding: utf-8 -*-
"""登录态与权限校验"""
from functools import wraps
from flask import session, g, jsonify

from auth import models as auth


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            return jsonify({"code": 401, "msg": "未登录或会话已过期"}), 401
        user = auth.get_user(uid)
        if not user:
            session.clear()
            return jsonify({"code": 401, "msg": "用户不存在"}), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def permission_required(perm):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = g.get("user")
            if not user:
                return jsonify({"code": 401, "msg": "未登录"}), 401
            if perm not in auth.user_permissions(user):
                return jsonify({"code": 403, "msg": "无权限执行该操作"}), 403
            return f(*args, **kwargs)
        return wrapper
    return deco


def current_oem_ids():
    """当前用户可查看的 oem 范围；admin 返回 None（全部）"""
    user = g.get("user")
    if not user:
        return None
    return auth.user_oem_ids(user)
