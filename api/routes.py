# -*- coding: utf-8 -*-
"""看板 REST API"""
from flask import Blueprint, request, jsonify, session

from auth import models as auth
from auth.decorators import login_required, permission_required, current_oem_ids
from core import db
from core import metrics
from core import devices
from core import overview
from core import business
from core import finance_assets
from core import dimensions
from core.battery_alarms import battery_alarms
from core.cabinet_alarms import exchange_alarms
from core import bigscreen

bp = Blueprint("api", __name__, url_prefix="/api")


def ok(data=None, msg="ok"):
    payload = {"code": 0, "msg": msg, "data": data}
    if db.FALLBACK:
        payload["cached"] = True
        payload["cached_at"] = db.FALLBACK_TIME or ""
    return jsonify(payload)


def err(msg, code=500, http=200):
    return jsonify({"code": code, "msg": msg}), http


# ---------- 筛选维度选项 ----------
@bp.get("/filters/options")
@login_required
def filter_options():
    """统一筛选器可用的维度选项（城市/区域/街道/社区/代理商/电池产品/品牌/事业线/网点/业务员/商户）"""
    try:
        return ok(dimensions.options(current_oem_ids(), city=(request.args.get("city") or "")))
    except Exception as e:  # noqa: BLE001
        return err(f"维度选项加载失败: {type(e).__name__}: {e}", 500, 502)


