# -*- coding: utf-8 -*-
"""数据总览模块：运营总览 / 月度趋势 / 区域维度 / 城市维度 / 设备维度 / 财务维度

数据源全部来自实时主表（t_exchange_order / t_user / t_site / t_bike /
t_battery / t_exchange / t_expense_bill），不使用停更的统计表。
"""
import time
from core import db
from core.customers import get_customer_map
from core.filters import FilterSet, USER_COLUMNS, ORDER_COLUMNS, SITE_COLUMNS, \
    EXCHANGE_COLUMNS, BATTERY_COLUMNS, EXPENSE_COLUMNS

T = db  # 兼容命名

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
    """按 oem 范围构造过滤片段（与 business/finance_assets 保持一致）"""
    if not oem_ids:
        return ""
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}oem_id IN ({','.join(map(str, oem_ids))})"


def _today_start_ms():
    lt = time.localtime()
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def _attach_customer(items):
    cmap = _customers()
    for it in items:
        oid = it.get("oem_id")
        it["customer_name"] = cmap.get(str(oid), "未分配客户" if oid in (0, "0", None) else f"客户#{oid}")
    return items


# ---------- 运营总览 ----------
def summary(oem_ids=None, args=None):
    """运营总览 KPI：今日换电 / 收入 / 活跃 / 累计设备用户（支持订单/用户维度筛选）"""
    where = "o.is_del=0"
    w2 = "u.is_del=0"
    if oem_ids:
        where += f" AND o.oem_id IN ({','.join(map(str, oem_ids))})"
        w2 += f" AND u.oem_id IN ({','.join(map(str, oem_ids))})"
    of = _flt(args, ORDER_COLUMNS)
    if of:
        where += of.and_clause()
    uf = _flt(args, USER_COLUMNS)
    if uf:
        w2 += uf.and_clause()
    today = _today_start_ms()
    today_ms = _now_ms()

    # 今日换电
    t = db.query(
        f"SELECT COUNT(*) cnt, COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, "
        f"COUNT(DISTINCT o.take_user_id) users "
        f"FROM t_exchange_order o WHERE {where} AND o.create_time>{today} AND o.create_time<={today_ms}")[0]
    # 昨日换电
    y = db.query(
        f"SELECT COUNT(*) cnt FROM t_exchange_order o "
        f"WHERE {where} AND o.create_time>{today - DAY_MS} AND o.create_time<={today}")[0]
    # 用户累计
    u = db.query(f"SELECT COUNT(*) cnt FROM t_user u WHERE {w2}")[0]
    # 设备（换电柜/电池/站点均支持设备维度筛选；车辆无映射表保持全量）
    ef = _flt(args, EXCHANGE_COLUMNS)
    bf = _flt(args, BATTERY_COLUMNS)
    sf = _flt(args, SITE_COLUMNS)
    ew = "e.is_del=0" + ((" AND " + ef.and_clause()) if ef else "")
    bw = "b.is_del=0" + ((" AND " + bf.and_clause()) if bf else "")
    sw = "s.is_del=0" + ((" AND " + sf.and_clause()) if sf else "")
    ej = " LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 " if (ef and "s." in ef.and_clause()) else ""
    dev = db.query(
        "SELECT "
        f"(SELECT COUNT(*) FROM t_exchange e {ej} WHERE {ew}) ex, "
        f"(SELECT COUNT(*) FROM t_exchange e {ej} WHERE {ew} AND e.online_status='online') ex_on, "
        f"(SELECT COUNT(*) FROM t_battery b WHERE {bw}) bt, "
        f"(SELECT COUNT(*) FROM t_battery b WHERE {bw} AND b.online_status='online') bt_on, "
        f"(SELECT COUNT(*) FROM t_bike WHERE is_del=0) bk, "
        f"(SELECT COUNT(*) FROM t_site s WHERE {sw}) st")[0]

    # 今日新增用户
    nu = db.query(f"SELECT COUNT(*) c FROM t_user u WHERE {w2} AND u.create_time>{today} AND u.create_time<={today_ms}")[0]
    # 活跃用户（今日有换电）
    return {
        "today_exchange": int(t["cnt"] or 0),
        "today_fee": round(float(t["fee"] or 0), 2),
        "today_users": int(t["users"] or 0),
        "yesterday_exchange": int(y["cnt"] or 0),
        "total_users": int(u["cnt"] or 0),
        "today_new_users": int(nu["c"] or 0),
        "devices": {
            "exchange_total": int(dev["ex"] or 0), "exchange_online": int(dev["ex_on"] or 0),
            "battery_total": int(dev["bt"] or 0), "battery_online": int(dev["bt_on"] or 0),
            "bike_total": int(dev["bk"] or 0), "site_total": int(dev["st"] or 0),
        },
    }


