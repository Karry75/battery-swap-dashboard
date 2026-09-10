# -*- coding: utf-8 -*-
"""业务板块模块：用户看板 / 销售看板 / 网点看板 / 客服服务台

数据来自实时主表 t_user / t_exchange_agreement / t_exchange_service_order /
t_user_exchange_rent / t_exchange_order / t_site / t_work_order 等。
"""
import datetime
import time
from core import db
from core.customers import get_customer_map
from core.filters import FilterSet

DAY_MS = 86400000

_customer_map = None


# ---- 各主表统一筛选字段映射（key=统一维度，value=SQL 列；与 filters.py 的 FilterSet 配合） ----
USER_COLUMNS = {
    "time": "u.create_time",
    "city": "u.city",
    "area": "u.area",
    "user_phone": "u.phone",
}

AGREEMENT_COLUMNS = {
    "time": "a.create_time",
    "activation_time": "a.activation_time",
    "stop_time": "a.stop_time",
    "city": "a.t_city_name",
    "agency_id": "a.agency_id",
    "battery_product_id": "a.battery_product_id",
    "site_id": "a.site_id",
    "user_phone": "a.user_phone",
    "agreement_id": "a.id",
    "employee_id": "a.sign_site_store_employee_id",
    "merchant_id": "a.sign_site_business_id",
}

ORDER_COLUMNS = {
    "time": "o.create_time",
    "city": "o.site_city",
    "area": "o.site_area",
    "street": "o.site_street",
    "agency_id": "o.agency_id",
    "battery_product_id": "o.battery_product_id",
    "site_id": "o.site_id",
    "user_phone": "o.take_user_phone",
    "agreement_id": "o.exchange_agreement_id",
    "device_sn": "o.bike_sn",
    "employee_id": "o.sign_site_store_employee_id",
}

SERVICE_COLUMNS = {
    "time": "s.create_time",
    "city": "s.t_city_name",
    "agency_id": "s.sign_agency_id",
    "battery_product_id": "s.battery_product_id",
    "site_id": "s.sign_site_id",
    "user_phone": "s.buyer_user_phone",
}

RENT_COLUMNS = {
    "time": "r.create_time",
    "battery_product_id": "r.battery_product_id",
}

SITE_COLUMNS = {
    "time": "s.create_time",
    "op_time": "s.start_open_time",          # 网点开业时间范围 op_start/op_end
    "city": "s.city",
    "area": "s.area",
    "street": "s.street",
    "community": "s.community",
    "agency_id": "s.agency_id",
    "site_id": "s.id",
    "merchant_id": "s.merchant_id",
    "battery_product_id": "s.battery_product_id",
    "bu_id": "s.bu_id",
}

WORK_ORDER_COLUMNS = {
    "time": "w.create_time",
    "city": "w.city",
    "area": "w.area",
    "street": "w.street",
    "community": "w.community",
    "agency_id": "w.agency_id",
}

COMPLAINT_COLUMNS = {
    "time": "c.create_time",
    "user_phone": "c.user_phone",
    "device_sn": "c.battery_sn",
}


def _flt(args, columns):
    """构造 FilterSet；args 为空或 None 时返回 None（表示无筛选）。"""
    if not args:
        return None
    return FilterSet(args, columns) if args is not None else None


def _customers():
    global _customer_map
    if _customer_map is None:
        _customer_map = get_customer_map()
    return _customer_map


def _now_ms():
    return int(time.time() * 1000)


def _oem_where(oem_ids, alias=""):
    if not oem_ids:
        return ""
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}oem_id IN ({','.join(map(str, oem_ids))})"


def _page(args):
    page = max(1, int(args.get("page", 1)))
    size = min(200, max(1, int(args.get("page_size", 50))))
    return page, size


def _pager(page, size, total, items):
    return {"page": page, "page_size": size, "total": int(total or 0), "items": items}


