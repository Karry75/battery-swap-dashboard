# -*- coding: utf-8 -*-
"""财务 / 设备资产 / 优惠券 / 人员 / 深度分析 模块

数据源：t_expense_bill（费用单，1216万行）、t_battery_transfer_log（电池流转）、
t_coupon（优惠券）、t_user_exchange_deposit（押金）、t_battery（电池）、
t_exchange（换电柜）、t_bike（车辆）、t_work_order（工单）。
"""
import time
from core import db
from core.customers import get_customer_map
from core.filters import FilterSet, AGREEMENT_COLUMNS, ORDER_COLUMNS, SERVICE_COLUMNS, \
    SITE_COLUMNS, EXCHANGE_COLUMNS, BATTERY_COLUMNS, EXPENSE_COLUMNS, \
    COUPON_COLUMNS, WORK_ORDER_COLUMNS

DAY_MS = 86400000
_customer_map = None


def _flt(args, columns):
    """按统一筛选参数构造 FilterSet；空筛选返回 None"""
    if not args:
        return None
    fs = FilterSet(args, columns)
    return fs if fs.has else None


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


def _fmt_ms(v):
    if not v:
        return ""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return str(v)
    if v > 10_000_000_000:
        v = v / 1000
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))


# ================= 财务看板 =================
def finance_summary(oem_ids=None, days=30, args=None):
    """财务看板 KPI：30天收入 / 支出 / 毛利 / 订单量（支持订单/支出维度筛选）"""
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    oc = _flt(args, ORDER_COLUMNS)
    if oc:
        w += oc.and_clause()
    wb = "b.is_del=0 AND b.is_cancel=0"
    if oem_ids:
        wb += _oem_where(oem_ids, "b")
    bc = _flt(args, EXPENSE_COLUMNS)
    if bc:
        wb += bc.and_clause()
    start = _now_ms() - days * DAY_MS
    inc = db.query(
        f"SELECT COUNT(*) c, COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start}")[0]
    exp = db.query(
        f"SELECT COUNT(*) c, COALESCE(SUM(b.fee),0) fee "
        f"FROM t_expense_bill b WHERE {wb} AND b.create_time>{start}")[0]
    return {
        "days": days,
        "income_count": int(inc["c"] or 0),
        "income_fee": round(float(inc["fee"] or 0), 2),
        "profit_fee": round(float(inc["profit"] or 0), 2),
        "expense_count": int(exp["c"] or 0),
        "expense_fee": round(float(exp["fee"] or 0), 2),
    }


def finance_income_trend(oem_ids=None, months=12, args=None):
    """近 N 月收入趋势（换电收入 / 套餐服务收入，支持订单/服务单维度筛选）"""
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    oc = _flt(args, ORDER_COLUMNS)
    if oc:
        w += oc.and_clause()
    ws = "s.is_del=0"
    if oem_ids:
        ws += _oem_where(oem_ids, "s")
    sc = _flt(args, SERVICE_COLUMNS)
    if sc:
        ws += sc.and_clause()
    start = _now_ms() - months * 30 * DAY_MS
    rows = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(o.create_time/1000), '%%Y-%%m') ym, "
        f"COUNT(*) cnt, COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start} GROUP BY ym ORDER BY ym")
    svc = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(s.create_time/1000), '%%Y-%%m') ym, "
        f"COALESCE(SUM(s.pay_fee),0) fee "
        f"FROM t_exchange_service_order s WHERE {ws} AND s.is_pay=1 AND s.create_time>{start} GROUP BY ym ORDER BY ym")
    smap = {r["ym"]: r for r in svc}
    out = []
    for r in rows:
        s = smap.get(r["ym"], {})
        out.append({
            "month": r["ym"],
            "income": round(float(r["fee"] or 0), 2),
            "profit": round(float(r["profit"] or 0), 2),
            "service_fee": round(float(s.get("fee") or 0), 2),
            "order_count": int(r["cnt"] or 0),
        })
    return out