def monthly_trend(oem_ids=None, months=24, args=None):
    """近 N 月月度趋势：换电次数 / 活跃用户 / 换电收入（实时聚合；支持订单维度筛选）"""
    where = "o.is_del=0"
    if oem_ids:
        where += f" AND o.oem_id IN ({','.join(map(str, oem_ids))})"
    of = _flt(args, ORDER_COLUMNS)
    if of:
        where += of.and_clause()
    start = _now_ms() - months * 30 * DAY_MS
    rows = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(o.create_time/1000), '%%Y-%%m') ym, "
        f"COUNT(*) cnt, COUNT(DISTINCT o.take_user_id) users, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {where} AND o.create_time>{start} "
        f"GROUP BY ym ORDER BY ym")
    # 收入口径：分成收入取 profit_fee（毛利）
    rows2 = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(o.create_time/1000), '%%Y-%%m') ym, "
        f"COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {where} AND o.create_time>{start} AND o.profit_fee>0 "
        f"GROUP BY ym ORDER BY ym")
    profit_map = {r["ym"]: round(float(r["profit"]), 2) for r in rows2}
    out = []
    for r in rows:
        out.append({
            "month": r["ym"],
            "exchange_count": int(r["cnt"] or 0),
            "active_users": int(r["users"] or 0),
            "fee": round(float(r["fee"] or 0), 2),
            "profit_fee": profit_map.get(r["ym"], 0),
        })
    return out


def city_dimension(oem_ids=None, days=30, args=None):
    """城市维度：按 t_city_name 聚合（近 N 天换电 + 累计用户/设备；支持订单维度筛选）"""
    where = "o.is_del=0"
    if oem_ids:
        where += f" AND o.oem_id IN ({','.join(map(str, oem_ids))})"
    of = _flt(args, ORDER_COLUMNS)
    if of:
        where += of.and_clause()
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT COALESCE(NULLIF(o.t_city_name,''),'未知城市') city, "
        f"COUNT(*) cnt, COUNT(DISTINCT o.take_user_id) users, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {where} AND o.create_time>{start} "
        f"GROUP BY city ORDER BY cnt DESC LIMIT 50")
    # 设备按城市（换电柜最后位置地址粗分，仅取前20）
    return [{
        "city": r["city"],
        "exchange_count": int(r["cnt"] or 0),
        "active_users": int(r["users"] or 0),
        "fee": round(float(r["fee"] or 0), 2),
        "profit_fee": round(float(r["profit"] or 0), 2),
    } for r in rows]


def _city_core(c):
    """提取城市核心名：去掉省/市/自治区等行政区划后缀，用于跨来源城市名归一"""
    c = (c or "").strip()
    if not c or c in ("未知", "未知城市", "<空>"):
        return "未知"
    for suf in ("特别行政区", "自治区", "壮族", "回族", "维吾尔", "省", "市"):
        c = c.replace(suf, "")
    return c or "未知"


def _city_match(cm, order_core):
    """精确或包含匹配：order 城市 core 与用户/柜子城市 core 对齐"""
    if order_core in cm:
        return cm[order_core]
    for k, v in cm.items():
        if order_core in k or k in order_core:
            return v
    return 0