# ================= 用户看板 =================
def users_summary(oem_ids=None, args=None):
    """用户看板 KPI：总用户 / 今日新增 / 协议数 / 在租 / 押金在押 / 30天活跃

    统一筛选（args 中的用户维度：时间/城市/区域/手机号）施加于主表 t_user，
    协议/租期卡/30天活跃子统计 join t_user 承接同一筛选，保证各指标口径一致。
    """
    flt_u = _flt(args, USER_COLUMNS)
    fw = flt_u.and_clause() if flt_u else ""
    w = "u.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "u")
    w += fw
    r = db.query(
        f"SELECT COUNT(*) c FROM t_user u WHERE {w}")[0]
    today = int(time.mktime((time.localtime().tm_year, time.localtime().tm_mon,
                             time.localtime().tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
    r2 = db.query(f"SELECT COUNT(*) c FROM t_user u WHERE {w} AND u.create_time>{today}")[0]
    wa = "a.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "a") + fw
    ag = db.query(
        f"SELECT COUNT(*) c, SUM(a.status='working') using_cnt, "
        f"SUM(a.status IN ('stop','cancelled')) stop_cnt, "
        f"SUM(CASE WHEN a.deposit_status='on' THEN COALESCE(a.deposit_real_fee,0) ELSE 0 END) deposit_on "
        f"FROM t_exchange_agreement a JOIN t_user u ON a.user_id=u.id WHERE {wa}")[0]
    wr = "r.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "r") + fw
    rent = db.query(
        f"SELECT COUNT(*) c FROM t_user_exchange_rent r JOIN t_user u ON r.user_id=u.id "
        f"WHERE {wr} AND r.card_status='using'")[0]
    start30 = _now_ms() - 30 * DAY_MS
    wact = "o.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "o") + fw
    act = db.query(
        f"SELECT COUNT(DISTINCT o.take_user_id) c FROM t_exchange_order o JOIN t_user u ON o.take_user_id=u.id "
        f"WHERE {wact} AND o.create_time>{start30}")[0]
    city = db.query(
        f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(*) cnt "
        f"FROM t_user u WHERE {w} GROUP BY city ORDER BY cnt DESC LIMIT 10")
    return {
        "user_total": int(r["c"] or 0),
        "new_30d": int(r2["c"] or 0),
        "active_30d": int(act["c"] or 0),
        "agreement_total": int(ag["c"] or 0),
        "agreement_using": int(ag["using_cnt"] or 0),
        "agreement_stop": int(ag["stop_cnt"] or 0),
        "deposit_total": round(float(ag["deposit_on"] or 0), 2),
        "rent_total": int(rent["c"] or 0),
        "city_rank": [{"city": x["city"], "cnt": int(x["cnt"] or 0)} for x in city],
    }
    return {
        "user_total": int(r["c"] or 0),
        "new_30d": int(r2["c"] or 0),
        "active_30d": int(act["c"] or 0),
        "agreement_total": int(ag["c"] or 0),
        "agreement_using": int(ag["using_cnt"] or 0),
        "agreement_stop": int(ag["stop_cnt"] or 0),
        "deposit_total": round(float(ag["deposit_on"] or 0), 2),
        "rent_total": int(rent["c"] or 0),
        "city_rank": [{"city": x["city"], "cnt": int(x["cnt"] or 0)} for x in city],
    }


def users_list(oem_ids=None, keyword="", city="", page=1, page_size=50, args=None):
    """用户列表（手机号/昵称搜索 + 城市筛选 + 统一多维筛选）"""
    where = "u.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "u")
    flt = _flt(args, USER_COLUMNS)
    where += flt.and_clause() if flt else ""
    if keyword:
        kw = keyword.strip()
        where += f" AND (u.phone LIKE '%%{kw}%%' OR u.username LIKE '%%{kw}%%')"
    if city:
        where += f" AND u.city LIKE '%%{city}%%'"
    total = db.query(f"SELECT COUNT(*) c FROM t_user u WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT u.id, u.oem_id, u.username, u.phone, u.gender, u.city, u.area, "
        f"u.user_status, u.register_source, u.owner_bike_id, u.create_time, u.update_time "
        f"FROM t_user u WHERE {where} ORDER BY u.create_time DESC LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    out = []
    cmap = _customers()
    for r in rows:
        r["customer_name"] = cmap.get(str(r["oem_id"]), "未分配客户")
        r["create_time"] = _fmt_ms(r["create_time"])
        out.append(r)
    return _pager(page, page_size, total, out)


def user_agreements(oem_ids=None, user_phone="", status="", page=1, page_size=50, args=None):
    """协议明细（按手机号/状态筛选 + 统一多维筛选：协议维度）
    """
    where = "a.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "a")
    flt = _flt(args, AGREEMENT_COLUMNS)
    where += flt.and_clause() if flt else ""
    if user_phone:
        where += f" AND a.user_phone LIKE '%%{user_phone.strip()}%%'"
    if status:
        where += f" AND a.status='{status}'"
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_agreement a WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT a.id, a.oem_id, a.type, a.user_id, a.user_name, a.user_phone, a.t_city_name, "
        f"a.battery_product_id, a.rent_package_id, a.deposit_status, a.deposit_fee, a.deposit_real_fee, "
        f"a.rent_expire_time, a.activation_time, a.stop_time, a.is_contract, a.status "
        f"FROM t_exchange_agreement a WHERE {where} ORDER BY a.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    cmap = _customers()
    status_map = {"working": "使用中", "owe_rent": "欠费", "paused": "已暂停", "unsubscribing": "退订中", "wait_activate": "待生效", "stop": "已停用", "cancelled": "已取消"}
    for r in rows:
        r["customer_name"] = cmap.get(str(r["oem_id"]), "未分配客户")
        r["status_text"] = status_map.get(r["status"], r["status"])
        r["activation_time"] = _fmt_ms(r["activation_time"])
        r["stop_time"] = _fmt_ms(r["stop_time"])
        r["rent_expire_time"] = _fmt_ms(r["rent_expire_time"])
    return _pager(page, page_size, total, rows)


def user_rents(oem_ids=None, user_phone="", card_status="", page=1, page_size=50, args=None):
    """租期卡明细"""
    where = "r.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "r")
    flt = _flt(args, RENT_COLUMNS)
    where += flt.and_clause() if flt else ""
    if user_phone:
        where += f" AND r.user_id IN (SELECT id FROM t_user WHERE phone LIKE '%%{user_phone.strip()}%%')"
    if card_status:
        where += f" AND r.card_status='{card_status}'"
    total = db.query(f"SELECT COUNT(*) c FROM t_user_exchange_rent r WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT r.id, r.oem_id, r.user_id, r.battery_product_id, r.package_id, r.package_name, "
        f"r.valid_days, r.is_permanent_valid, r.work_time, r.card_status, r.expire_time, r.power_fee, "
        f"r.is_refund, r.create_time "
        f"FROM t_user_exchange_rent r WHERE {where} ORDER BY r.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    status_map = {"using": "使用中", "used": "已使用完", "refunded": "已退", "unused": "未使用", "stop": "已停用", "working": "生效中"}
    for r in rows:
        r["status_text"] = status_map.get(r["card_status"], r["card_status"])
        r["expire_time"] = _fmt_ms(r["expire_time"])
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


def user_orders(oem_ids=None, user_phone="", page=1, page_size=50, args=None):
    """用户换电订单明细（按手机号 + 统一多维筛选：订单维度）"""
    where = "o.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    where += flt.and_clause() if flt else ""
    if user_phone:
        where += f" AND o.take_user_phone LIKE '%%{user_phone.strip()}%%'"
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_order o WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT o.id, o.oem_id, o.take_user_name, o.take_user_phone, o.t_city_name, o.site_name, "
        f"o.take_exchange_sn, o.take_battery_sn, o.back_battery_sn, o.bike_sn, o.pay_price, "
        f"o.real_pay_price, o.profit_fee, o.order_status, o.is_first_take, o.use_power, o.mileage, "
        f"o.create_time "
        f"FROM t_exchange_order o WHERE {where} ORDER BY o.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


# ================= 用户看板：协议生命周期 / 分层 / 增长 / 详情 / 城市分布 =================
def users_lifecycle(oem_ids=None, args=None):
    """协议生命周期统计：生效中 / 欠费 / 已暂停 / 退订中 / 待生效 / 已终止

    状态枚举以真实库为准：working=生效中、owe_rent=欠费、paused=已暂停、
    unsubscribing=退订中、wait_activate=待生效、stop/cancelled=已终止。
    数据实时从 AnalyticDB 抽取，禁止写死。
    """
    w = "a.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "a")
    flt = _flt(args, AGREEMENT_COLUMNS)
    w += flt.and_clause() if flt else ""
    r = db.query(
        f"SELECT COUNT(*) total_cnt, "
        f"SUM(a.status='working') working_cnt, "
        f"SUM(a.status='owe_rent') arrears_cnt, "
        f"SUM(a.status='paused') paused_cnt, "
        f"SUM(a.status='unsubscribing') unsubscribing_cnt, "
        f"SUM(a.status='wait_activate') wait_cnt, "
        f"SUM(a.status IN ('stop','cancelled')) stop_cnt "
        f"FROM t_exchange_agreement a WHERE {w}")[0]
    total = int(r["total_cnt"] or 0)
    items = [
        {"key": "using", "name": "生效中", "count": int(r["working_cnt"] or 0)},
        {"key": "arrears", "name": "欠费", "count": int(r["arrears_cnt"] or 0)},
        {"key": "paused", "name": "已暂停", "count": int(r["paused_cnt"] or 0)},
        {"key": "unsubscribing", "name": "退订中", "count": int(r["unsubscribing_cnt"] or 0)},
        {"key": "pending", "name": "待生效", "count": int(r["wait_cnt"] or 0)},
        {"key": "stop", "name": "已终止", "count": int(r["stop_cnt"] or 0)},
    ]
    for it in items:
        it["percent"] = round(it["count"] * 100.0 / total, 2) if total else 0
    return {"total": total, "items": items}


def users_tier(oem_ids=None, days=30, args=None):
    """近 N 天用户分层：
    - 按换电次数：高频 >=30 次 / 中频 10~29 次 / 低频 1~9 次
    - 按消费金额（分为单位，以 expend_power_fee 电费为准）：
      高价值 >=5000 分（50 元）/ 中价值 1000~4999 分（10~50 元）/ 低价值 <1000 分
    阈值以 threshold 字段返回，前端可直接展示口径。
    """
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    w += flt.and_clause() if flt else ""
    start = _now_ms() - days * DAY_MS
    r = db.query(
        f"SELECT COUNT(*) total_users, "
        f"SUM(t.cnt>=30) freq_high, SUM(t.cnt>=10 AND t.cnt<30) freq_medium, "
        f"SUM(t.cnt>0 AND t.cnt<10) freq_low, "
        f"SUM(t.fee>=5000) value_high, SUM(t.fee>=1000 AND t.fee<5000) value_medium, "
        f"SUM(t.fee>0 AND t.fee<1000) value_low "
        f"FROM (SELECT o.take_user_id, COUNT(*) cnt, COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start} "
        f"GROUP BY o.take_user_id) t")[0]
    return {
        "days": days,
        "threshold": {
            "frequency": {"high": 30, "medium": 10},
            "value": {"high_fen": 5000, "medium_fen": 1000},
        },
        "total_users": int(r["total_users"] or 0),
        "frequency": {
            "high": int(r["freq_high"] or 0),
            "medium": int(r["freq_medium"] or 0),
            "low": int(r["freq_low"] or 0),
        },
        "value": {
            "high": int(r["value_high"] or 0),
            "medium": int(r["value_medium"] or 0),
            "low": int(r["value_low"] or 0),
        },
    }


def users_growth(oem_ids=None, months=6, args=None):
    """近 N 月新增用户趋势 + 注册来源 register_source 分布"""
    w = "u.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "u")
    flt = _flt(args, USER_COLUMNS)
    w += flt.and_clause() if flt else ""
    start = _month_start_ms(months)
    rows = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(u.create_time/1000), '%%Y-%%m') month, COUNT(*) cnt "
        f"FROM t_user u WHERE {w} AND u.create_time>={start} "
        f"GROUP BY month ORDER BY month")
    src = db.query(
        f"SELECT COALESCE(NULLIF(u.register_source,''),'未知') register_source, COUNT(*) cnt "
        f"FROM t_user u WHERE {w} GROUP BY register_source ORDER BY cnt DESC")
    return {
        "months": months,
        "trend": _fill_months(months, rows),
        "register_source": [
            {"register_source": r["register_source"], "cnt": int(r["cnt"] or 0)} for r in src
        ],
    }


def _month_start_ms(months_back):
    """返回 N 个月前月初的毫秒时间戳（用于新增趋势起点）"""
    now = datetime.datetime.now()
    y, m = now.year, now.month
    for _ in range(months_back - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return int(datetime.datetime(y, m, 1).timestamp() * 1000)


def _fill_months(months, rows):
    """将查询结果补齐为最近 N 个月（含空月补 0）"""
    data = {r["month"]: int(r["cnt"] or 0) for r in rows}
    now = datetime.datetime.now()
    out = []
    for i in range(months - 1, -1, -1):
        y, m = now.year, now.month
        for _ in range(i):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        key = f"{y:04d}-{m:02d}"
        out.append({"month": key, "cnt": data.get(key, 0)})
    return out


def users_detail(oem_ids=None, phone=""):
    """单用户详情：基本信息 + 协议 + 租期卡 + 订单汇总（按手机号模糊查询取最新）"""
    phone = (phone or "").strip()
    if not phone:
        return {"user": None, "agreements": [], "rents": [], "orders": None}
    w = "u.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "u")
    users = db.query(
        f"SELECT u.id, u.oem_id, u.username, u.phone, u.gender, u.city, u.area, "
        f"u.user_status, u.register_source, u.owner_bike_id, u.create_time, u.update_time "
        f"FROM t_user u WHERE {w} AND u.phone LIKE '%%{phone}%%' "
        f"ORDER BY u.create_time DESC LIMIT 1")
    if not users:
        return {"user": None, "agreements": [], "rents": [], "orders": None}
    u = users[0]
    uid = int(u["id"])
    u["customer_name"] = _customers().get(str(u["oem_id"]), "未分配客户")
    u["create_time"] = _fmt_ms(u["create_time"])
    u["update_time"] = _fmt_ms(u["update_time"])

    wa = "a.is_del=0"
    if oem_ids:
        wa += _oem_where(oem_ids, "a")
    agreements = db.query(
        f"SELECT a.id, a.type, a.user_name, a.user_phone, a.t_city_name, a.battery_product_id, "
        f"a.rent_package_id, a.deposit_status, a.deposit_fee, a.deposit_real_fee, "
        f"a.rent_expire_time, a.activation_time, a.stop_time, a.is_contract, a.status "
        f"FROM t_exchange_agreement a WHERE {wa} AND a.user_id={uid} "
        f"ORDER BY a.create_time DESC LIMIT 100")
    status_map = {"working": "使用中", "owe_rent": "欠费", "paused": "已暂停", "unsubscribing": "退订中", "wait_activate": "待生效", "stop": "已停用", "cancelled": "已取消"}
    for a in agreements:
        a["status_text"] = status_map.get(a["status"], a["status"])
        a["activation_time"] = _fmt_ms(a["activation_time"])
        a["stop_time"] = _fmt_ms(a["stop_time"])
        a["rent_expire_time"] = _fmt_ms(a["rent_expire_time"])

    wr = "r.is_del=0"
    if oem_ids:
        wr += _oem_where(oem_ids, "r")
    rents = db.query(
        f"SELECT r.id, r.battery_product_id, r.package_id, r.package_name, r.valid_days, "
        f"r.is_permanent_valid, r.work_time, r.card_status, r.expire_time, r.power_fee, "
        f"r.is_refund, r.create_time "
        f"FROM t_user_exchange_rent r WHERE {wr} AND r.user_id={uid} "
        f"ORDER BY r.create_time DESC LIMIT 100")
    card_map = {"using": "使用中", "used": "已使用完", "refunded": "已退", "unused": "未使用", "stop": "已停用", "working": "生效中"}
    for rr in rents:
        rr["status_text"] = card_map.get(rr["card_status"], rr["card_status"])
        rr["expire_time"] = _fmt_ms(rr["expire_time"])
        rr["create_time"] = _fmt_ms(rr["create_time"])

    wo = "o.is_del=0"
    if oem_ids:
        wo += _oem_where(oem_ids, "o")
    start30 = _now_ms() - 30 * DAY_MS
    orders = db.query(
        f"SELECT COUNT(*) total_cnt, COALESCE(SUM(o.real_pay_price),0) total_fee, "
        f"SUM(o.create_time>{start30}) cnt_30d, "
        f"COALESCE(SUM(CASE WHEN o.create_time>{start30} THEN o.real_pay_price ELSE 0 END),0) fee_30d "
        f"FROM t_exchange_order o WHERE {wo} AND o.take_user_id={uid}")[0]
    return {
        "user": u,
        "agreements": agreements,
        "rents": rents,
        "orders": {
            "total": int(orders["total_cnt"] or 0),
            "total_fee": round(float(orders["total_fee"] or 0), 2),
            "cnt_30d": int(orders["cnt_30d"] or 0),
            "fee_30d": round(float(orders["fee_30d"] or 0), 2),
        },
    }


def users_city_detail(oem_ids=None, args=None):
    """城市分布明细：用户数 / 活跃用户(30d) / 协议数 / 近30天换电次数

    统一以 t_user.city（用户注册城市）为维度聚合，缺失城市归为"未知"。
    支持用户维度筛选（时间/城市/区域/手机号），各子查询统计口径一致。
    """
    wu = "u.is_del=0"
    if oem_ids:
        wu += _oem_where(oem_ids, "u")
    flt = _flt(args, USER_COLUMNS)
    fw = flt.and_clause() if flt else ""
    wu += fw
    users = db.query(
        f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(*) users "
        f"FROM t_user u WHERE {wu} GROUP BY city ORDER BY users DESC")

    start30 = _now_ms() - 30 * DAY_MS
    wo = "o.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "o") + fw
    active = db.query(
        f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(DISTINCT o.take_user_id) active_users "
        f"FROM t_exchange_order o JOIN t_user u ON o.take_user_id=u.id "
        f"WHERE {wo} AND o.create_time>{start30} GROUP BY city")
    ex30 = db.query(
        f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(*) exchange_30d "
        f"FROM t_exchange_order o JOIN t_user u ON o.take_user_id=u.id "
        f"WHERE {wo} AND o.create_time>{start30} GROUP BY city")

    wa = "a.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "a") + fw
    aggr = db.query(
        f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(*) agreements "
        f"FROM t_exchange_agreement a JOIN t_user u ON a.user_id=u.id "
        f"WHERE {wa} GROUP BY city")

    city_map = {}

    def _merge(rows, field):
        for r in rows:
            c = city_map.setdefault(r["city"], {
                "city": r["city"], "users": 0, "active_users": 0,
                "agreements": 0, "exchange_30d": 0,
            })
            c[field] = int(r[field] or 0)

    _merge(users, "users")
    _merge(active, "active_users")
    _merge(ex30, "exchange_30d")
    _merge(aggr, "agreements")
    items = sorted(city_map.values(), key=lambda x: (x["users"], x["exchange_30d"]), reverse=True)
    return {"items": items}


# ================= 销售看板 =================
def sales_summary(oem_ids=None, days=30, args=None):
    """销售看板 KPI：30天销售额 / 协议新增 / 套餐销量 / 换电收入

    三维度分别构造 FilterSet：套餐订单用 SERVICE_COLUMNS、
    协议新增用 AGREEMENT_COLUMNS、换电收入用 ORDER_COLUMNS，
    各维度对不存在的表列自动跳过（合理裁剪）。
    """
    w = "s.is_del=0"
    wo = "o.is_del=0"
    wa = "a.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "s")
        wo += _oem_where(oem_ids, "o")
        wa += _oem_where(oem_ids, "a")
    fs = _flt(args, SERVICE_COLUMNS)
    w += fs.and_clause() if fs else ""
    fo = _flt(args, ORDER_COLUMNS)
    wo += fo.and_clause() if fo else ""
    fa = _flt(args, AGREEMENT_COLUMNS)
    wa += fa.and_clause() if fa else ""
    start = _now_ms() - days * DAY_MS
    so = db.query(
        f"SELECT COUNT(*) c, COALESCE(SUM(s.pay_fee),0) fee "
        f"FROM t_exchange_service_order s WHERE {w} AND s.is_pay=1 AND s.create_time>{start}")[0]
    ag = db.query(
        f"SELECT COUNT(*) c FROM t_exchange_agreement a WHERE {wa} AND a.create_time>{start}")[0]
    ex = db.query(
        f"SELECT COUNT(*) c, COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {wo} AND o.create_time>{start}")[0]
    return {
        "days": days,
        "service_order_count": int(so["c"] or 0),
        "service_order_fee": round(float(so["fee"] or 0), 2),
        "new_agreement": int(ag["c"] or 0),
        "exchange_count": int(ex["c"] or 0),
        "exchange_fee": round(float(ex["fee"] or 0), 2),
    }


def sales_site_rank(oem_ids=None, days=30, limit=20, args=None):
    """网点销售排行（近 N 天订单金额/数量 Top；支持订单维度筛选）"""
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    w += flt.and_clause() if flt else ""
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT COALESCE(NULLIF(o.site_name,''),'未知网点') site_name, "
        f"COUNT(*) cnt, COUNT(DISTINCT o.take_user_id) users, "
        f"COALESCE(SUM(o.real_pay_price),0) fee, COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start} "
        f"GROUP BY site_name ORDER BY fee DESC LIMIT {limit}")
    return [{"site_name": r["site_name"], "exchange_count": int(r["cnt"] or 0),
             "active_users": int(r["users"] or 0), "fee": round(float(r["fee"] or 0), 2),
             "profit_fee": round(float(r["profit"] or 0), 2)} for r in rows]


def sales_staff_rank(oem_ids=None, days=30, limit=20, args=None):
    """业务员业绩排行（签约门店关联业务员：sign_site_store_employee_id 聚合协议；支持协议维度筛选）"""
    w = "a.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "a")
    flt = _flt(args, AGREEMENT_COLUMNS)
    w += flt.and_clause() if flt else ""
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT a.sign_site_business_name business_name, "
        f"COUNT(*) cnt, COUNT(DISTINCT a.user_id) users "
        f"FROM t_exchange_agreement a WHERE {w} AND a.create_time>{start} "
        f"GROUP BY business_name ORDER BY cnt DESC LIMIT {limit}")
    return [{"business_name": r["business_name"] or "未知商户",
             "agreement_count": int(r["cnt"] or 0), "users": int(r["users"] or 0)} for r in rows]


def sales_service_orders(oem_ids=None, order_status="", page=1, page_size=50, args=None):
    """套餐订单明细（支持套餐订单维度筛选）"""
    where = "s.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "s")
    flt = _flt(args, SERVICE_COLUMNS)
    where += flt.and_clause() if flt else ""
    if order_status:
        where += f" AND s.order_status='{order_status}'"
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_service_order s WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT s.id, s.oem_id, s.goods_type, s.goods_quantity, s.battery_product_id, s.t_city_name, "
        f"s.sign_site_name, s.buyer_user_name, s.buyer_user_phone, s.fee, s.pay_fee, s.pay_way, "
        f"s.is_pay, s.pay_time, s.is_refund, s.order_status, s.create_time "
        f"FROM t_exchange_service_order s WHERE {where} ORDER BY s.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["pay_time"] = _fmt_ms(r["pay_time"])
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


# ================= 网点看板 =================
def sites_summary(oem_ids=None, args=None):
    """网点看板 KPI：总网点 / 营业中 / 异常 / 24h营业 / 独立电表

    主指标以 t_site 为基（SITE_COLUMNS），异常工单以 t_work_order 为基（WORK_ORDER_COLUMNS）。
    """
    w = "s.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "s")
    flt = _flt(args, SITE_COLUMNS)
    w += flt.and_clause() if flt else ""
    r = db.query(
        f"SELECT COUNT(*) c, "
        f"SUM(s.site_status='on') open_cnt, "
        f"SUM(s.site_status='off') closed_cnt, "
        f"SUM(s.is_all_day_open=1) allday_cnt, "
        f"SUM(s.alone_meter_status IN ('only_install','gdj_install','install_and_use')) meter_cnt "
        f"FROM t_site s WHERE {w}")[0]
    # 异常：最近30天有工单的网点数（工单维度继承筛选）
    wo = "w.is_del=0"
    if oem_ids:
        wo += _oem_where(oem_ids, "w")
    wflt = _flt(args, WORK_ORDER_COLUMNS)
    wo += wflt.and_clause() if wflt else ""
    wc = db.query(f"SELECT COUNT(DISTINCT w.event_id) c FROM t_work_order w WHERE {wo} AND w.status='doing'")[0]
    return {
        "site_total": int(r["c"] or 0),
        "site_open": int(r["open_cnt"] or 0),
        "site_closed": int(r["closed_cnt"] or 0),
        "site_allday": int(r["allday_cnt"] or 0),
        "site_meter": int(r["meter_cnt"] or 0),
        "work_order_doing": int(wc["c"] or 0),
    }


def sites_list(oem_ids=None, keyword="", type_="", status="", page=1, page_size=50, args=None):
    """网点列表（关键字/类型/状态 + 统一多维筛选：网点维度）"""
    where = "s.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "s")
    flt = _flt(args, SITE_COLUMNS)
    where += flt.and_clause() if flt else ""
    if keyword:
        kw = keyword.strip()
        where += f" AND (s.name LIKE '%%{kw}%%' OR s.contact_person_name LIKE '%%{kw}%%' OR s.contact_person_tel LIKE '%%{kw}%%')"
    if type_:
        where += f" AND s.type='{type_}'"
    if status:
        status = {"open": "on", "closed": "off"}.get(status, status)
        where += f" AND s.site_status='{status}'"
    total = db.query(f"SELECT COUNT(*) c FROM t_site s WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT s.id, s.oem_id, s.type, s.name, s.contact_person_name, s.contact_person_tel, "
        f"s.province, s.city, s.area, s.address, s.site_status, s.audit_progress, "
        f"s.is_all_day_open, s.alone_meter_status, s.electric_settle_way, s.longitude, s.latitude, "
        f"s.store_manager_name, s.create_time "
        f"FROM t_site s WHERE {where} ORDER BY s.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    cmap = _customers()
    type_map = {"exchange": "换电网点", "sale": "销售网点", "mixed": "综合网点", "repair": "维修网点"}
    for r in rows:
        r["customer_name"] = cmap.get(str(r["oem_id"]), "未分配客户")
        r["type_text"] = type_map.get(r["type"], r["type"])
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


def site_orders(oem_ids=None, site_id=None, page=1, page_size=50, args=None):
    """指定网点换电订单明细（支持订单维度筛选）"""
    where = "o.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    where += flt.and_clause() if flt else ""
    if site_id:
        where += f" AND o.site_id={int(site_id)}"
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_order o WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT o.id, o.oem_id, o.site_name, o.take_user_name, o.take_user_phone, "
        f"o.take_exchange_sn, o.take_battery_sn, o.bike_sn, o.real_pay_price, o.profit_fee, "
        f"o.is_first_take, o.create_time "
        f"FROM t_exchange_order o WHERE {where} ORDER BY o.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


# ================= 客服服务台 =================
def service_query(oem_ids=None, keyword="", city="", status="", page=1, page_size=50, args=None):
    """协议查询台（手机号/姓名/城市/状态 + 统一协议维度筛选）"""
    where = "a.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "a")
    flt = _flt(args, AGREEMENT_COLUMNS)
    where += flt.and_clause() if flt else ""
    if keyword:
        kw = keyword.strip()
        where += f" AND (a.user_name LIKE '%%{kw}%%' OR a.user_phone LIKE '%%{kw}%%')"
    if city:
        where += f" AND a.t_city_name LIKE '%%{city}%%'"
    if status:
        where += f" AND a.status='{status}'"
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_agreement a WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT a.id, a.oem_id, a.user_name, a.user_phone, a.t_city_name, a.type, "
        f"a.battery_product_id, a.deposit_status, a.deposit_fee, a.rent_package_id, "
        f"a.activation_time, a.rent_expire_time, a.status, a.remark "
        f"FROM t_exchange_agreement a WHERE {where} ORDER BY a.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    status_map = {"working": "使用中", "owe_rent": "欠费", "paused": "已暂停", "unsubscribing": "退订中", "wait_activate": "待生效", "stop": "已停用", "cancelled": "已取消"}
    for r in rows:
        r["status_text"] = status_map.get(r["status"], r["status"])
        r["activation_time"] = _fmt_ms(r["activation_time"])
        r["rent_expire_time"] = _fmt_ms(r["rent_expire_time"])
    return _pager(page, page_size, total, rows)


def service_complaints(oem_ids=None, page=1, page_size=50, args=None):
    """客诉记录（数据截至2023-08，仅展示存量；支持客诉维度筛选）"""
    where = "c.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "c")
    flt = _flt(args, COMPLAINT_COLUMNS)
    where += flt.and_clause() if flt else ""
    total = db.query(f"SELECT COUNT(*) c FROM t_exchange_order_complaint c WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT c.id, c.oem_id, c.source, c.type, c.user_name, c.user_phone, c.exchange_sn, "
        f"c.battery_sn, c.operation_status, c.order_fail_reason, c.remark, c.create_time "
        f"FROM t_exchange_order_complaint c WHERE {where} ORDER BY c.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


def _fmt_ms(v):
    if not v:
        return ""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return str(v)
    if v > 10_000_000_000:  # 毫秒
        v = v / 1000
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))