def finance_expense_list(oem_ids=None, fee_type="", keyword="", page=1, page_size=50, args=None):
    """费用支出明细（按类型/商户/时间/事业线筛选）"""
    where = "b.is_del=0 AND b.is_cancel=0"
    if oem_ids:
        where += _oem_where(oem_ids, "b")
    flt = _flt(args, EXPENSE_COLUMNS)
    if flt:
        where += flt.and_clause()
    if fee_type:
        where += f" AND b.expense_type='{fee_type}'"
    if keyword:
        kw = keyword.strip()
        where += f" AND (b.out_unit_name LIKE '%%{kw}%%' OR b.expense_name LIKE '%%{kw}%%')"
    total = db.query(f"SELECT COUNT(*) c FROM t_expense_bill b WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT b.id, b.oem_id, b.expense_type, b.expense_name, b.out_unit_name, "
        f"b.expense_description, b.fee, b.bill_status, b.is_cancel, b.create_time, b.update_time, b.remark, b.bu_id "
        f"FROM t_expense_bill b WHERE {where} ORDER BY b.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


def finance_expense_types(oem_ids=None, days=30, args=None):
    """费用类型分布（近 N 天，支持支出维度筛选）"""
    w = "b.is_del=0 AND b.is_cancel=0"
    if oem_ids:
        w += _oem_where(oem_ids, "b")
    flt = _flt(args, EXPENSE_COLUMNS)
    if flt:
        w += flt.and_clause()
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT b.expense_type, COUNT(*) cnt, COALESCE(SUM(b.fee),0) fee "
        f"FROM t_expense_bill b WHERE {w} AND b.create_time>{start} GROUP BY b.expense_type ORDER BY fee DESC LIMIT 20")
    return [{"fee_type": r["expense_type"] or "未知", "count": int(r["cnt"] or 0),
             "fee": round(float(r["fee"] or 0), 2)} for r in rows]