def regions(oem_ids=None, days=30, args=None):
    """区域总览表：城市 / 用户数 / 换电柜数 / 电池数 / 30天换电次数 / 30天骑行距离（支持多维度筛选）"""
    # 用户按 city 字段（t_user.city 是城市名，部分为空）
    uw = "u.is_del=0"
    if oem_ids:
        uw += f" AND u.oem_id IN ({','.join(map(str, oem_ids))})"
    uf = _flt(args, USER_COLUMNS)
    if uf:
        uw += uf.and_clause()
    urows = db.query(f"SELECT COALESCE(NULLIF(u.city,''),'未知') city, COUNT(*) c FROM t_user u WHERE {uw} GROUP BY city")
    umap = {_city_core(r["city"]): int(r["c"]) for r in urows}

    # 换电柜按网点城市分组（t_exchange.site_id -> t_site.city；无网点柜子归未知）
    exw = "e.is_del=0"
    if oem_ids:
        exw += f" AND e.oem_id IN ({','.join(map(str, oem_ids))})"
    exf = _flt(args, {"city": "s.city", "area": "s.area", "street": "s.street",
                      "community": "s.community", "agency_id": "e.agency_id",
                      "site_id": "e.site_id", "brand_id": "e.brand_id", "device_sn": "e.device_sn"})
    if exf:
        exw += exf.and_clause()
    exrows = db.query(
        f"SELECT COALESCE(NULLIF(s.city,''),'未知') city, COUNT(*) c "
        f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 WHERE {exw} GROUP BY city")
    exmap = {_city_core(r["city"]): int(r["c"]) for r in exrows}

    # 30天换电 + 骑行距离 按城市
    ow = "o.is_del=0"
    if oem_ids:
        ow += f" AND o.oem_id IN ({','.join(map(str, oem_ids))})"
    of = _flt(args, ORDER_COLUMNS)
    if of:
        ow += of.and_clause()
    start = _now_ms() - days * DAY_MS
    orows = db.query(
        f"SELECT COALESCE(NULLIF(o.t_city_name,''),'未知城市') city, COUNT(*) cnt, "
        f"COALESCE(SUM(o.mileage),0) mileage, COUNT(DISTINCT o.take_user_id) users "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{start} GROUP BY city")

    out = []
    for r in orows:
        c = r["city"]
        key = _city_core(c)
        out.append({
            "city": c,
            "users": _city_match(umap, key),
            "exchange_count": _city_match(exmap, key),
            "exchange_30d": int(r["cnt"] or 0),
            "active_users_30d": int(r["users"] or 0),
            "mileage_30d": round(float(r["mileage"] or 0), 1),
        })
    out.sort(key=lambda x: -x["exchange_30d"])
    return out


def device_dimension(oem_ids=None, args=None):
    """设备维度总览：换电柜 / 电池 / 车辆 / 网点 状态分布（换电柜支持城市/网点/代理商/品牌筛选；
    电池支持代理商/品牌；车辆数为全量）"""
    ex_sub = (f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
              f"WHERE e.is_del=0{_oem_where(oem_ids, 'e')}")
    exf = _flt(args, EXCHANGE_COLUMNS)
    if exf:
        ex_sub += exf.and_clause()
    bt_w = f"is_del=0{_oem_where(oem_ids)}"
    btf = _flt(args, BATTERY_COLUMNS)
    if btf:
        bt_w += btf.and_clause()
    ex = db.query(
        f"SELECT COUNT(*) total, SUM(e.online_status='online') online, SUM(e.online_status='offline') offline "
        f"{ex_sub}")[0]
    bt = db.query(
        f"SELECT COUNT(*) total, SUM(b.online_status='online') online, SUM(b.online_status='offline') offline "
        f"FROM t_battery b WHERE {bt_w}")[0]
    rows = db.query(
        "SELECT "
        "(SELECT COUNT(*) FROM t_bike WHERE is_del=0) bk_total, "
        "(SELECT COUNT(*) FROM t_bike WHERE is_del=0 AND online_status='online') bk_on, "
        "(SELECT COUNT(*) FROM t_bike WHERE is_del=0 AND online_status='offline') bk_off, "
        "(SELECT COUNT(*) FROM t_site WHERE is_del=0) st_total, "
        "(SELECT COUNT(*) FROM t_site WHERE is_del=0 AND site_status='on') st_open, "
        "(SELECT COUNT(*) FROM t_site WHERE is_del=0 AND site_status='off') st_closed")[0]
    return {
        "exchange": {"total": int(ex["total"] or 0), "online": int(ex["online"] or 0), "offline": int(ex["offline"] or 0)},
        "battery": {"total": int(bt["total"] or 0), "online": int(bt["online"] or 0), "offline": int(bt["offline"] or 0)},
        "bike": {"total": int(rows["bk_total"] or 0), "online": int(rows["bk_on"] or 0), "offline": int(rows["bk_off"] or 0)},
        "site": {"total": int(rows["st_total"] or 0), "open": int(rows["st_open"] or 0), "closed": int(rows["st_closed"] or 0)},
    }


def finance_dimension(oem_ids=None, months=12, args=None):
    """财务维度：近 N 月收入 / 支出 / 毛利（订单收入 + 费用单支出；支持订单/支出维度筛选）"""
    iw = "o.is_del=0"
    if oem_ids:
        iw += _oem_where(oem_ids, "o")
    of = _flt(args, ORDER_COLUMNS)
    if of:
        iw += of.and_clause()
    ew = "b.is_del=0 AND b.is_cancel=0"
    if oem_ids:
        ew += _oem_where(oem_ids, "b")
    ef = _flt(args, EXPENSE_COLUMNS)
    if ef:
        ew += ef.and_clause()
    start = _now_ms() - months * 30 * DAY_MS
    income = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(o.create_time/1000), '%%Y-%%m') ym, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, COALESCE(SUM(o.profit_fee),0) profit "
        f"FROM t_exchange_order o WHERE {iw} AND o.create_time>{start} GROUP BY ym ORDER BY ym")
    expense = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(b.create_time/1000), '%%Y-%%m') ym, "
        f"COALESCE(SUM(b.fee),0) fee, COUNT(*) cnt "
        f"FROM t_expense_bill b WHERE {ew} AND b.create_time>{start} GROUP BY ym ORDER BY ym")
    emap = {r["ym"]: r for r in expense}
    out = []
    for r in income:
        e = emap.get(r["ym"], {})
        out.append({
            "month": r["ym"],
            "income": round(float(r["fee"] or 0), 2),
            "profit": round(float(r["profit"] or 0), 2),
            "expense": round(float(e.get("fee") or 0), 2),
            "expense_count": int(e.get("cnt") or 0),
        })
    return out