# ---------- 认证 ----------
@bp.post("/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = auth.verify_login(username, password)
    if not user:
        return err("用户名或密码错误", 401, 401)
    session.clear()
    session["uid"] = user["id"]
    return ok({"id": user["id"], "username": user["username"],
               "role": user["role"], "display_name": user["display_name"],
               "oem_ids": user["oem_ids"]})


@bp.post("/auth/logout")
def logout():
    session.clear()
    return ok()


@bp.get("/auth/me")
@login_required
def me():
    u = g_current()
    return ok(u)


def g_current():
    from flask import g
    user = g.user
    role = auth.get_role_by_key(user["role"] or "viewer")
    return {"id": user["id"], "username": user["username"], "role": user["role"],
            "role_name": (role or {}).get("name", user["role"]),
            "display_name": user["display_name"], "oem_ids": user["oem_ids"],
            "permissions": auth.user_permissions(user)}


# ---------- 看板 ----------
@bp.get("/health")
def health():
    h = db.health()
    if not h["ok"]:
        return err("业务数据库连接异常：" + h["detail"], 500, 503)
    return ok(h)


@bp.get("/dashboard/summary")
@login_required
@permission_required("dashboard:view")
def dashboard_summary():
    try:
        return ok(metrics.summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/dashboard/customer-stats")
@login_required
@permission_required("dashboard:view")
def dashboard_customer_stats():
    try:
        return ok(metrics.customer_stats(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/dashboard/alarm-stats")
@login_required
@permission_required("dashboard:view")
def dashboard_alarm_stats():
    device_type = request.args.get("device_type", "all")
    try:
        if device_type == "battery":
            data = metrics.alarm_summary(current_oem_ids(), args=request.args)["battery"]
        elif device_type == "exchange":
            data = metrics.alarm_summary(current_oem_ids(), args=request.args)["exchange"]
        elif device_type == "board":
            data = metrics.alarm_summary(current_oem_ids(), args=request.args)["board"]
        else:
            data = metrics.alarm_summary(current_oem_ids(), args=request.args)
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)
    return ok(data)


@bp.get("/dashboard/emergency-center")
@login_required
@permission_required("dashboard:view")
def dashboard_emergency_center():
    """紧急告警中心：电池规模/柜内外分布/紧急告警电池/紧急告警事项 + 检测板六类告警

    继承统一多维筛选（客户 oem_id、电池产品 battery_product_id、城市/区域/代理商/网点）。
    """
    try:
        return ok(metrics.emergency_center(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"紧急告警中心统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/alarms")
@login_required
@permission_required("dashboard:view")
def alarms_list():
    """告警明细，支持 device_type / alarm_type / page / page_size 及统一筛选(device_sn/city/area/agency/site)"""
    device_type = request.args.get("device_type", "all")
    alarm_type = request.args.get("alarm_type", "")
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(200, max(1, int(request.args.get("page_size", 50))))
    oem_ids = current_oem_ids()
    # 客户筛选（oem_id）与权限范围合并
    oem_ids = metrics._eff_oem(oem_ids, request.args)
    try:
        if device_type == "battery":
            items = battery_alarms(oem_ids)
        elif device_type == "exchange":
            items = exchange_alarms(oem_ids)
        else:
            items = battery_alarms(oem_ids) + exchange_alarms(oem_ids)
        if oem_ids:
            _ids = set(int(i) for i in oem_ids)
            items = [a for a in items if int(a.get("customer_id") or 0) in _ids]
        if alarm_type:
            items = [a for a in items if a["alarm_type"] == alarm_type]
        # ---- 统一筛选：告警为实时检测计算结果，在后端结果集过滤（非前端假过滤）----
        # 支持 device_sn / city(匹配地址/网点名) / area(匹配地址) / start / end(告警时间范围)
        _kw = lambda key: (request.args.get(key) or "").strip()
        _sn = _kw("device_sn")
        if _sn:
            _snl = _sn.lower().lstrip("sn").strip()
            items = [a for a in items if _snl in str(a.get("device_sn") or "").lower()]
        _city = _kw("city")
        if _city:
            items = [a for a in items if _city in (a.get("extra") or {}).get("address", "")
                     or _city in (a.get("extra") or {}).get("site_name", "")
                     or _city in (a.get("extra") or {}).get("agency_name", "")]
        _area = _kw("area")
        if _area:
            items = [a for a in items if _area in (a.get("extra") or {}).get("address", "")]
        _start, _end = _kw("start"), _kw("end")
        if _start or _end:
            def _norm(v, is_end):
                v = v.replace("T", " ")
                if len(v) <= 10:
                    v = v + (" 23:59:59" if is_end else " 00:00:00")
                elif len(v) == 16:
                    v += ":00"
                return v
            _st = _norm(_start, False) if _start else ""
            _en = _norm(_end, True) if _end else ""
            def _keep(a):
                t = str(a.get("time") or "")
                if _st and t < _st:
                    return False
                if _en and t > _en:
                    return False
                return True
            items = [a for a in items if _keep(a)]
        total = len(items)
        start = (page - 1) * page_size
        return ok({"total": total, "page": page, "page_size": page_size,
                   "items": items[start:start + page_size]})
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# ---------- 设备列表（换电柜管理 / 电池管理） ----------
@bp.get("/devices/exchanges")
@login_required
@permission_required("dashboard:view")
def devices_exchanges():
    page, page_size = devices._page_args(request.args)
    try:
        return ok(devices.exchange_list(
            oem_ids=current_oem_ids(),
            status=request.args.get("status", ""),
            keyword=(request.args.get("keyword") or "").strip(),
            page=page, page_size=page_size, args=request.args,
        ))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/devices/batteries")
@login_required
@permission_required("dashboard:view")
def devices_batteries():
    page, page_size = devices._page_args(request.args)
    try:
        return ok(devices.battery_list(
            oem_ids=current_oem_ids(),
            status=request.args.get("status", ""),
            keyword=(request.args.get("keyword") or "").strip(),
            power_min=request.args.get("power_min", ""),
            power_max=request.args.get("power_max", ""),
            page=page, page_size=page_size, args=request.args,
        ))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/devices/export")
@login_required
@permission_required("dashboard:view")
def devices_export():
    """通用 CSV 导出（当前筛选条件全量）"""
    import csv
    import io
    from flask import Response
    export_type = request.args.get("type", "battery")
    oem_ids = current_oem_ids()
    try:
        if export_type == "exchange":
            data = devices.exchange_list(
                oem_ids=oem_ids,
                status=request.args.get("status", ""),
                keyword=(request.args.get("keyword") or "").strip(),
                page=1, page_size=5000, args=request.args,
            )
            headers = ["柜号", "设备名称", "客户", "在线状态", "总仓位", "满仓", "充电中", "空仓",
                       "烟感", "水浸", "火警", "摆放位置", "所在地址", "最后上报时间"]
            rows = []
            for it in data["items"]:
                rows.append([
                    it.get("device_sn", ""), it.get("device_name", ""), it.get("customer_name", ""),
                    it.get("online_status", ""), it.get("slot_total", 0), it.get("slot_full", 0),
                    it.get("slot_charging", 0), it.get("slot_empty", 0),
                    it.get("smoke", ""), it.get("flooded", ""), it.get("fire", ""),
                    it.get("site_placement", ""), it.get("last_location_address", ""),
                    _fmt_ts(it.get("last_upload_time")),
                ])
        elif export_type == "alarm":
            device_type = request.args.get("device_type", "all")
            alarm_type = request.args.get("alarm_type", "")
            if device_type == "battery":
                items = battery_alarms(oem_ids)
            elif device_type == "exchange":
                items = exchange_alarms(oem_ids)
            else:
                items = battery_alarms(oem_ids) + exchange_alarms(oem_ids)
            if alarm_type:
                items = [a for a in items if a["alarm_type"] == alarm_type]
            headers = ["设备类型", "告警类型", "告警等级", "设备SN", "客户", "位置", "发生时间"]
            rows = [[
                "电池" if it.get("device_type") == "battery" else "换电柜",
                it.get("alarm_name", ""), it.get("priority", ""),
                it.get("device_sn", ""), it.get("customer_name", ""),
                it.get("location", ""), it.get("alarm_time", ""),
            ] for it in items]
        else:  # battery
            data = devices.battery_list(
                oem_ids=oem_ids,
                status=request.args.get("status", ""),
                keyword=(request.args.get("keyword") or "").strip(),
                power_min=request.args.get("power_min", ""),
                power_max=request.args.get("power_max", ""),
                page=1, page_size=5000, args=request.args,
            )
            headers = ["电池SN", "客户", "电池状态", "在线状态", "类型", "电量%", "电压V", "充电状态",
                       "所在换电柜", "供应商", "位置", "最后上报时间"]
            rows = []
            for it in data["items"]:
                rows.append([
                    it.get("device_sn", ""), it.get("customer_name", ""),
                    it.get("battery_status", ""), it.get("online_status", ""), it.get("type", ""),
                    it.get("power", ""), it.get("voltage", ""), it.get("charging", ""),
                    it.get("last_upload_exchange_sn", ""), it.get("supplier_name", ""),
                    it.get("last_location_address", ""),
                    _fmt_ts(it.get("last_battery_upload_time")),
                ])
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        out = "\ufeff" + buf.getvalue()
        return Response(out, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={export_type}_{_now_str()}.csv"})
    except Exception as e:  # noqa: BLE001
        return err(f"导出失败: {type(e).__name__}: {e}", 500, 502)


def _fmt_ts(ts):
    """毫秒时间戳 -> 字符串"""
    import datetime
    if not ts or int(ts or 0) <= 0:
        return ""
    return datetime.datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _now_str():
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


# ---------- 平台板块（数据总览 / 用户 / 销售 / 网点 / 客服 / 财务 / 资产 / 优惠券 / 人员 / 深度分析） ----------
def _bp(days):
    try:
        return max(1, int(days))
    except (TypeError, ValueError):
        return 30


@bp.get("/overview/summary")
@login_required
@permission_required("overview:view")
def overview_summary():
    try:
        return ok(overview.summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/overview/monthly-trend")
@login_required
@permission_required("overview:view")
def overview_monthly():
    try:
        return ok(overview.monthly_trend(current_oem_ids(), months=_bp(request.args.get("months", 12)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/overview/city-dimension")
@login_required
@permission_required("overview:view")
def overview_city():
    try:
        return ok(overview.city_dimension(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/overview/regions")
@login_required
@permission_required("overview:view")
def overview_regions():
    try:
        return ok(overview.regions(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/overview/device-dimension")
@login_required
@permission_required("overview:view")
def overview_device():
    try:
        return ok(overview.device_dimension(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/overview/finance-dimension")
@login_required
@permission_required("overview:view")
def overview_finance():
    try:
        return ok(overview.finance_dimension(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


# 用户看板
@bp.get("/users/summary")
@login_required
@permission_required("user:view")
def users_summary():
    try:
        return ok(business.users_summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/list")
@login_required
@permission_required("user:view")
def users_list():
    page, size = _pg(request.args)
    try:
        return ok(business.users_list(current_oem_ids(), keyword=request.args.get("keyword", ""),
                                      city=request.args.get("city", ""), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/agreements")
@login_required
@permission_required("user:view")
def users_agreements():
    page, size = _pg(request.args)
    try:
        return ok(business.user_agreements(current_oem_ids(), user_phone=request.args.get("user_phone", ""),
                                           status=request.args.get("status", ""), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/rents")
@login_required
@permission_required("user:view")
def users_rents():
    page, size = _pg(request.args)
    try:
        return ok(business.user_rents(current_oem_ids(), user_phone=request.args.get("user_phone", ""),
                                      card_status=request.args.get("card_status", ""), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/orders")
@login_required
@permission_required("user:view")
def users_orders():
    page, size = _pg(request.args)
    try:
        return ok(business.user_orders(current_oem_ids(), user_phone=request.args.get("user_phone", ""),
                                       page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/lifecycle")
@login_required
@permission_required("user:view")
def users_lifecycle():
    """协议生命周期统计：生效中/欠费/已终止/待生效/已过期"""
    try:
        return ok(business.users_lifecycle(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/tier")
@login_required
@permission_required("user:view")
def users_tier():
    """近 N 天用户分层（按换电次数 / 消费金额）"""
    try:
        return ok(business.users_tier(current_oem_ids(), days=_bp(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/growth")
@login_required
@permission_required("user:view")
def users_growth():
    """近 N 月新增用户趋势 + 注册来源分布"""
    try:
        return ok(business.users_growth(current_oem_ids(), months=_bp(request.args.get("months", 6)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/detail")
@login_required
@permission_required("user:view")
def users_detail():
    """单用户详情（手机号）：基本信息 + 协议 + 租期卡 + 订单汇总"""
    try:
        return ok(business.users_detail(current_oem_ids(), phone=request.args.get("phone", "")))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/users/city-detail")
@login_required
@permission_required("user:view")
def users_city_detail():
    """城市分布明细：用户数/活跃用户/协议数/近30天换电次数"""
    try:
        return ok(business.users_city_detail(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


# 销售看板
@bp.get("/sales/summary")
@login_required
@permission_required("sales:view")
def sales_summary():
    try:
        return ok(business.sales_summary(current_oem_ids(), days=_bp(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/sales/site-rank")
@login_required
@permission_required("sales:view")
def sales_site_rank():
    try:
        return ok(business.sales_site_rank(current_oem_ids(), days=_bp(request.args.get("days", 30)),
                                           limit=_bp(request.args.get("limit", 20)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/sales/staff-rank")
@login_required
@permission_required("sales:view")
def sales_staff_rank():
    try:
        return ok(business.sales_staff_rank(current_oem_ids(), days=_bp(request.args.get("days", 30)),
                                            limit=_bp(request.args.get("limit", 20)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/sales/service-orders")
@login_required
@permission_required("sales:view")
def sales_service_orders():
    page, size = _pg(request.args)
    try:
        return ok(business.sales_service_orders(current_oem_ids(),
                                                order_status=request.args.get("order_status", ""),
                                                page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 网点看板
@bp.get("/sites/summary")
@login_required
@permission_required("site:view")
def sites_summary():
    try:
        return ok(business.sites_summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/sites/list")
@login_required
@permission_required("site:view")
def sites_list():
    page, size = _pg(request.args)
    try:
        return ok(business.sites_list(current_oem_ids(), keyword=request.args.get("keyword", ""),
                                      type_=request.args.get("type", ""),
                                      status=request.args.get("status", ""), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/sites/orders")
@login_required
@permission_required("site:view")
def sites_orders():
    page, size = _pg(request.args)
    try:
        return ok(business.site_orders(current_oem_ids(), site_id=request.args.get("site_id", ""),
                                       page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 客服服务台
@bp.get("/service/query")
@login_required
@permission_required("service:view")
def service_query():
    page, size = _pg(request.args)
    try:
        return ok(business.service_query(current_oem_ids(), keyword=request.args.get("keyword", ""),
                                         city=request.args.get("city", ""),
                                         status=request.args.get("status", ""), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/service/complaints")
@login_required
@permission_required("service:view")
def service_complaints():
    page, size = _pg(request.args)
    try:
        return ok(business.service_complaints(current_oem_ids(), page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 财务看板
@bp.get("/finance/summary")
@login_required
@permission_required("finance:view")
def finance_summary():
    try:
        return ok(finance_assets.finance_summary(current_oem_ids(), days=_bp(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/finance/income-trend")
@login_required
@permission_required("finance:view")
def finance_income_trend():
    try:
        return ok(finance_assets.finance_income_trend(current_oem_ids(), months=_bp(request.args.get("months", 12)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/finance/expense-list")
@login_required
@permission_required("finance:view")
def finance_expense_list():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.finance_expense_list(current_oem_ids(),
                                                      fee_type=request.args.get("fee_type", ""),
                                                      keyword=request.args.get("keyword", ""),
                                                      page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/finance/expense-types")
@login_required
@permission_required("finance:view")
def finance_expense_types():
    try:
        return ok(finance_assets.finance_expense_types(current_oem_ids(), days=_bp(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/finance/deposit-list")
@login_required
@permission_required("finance:view")
def finance_deposit_list():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.finance_deposit_list(current_oem_ids(),
                                                      deposit_status=request.args.get("deposit_status", ""),
                                                      page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 设备资产看板
@bp.get("/assets/summary")
@login_required
@permission_required("asset:view")
def assets_summary():
    try:
        return ok(finance_assets.assets_summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/assets/battery-status")
@login_required
@permission_required("asset:view")
def assets_battery_status():
    try:
        return ok(finance_assets.assets_battery_status(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/assets/transfer-logs")
@login_required
@permission_required("asset:view")
def assets_transfer_logs():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.assets_transfer_logs(current_oem_ids(),
                                                      transfer_type=request.args.get("transfer_type", ""),
                                                      keyword=(request.args.get("keyword") or "").strip(),
                                                      page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/assets/work-orders")
@login_required
@permission_required("asset:view")
def assets_work_orders():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.assets_work_orders(current_oem_ids(),
                                                    status=request.args.get("status", ""),
                                                    page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 优惠券看板
@bp.get("/coupons/summary")
@login_required
@permission_required("coupon:view")
def coupons_summary():
    try:
        return ok(finance_assets.coupons_summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/coupons/list")
@login_required
@permission_required("coupon:view")
def coupons_list():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.coupons_list(current_oem_ids(), status=request.args.get("status", ""),
                                              keyword=request.args.get("keyword", ""),
                                              page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 人员看板
@bp.get("/staff/summary")
@login_required
@permission_required("staff:view")
def staff_summary():
    try:
        return ok(finance_assets.staff_summary(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/staff/work-orders")
@login_required
@permission_required("staff:view")
def staff_work_orders():
    page, size = _pg(request.args)
    try:
        return ok(finance_assets.staff_work_orders(current_oem_ids(),
                                                   solve_user=request.args.get("solve_user", ""),
                                                   page=page, page_size=size, args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"查询失败: {type(e).__name__}: {e}", 500, 502)


# 深度分析
@bp.get("/insights/exchange-peak")
@login_required
@permission_required("analysis:view")
def insights_exchange_peak():
    try:
        return ok(finance_assets.insights_exchange_peak(current_oem_ids(), days=_bp(request.args.get("days", 7)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/insights/first-take")
@login_required
@permission_required("analysis:view")
def insights_first_take():
    try:
        return ok(finance_assets.insights_first_take(current_oem_ids(), days=_bp(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/insights/battery-age")
@login_required
@permission_required("analysis:view")
def insights_battery_age():
    try:
        return ok(finance_assets.insights_battery_age(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/insights/expense-compare")
@login_required
@permission_required("analysis:view")
def insights_expense_compare():
    try:
        return ok(finance_assets.insights_expense_compare(current_oem_ids(),
                                                          months=_bp(request.args.get("months", 6)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


def _pg(args):
    page = max(1, int(args.get("page", 1)))
    size = min(200, max(1, int(args.get("page_size", 50))))
    return page, size


# ---------- 管理 ----------
@bp.get("/admin/permissions")
@login_required
@permission_required("admin:user")
def admin_permissions():
    return ok(auth.PERMISSIONS)


@bp.get("/admin/roles")
@login_required
@permission_required("admin:user")
def admin_roles():
    return ok(auth.get_roles())


@bp.post("/admin/roles")
@login_required
@permission_required("admin:user")
def admin_create_role():
    body = request.get_json(silent=True) or {}
    ok_flag, msg = auth.create_role(
        body.get("key"), body.get("name"),
        [p for p in (body.get("permissions") or [])],
    )
    if ok_flag:
        return ok()
    return err(msg, 400, 400)


@bp.put("/admin/roles/<int:role_id>")
@login_required
@permission_required("admin:user")
def admin_update_role(role_id):
    body = request.get_json(silent=True) or {}
    ok_flag, msg = auth.update_role(
        role_id,
        name=body.get("name"),
        permissions=body.get("permissions"),
    )
    if ok_flag:
        return ok()
    return err(msg, 400, 400)


@bp.delete("/admin/roles/<int:role_id>")
@login_required
@permission_required("admin:user")
def admin_delete_role(role_id):
    ok_flag, msg = auth.delete_role(role_id)
    if ok_flag:
        return ok()
    return err(msg, 400, 400)


@bp.get("/admin/users")
@login_required
@permission_required("admin:user")
def admin_users():
    return ok(auth.list_users())


@bp.post("/admin/users")
@login_required
@permission_required("admin:user")
def admin_create_user():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "viewer"
    oem_ids = body.get("oem_ids") or []
    display_name = body.get("display_name") or ""
    if not username or len(password) < 6:
        return err("用户名必填且密码不少于6位", 400, 400)
    if not auth.get_role_by_key(role):
        return err("非法角色", 400, 400)
    if auth.create_user(username, password, role, oem_ids, display_name):
        return ok()
    return err("用户名已存在", 400, 400)


@bp.put("/admin/users/<int:user_id>")
@login_required
@permission_required("admin:user")
def admin_update_user(user_id):
    body = request.get_json(silent=True) or {}
    if auth.update_user(
        user_id,
        password=body.get("password") or None,
        role=body.get("role"),
        oem_ids=body.get("oem_ids"),
        display_name=body.get("display_name"),
    ):
        return ok()
    return err("更新失败或用户不存在", 400, 400)


@bp.delete("/admin/users/<int:user_id>")
@login_required
@permission_required("admin:user")
def admin_delete_user(user_id):
    if user_id == session.get("uid"):
        return err("不能删除自己", 400, 400)
    if auth.delete_user(user_id):
        return ok()
    return err("用户不存在", 400, 400)


# ---------- 数据大屏（城市维度） ----------
@bp.get("/bigscreen/cities")
@login_required
def bigscreen_cities():
    try:
        return ok(bigscreen.cities(current_oem_ids(), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/bigscreen/summary")
@login_required
def bigscreen_summary():
    try:
        return ok(bigscreen.summary(current_oem_ids(), city=request.args.get("city", ""), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/bigscreen/regions")
@login_required
def bigscreen_regions():
    try:
        return ok(bigscreen.regions(current_oem_ids(), city=request.args.get("city", ""), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/bigscreen/dist")
@login_required
def bigscreen_dist():
    try:
        return ok(bigscreen.dist(current_oem_ids(), city=request.args.get("city", ""), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/bigscreen/trend")
@login_required
def bigscreen_trend():
    try:
        return ok(bigscreen.trend(current_oem_ids(), city=request.args.get("city", ""),
                                  months=int(request.args.get("months", 12)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)


@bp.get("/bigscreen/top-cities")
@login_required
def bigscreen_top_cities():
    try:
        return ok(bigscreen.top_cities(current_oem_ids(), days=int(request.args.get("days", 30)), args=request.args))
    except Exception as e:  # noqa: BLE001
        return err(f"统计失败: {type(e).__name__}: {e}", 500, 502)