def finance_deposit_list(oem_ids=None, deposit_status="", page=1, page_size=50, args=None):
    """押金明细（存量表，最新2023-08；支持时间/手机号筛选）"""
    where = "d.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "d")
    if deposit_status:
        where += f" AND d.take_battery_status='{deposit_status}'"
    if args and (args.get("start") or args.get("end") or args.get("user_phone")):
        fs = FilterSet(args, {"time": "d.create_time", "user_phone": "u.phone"})
        where += fs.and_clause()
    total = db.query(
        f"SELECT COUNT(*) c FROM t_user_exchange_deposit d LEFT JOIN t_user u ON u.id=d.user_id "
        f"WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT d.id, d.oem_id, d.user_id, u.username, u.phone, d.take_battery_status, "
        f"d.fee, d.is_withdraw, d.is_freeze, d.create_time, d.update_time "
        f"FROM t_user_exchange_deposit d LEFT JOIN t_user u ON u.id=d.user_id "
        f"WHERE {where} ORDER BY d.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


# ================= 设备资产看板 =================
def assets_summary(oem_ids=None, args=None):
    """设备资产总览（换电柜支持城市/网点/代理商/品牌筛选；电池支持代理商/品牌；
    车辆数/故障数为全量，不随设备筛选变动）"""
    ex_sub = (f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
              f"WHERE e.is_del=0{_oem_where(oem_ids, 'e')}")
    ex_flt = _flt(args, EXCHANGE_COLUMNS)
    if ex_flt:
        ex_sub += ex_flt.and_clause()
    bt_w = f"is_del=0{_oem_where(oem_ids)}"
    bt_flt = _flt(args, BATTERY_COLUMNS)
    if bt_flt:
        bt_w += bt_flt.and_clause()
    st_w = "s.is_del=0"
    if oem_ids:
        st_w += _oem_where(oem_ids, "s")
    st_flt = _flt(args, SITE_COLUMNS)
    if st_flt:
        st_w += st_flt.and_clause()

    ex_total = db.query(f"SELECT COUNT(*) c {ex_sub}")[0]["c"]
    ex_on = db.query(f"SELECT COUNT(*) c {ex_sub} AND e.online_status='online'")[0]["c"]
    r = db.query(
        f"SELECT "
        f"(SELECT COUNT(*) FROM t_battery b WHERE {bt_w}) bt_total, "
        f"(SELECT COUNT(*) FROM t_battery b WHERE {bt_w} AND b.online_status='online') bt_on, "
        f"(SELECT COUNT(DISTINCT e.id) FROM t_monitor_ex_event e INNER JOIN t_monitor_ex_event_battery eb ON eb.ex_event_id=e.id WHERE e.is_del=0 AND e.status='init') bt_fault, "
        f"(SELECT COUNT(*) FROM t_bike WHERE is_del=0) bk_total, "
        f"(SELECT COUNT(*) FROM t_bike WHERE is_del=0 AND online_status='online') bk_on, "
        f"(SELECT COUNT(*) FROM t_site s WHERE {st_w}) st_total")[0]
    return {
        "exchange": {"total": int(ex_total or 0), "online": int(ex_on or 0)},
        "battery": {"total": int(r["bt_total"] or 0), "online": int(r["bt_on"] or 0), "fault": int(r["bt_fault"] or 0)},
        "bike": {"total": int(r["bk_total"] or 0), "online": int(r["bk_on"] or 0)},
        "site": {"total": int(r["st_total"] or 0)},
    }


def assets_battery_status(oem_ids=None, args=None):
    """电池状态分布（电池状态字段分布；支持代理商/品牌筛选）"""
    w = "b.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "b")
    flt = _flt(args, BATTERY_COLUMNS)
    if flt:
        w += flt.and_clause()
    rows = db.query(
        f"SELECT COALESCE(NULLIF(b.battery_status,''),'unknown') status, COUNT(*) c "
        f"FROM t_battery b WHERE {w} GROUP BY status ORDER BY c DESC")
    return [{"status": r["status"], "count": int(r["c"])} for r in rows]


def assets_transfer_logs(oem_ids=None, transfer_type="", keyword="", page=1, page_size=50, args=None):
    """电池流转记录（支持时间/电池SN筛选）"""
    where = "t.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "t")
    if transfer_type:
        where += f" AND t.transfer_type='{transfer_type}'"
    if keyword:
        kw = keyword.strip()
        where += f" AND t.battery_device_sn LIKE '%%{kw}%%'"
    if args and (args.get("start") or args.get("end") or args.get("device_sn")):
        fs = FilterSet(args, {"time": "t.create_time", "device_sn": "t.battery_device_sn"})
        where += fs.and_clause()
    total = db.query(f"SELECT COUNT(*) c FROM t_battery_transfer_log t WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT t.id, t.oem_id, t.battery_id, t.battery_device_sn, t.transfer_type, t.transfer_status, "
        f"t.inflow_name, t.outflow_name, t.inflow_type, t.outflow_type, t.create_time "
        f"FROM t_battery_transfer_log t WHERE {where} ORDER BY t.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


def assets_work_orders(oem_ids=None, status="", page=1, page_size=50, args=None):
    """运维工单（支持工单维度筛选：时间/省市街区/代理商/状态）"""
    where = "w.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "w")
    if status:
        where += f" AND w.status='{status}'"
    flt = _flt(args, WORK_ORDER_COLUMNS)
    if flt:
        where += flt.and_clause()
    total = db.query(f"SELECT COUNT(*) c FROM t_work_order w WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT w.id, w.oem_id, w.event_type, w.event_id, w.event_name, w.agency_name, "
        f"w.address, w.status, w.priority, w.description, w.creator_name, w.handler_name, "
        f"w.create_time, w.handle_start_time, w.handle_stop_time "
        f"FROM t_work_order w WHERE {where} ORDER BY w.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
        r["handle_start_time"] = _fmt_ms(r["handle_start_time"])
        r["handle_stop_time"] = _fmt_ms(r["handle_stop_time"])
    return _pager(page, page_size, total, rows)


# ================= 优惠券看板 =================
def coupons_summary(oem_ids=None, args=None):
    """优惠券总览（支持电池产品/品牌维度筛选）"""
    w = "c.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "c")
    flt = _flt(args, COUPON_COLUMNS)
    if flt:
        w += flt.and_clause()
    r = db.query(
        f"SELECT COUNT(*) c, "
        f"SUM(c.coupon_status='on') on_cnt, SUM(c.coupon_status='off') off_cnt "
        f"FROM t_coupon c WHERE {w}")[0]
    return {
        "coupon_total": int(r["c"] or 0),
        "on": int(r["on_cnt"] or 0),
        "off": int(r["off_cnt"] or 0),
    }


def coupons_list(oem_ids=None, status="", keyword="", page=1, page_size=50, args=None):
    """优惠券明细（支持电池产品/品牌/时间筛选）"""
    where = "c.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "c")
    if status:
        where += f" AND c.coupon_status='{status}'"
    if keyword:
        kw = keyword.strip()
        where += f" AND c.title LIKE '%%{kw}%%'"
    flt = _flt(args, COUPON_COLUMNS)
    if flt:
        where += flt.and_clause()
    total = db.query(f"SELECT COUNT(*) c FROM t_coupon c WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT c.id, c.oem_id, c.title, c.channel, c.deduct_type, c.deduct_rule, "
        f"c.coupon_status, c.creator_name, c.valid_days, c.create_time "
        f"FROM t_coupon c WHERE {where} ORDER BY c.create_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
    return _pager(page, page_size, total, rows)


# ================= 人员看板 =================
def staff_summary(oem_ids=None, args=None):
    """人员总览（按协议签约商户/门店员工统计；支持协议维度筛选）"""
    where = "a.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "a")
    flt = _flt(args, AGREEMENT_COLUMNS)
    if flt:
        where += flt.and_clause()
    # 有协议签署的商户数量（业务员维度）
    rows = db.query(
        f"SELECT COALESCE(NULLIF(a.sign_site_business_name,''),'未知') bname, COUNT(*) c "
        f"FROM t_exchange_agreement a WHERE {where} GROUP BY bname ORDER BY c DESC LIMIT 20")
    total_staff = db.query(
        f"SELECT COUNT(DISTINCT COALESCE(NULLIF(a.sign_site_business_name,''),'未知')) c "
        f"FROM t_exchange_agreement a WHERE {where}")[0]["c"]
    return {
        "total_staff": int(total_staff or 0),
        "staff_rank": [{"name": r["bname"], "agreement_count": int(r["c"])} for r in rows],
    }


def staff_work_orders(oem_ids=None, solve_user="", page=1, page_size=50, args=None):
    """人员工单处理记录（支持工单维度筛选：时间/省市街区/代理商/处理人）"""
    where = "w.is_del=0"
    if oem_ids:
        where += _oem_where(oem_ids, "w")
    if solve_user:
        where += f" AND w.handler_name LIKE '%%{solve_user.strip()}%%'"
    flt = _flt(args, WORK_ORDER_COLUMNS)
    if flt:
        where += flt.and_clause()
    total = db.query(f"SELECT COUNT(*) c FROM t_work_order w WHERE {where}")[0]["c"]
    rows = db.query(
        f"SELECT w.id, w.oem_id, w.event_type, w.event_name, w.address, w.status, w.creator_name, "
        f"w.handler_name, w.create_time, w.handle_start_time, w.handle_stop_time "
        f"FROM t_work_order w WHERE {where} ORDER BY w.handle_stop_time DESC "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}")
    for r in rows:
        r["create_time"] = _fmt_ms(r["create_time"])
        r["handle_start_time"] = _fmt_ms(r["handle_start_time"])
        r["handle_stop_time"] = _fmt_ms(r["handle_stop_time"])
    return _pager(page, page_size, total, rows)


# ================= 深度分析 =================
def insights_exchange_peak(oem_ids=None, days=7, args=None):
    """换电高峰时段分析（近 N 天按小时分布；支持订单维度筛选）"""
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    if flt:
        w += flt.and_clause()
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT HOUR(FROM_UNIXTIME(o.create_time/1000)) hour, COUNT(*) cnt "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start} GROUP BY hour ORDER BY hour")
    return [{"hour": int(r["hour"]), "count": int(r["cnt"])} for r in rows]


def insights_first_take(oem_ids=None, days=30, args=None):
    """新老用户占比（首次换电 vs 复购；支持订单维度筛选）"""
    w = "o.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "o")
    flt = _flt(args, ORDER_COLUMNS)
    if flt:
        w += flt.and_clause()
    start = _now_ms() - days * DAY_MS
    r = db.query(
        f"SELECT SUM(o.is_first_take=1) first_cnt, SUM(o.is_first_take=0) again_cnt "
        f"FROM t_exchange_order o WHERE {w} AND o.create_time>{start}")[0]
    return {"first_take": int(r["first_cnt"] or 0), "again": int(r["again_cnt"] or 0)}


def insights_battery_age(oem_ids=None, args=None):
    """电池使用时长分布（按创建时间粗略分龄；支持代理商/品牌筛选）"""
    w = "b.is_del=0"
    if oem_ids:
        w += _oem_where(oem_ids, "b")
    flt = _flt(args, BATTERY_COLUMNS)
    if flt:
        w += flt.and_clause()
    now = _now_ms()
    rows = db.query(
        f"SELECT CASE "
        f"WHEN b.create_time>{now - 180 * DAY_MS} THEN '6个月内' "
        f"WHEN b.create_time>{now - 365 * DAY_MS} THEN '6-12个月' "
        f"WHEN b.create_time>{now - 730 * DAY_MS} THEN '1-2年' "
        f"ELSE '2年以上' END age_range, COUNT(*) c "
        f"FROM t_battery b WHERE {w} GROUP BY age_range")
    return [{"age_range": r["age_range"], "count": int(r["c"])} for r in rows]


def insights_expense_compare(oem_ids=None, months=6, args=None):
    """近 N 月收入支出对比（支持订单/支出维度筛选）"""
    return finance_income_trend(oem_ids, months, args)
