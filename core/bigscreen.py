# -*- coding: utf-8 -*-
"""数据大屏模块：按城市维度聚合的真实数据接口

数据源全部来自实时主表（t_exchange_order / t_user / t_site / t_exchange /
t_battery / t_device_type），城市归一化规则与 core/overview 保持一致
（_city_core 去掉省市自治区后缀后做包含匹配）。
"""
import time
from core import db
from core.cn_labels import BATTERY_STATUS_CN, UNKNOWN_CN
from core.overview import DAY_MS, _now_ms, _today_start_ms, _city_core
from core.filters import FilterSet, USER_COLUMNS, ORDER_COLUMNS, EXCHANGE_COLUMNS, BATTERY_COLUMNS

T = db  # 兼容命名


import re

_PROVINCE_PREFIX = re.compile(
    r"^(北京市|上海市|天津市|重庆市|河北省|山西省|辽宁省|吉林省|黑龙江省|江苏省|浙江省|安徽省|福建省|"
    r"江西省|山东省|河南省|湖北省|湖南省|广东省|海南省|四川省|贵州省|云南省|陕西省|甘肃省|青海省|台湾省|"
    r"内蒙古自治区|广西壮族自治区|西藏自治区|宁夏回族自治区|新疆维吾尔自治区|香港特别行政区|澳门特别行政区)")


def _flt(args, columns):
    """按统一筛选参数构造 FilterSet；空筛选返回 None"""
    if not args:
        return None
    fs = FilterSet(args, columns)
    return fs if fs.has else None


def _city_like(city):
    """城市名归一化为 LIKE 模式；空/未知返回 None 表示不做城市过滤

    先剥离省份/直辖市前缀（广东省深圳市 -> 深圳市），再按 core/overview
    的 _city_core 规则去省市后缀做包含匹配，兼容两种入库口径。
    """
    if not city:
        return None
    city = _PROVINCE_PREFIX.sub("", str(city)).strip()
    core = _city_core(city)
    if not core or core == "未知":
        return None
    return "%" + core + "%"


def _oem_where(oem_ids, alias):
    if not oem_ids:
        return ""
    return f" AND {alias}.oem_id IN ({','.join(map(str, oem_ids))})"


def cities(oem_ids=None, args=None):
    """城市列表：按订单量排序取 Top 15（订单 t_city_name 为主，补充用户城市）"""
    ow = "o.is_del=0"
    if oem_ids:
        ow += f" AND o.oem_id IN ({','.join(map(str, oem_ids))})"
    of = _flt(args, ORDER_COLUMNS)
    if of:
        ow += of.and_clause()
    rows = db.query(
        f"SELECT COALESCE(NULLIF(o.t_city_name,''),'') city, COUNT(*) cnt, "
        f"COUNT(DISTINCT o.take_user_id) users "
        f"FROM t_exchange_order o WHERE {ow} GROUP BY city ORDER BY cnt DESC LIMIT 50")
    uw = "u.is_del=0"
    if oem_ids:
        uw += f" AND u.oem_id IN ({','.join(map(str, oem_ids))})"
    uf = _flt(args, USER_COLUMNS)
    if uf:
        uw += uf.and_clause()
    urows = db.query(f"SELECT COALESCE(NULLIF(u.city,''),'') city, COUNT(*) c FROM t_user u WHERE {uw} GROUP BY city")
    umap = {_city_core(r["city"]): int(r["c"]) for r in urows if r["city"]}

    out = []
    seen = set()
    for r in rows:
        city = r["city"] or "未知城市"
        key = _city_core(city)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "city": city,
            "core": key,
            "orders": int(r["cnt"] or 0),
            "users": int(r["users"] or 0) + umap.get(key, 0),
        })
    # 补充只有用户没有订单的城市
    for city, c in umap.items():
        if city and city not in seen and city != "未知":
            seen.add(city)
            out.append({"city": city, "core": city, "orders": 0, "users": c})
    out.sort(key=lambda x: -x["orders"])
    return out[:15]


def summary(oem_ids=None, city=None, args=None):
    """城市大屏核心指标：用户 / 柜 / 电池 / 今日换电 / 今日收入 / 本月收入与目标完成度"""
    ulike = _city_like(city)
    uw = "u.is_del=0" + _oem_where(oem_ids, "u")
    ow = "o.is_del=0" + _oem_where(oem_ids, "o")
    if ulike:
        uw += " AND u.city LIKE %s"
        ow += " AND o.t_city_name LIKE %s"
    uf = _flt(args, USER_COLUMNS)
    if uf:
        uw += uf.and_clause()
    of = _flt(args, ORDER_COLUMNS)
    if of:
        ow += of.and_clause()

    today = _today_start_ms()
    now = _now_ms()
    pu = (ulike,) if ulike else ()
    po = (ulike,) if ulike else ()

    # 用户：累计 / 今日新增
    u = db.query(f"SELECT COUNT(*) c FROM t_user u WHERE {uw}", pu)[0]
    nu = db.query(f"SELECT COUNT(*) c FROM t_user u WHERE {uw} AND u.create_time>{today} AND u.create_time<={now}", pu)[0]

    # 今日换电：单量 / 收入 / 活跃用户
    t = db.query(
        f"SELECT COUNT(*) cnt, COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee, "
        f"COUNT(DISTINCT o.take_user_id) users "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{today} AND o.create_time<={now}", po)[0]

    # 本月收入 / 近12个月月均收入（不含本月）作为月度目标基准
    lt = time.localtime()
    month_start = int(time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0, 0, 0, -1)) * 1000)
    mi = db.query(
        f"SELECT COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{month_start} AND o.create_time<={now}", po)[0]
    hist_start = month_start - 11 * 30 * DAY_MS
    hi = db.query(
        f"SELECT COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{hist_start} AND o.create_time<{month_start}", po)[0]
    month_target = round(float(hi["fee"] or 0) / 11.0, 2)
    month_income = round(float(mi["fee"] or 0), 2)
    target_rate = round(month_income / month_target * 100, 1) if month_target > 0 else 0

    # 换电柜：总数 / 在线 / 离线（site.city 或最后位置地址匹配）
    exw = "e.is_del=0" + _oem_where(oem_ids, "e")
    exf = _flt(args, EXCHANGE_COLUMNS)
    if exf:
        exw += exf.and_clause()
    exp = ()
    if ulike:
        exw += " AND (s.city LIKE %s OR e.last_location_address LIKE %s)"
        exp = (ulike, ulike)
    ex = db.query(
        f"SELECT COUNT(*) total, "
        f"SUM(CASE WHEN e.online_status='online' THEN 1 ELSE 0 END) onn, "
        f"SUM(CASE WHEN e.online_status='offline' THEN 1 ELSE 0 END) offn "
        f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 WHERE {exw}", exp)[0]

    # 电池总数（最后位置地址匹配）
    btw = "b.is_del=0" + _oem_where(oem_ids, "b")
    btf = _flt(args, BATTERY_COLUMNS)
    if btf:
        btw += btf.and_clause()
    btp = ()
    if ulike:
        btw += " AND b.last_location_address LIKE %s"
        btp = (ulike,)
    bt = db.query(f"SELECT COUNT(*) c FROM t_battery b WHERE {btw}", btp)[0]

    return {
        "city": city or "全部城市",
        "total_users": int(u["c"] or 0),
        "today_new_users": int(nu["c"] or 0),
        "today_exchange": int(t["cnt"] or 0),
        "today_fee": round(float(t["fee"] or 0), 2),
        "today_users": int(t["users"] or 0),
        "month_income": month_income,
        "month_target": month_target,
        "month_target_rate": target_rate,
        "exchanges": {
            "total": int(ex["total"] or 0),
            "online": int(ex["onn"] or 0),
            "offline": int(ex["offn"] or 0),
        },
        "battery_total": int(bt["c"] or 0),
    }


def regions(oem_ids=None, city=None, args=None):
    """区域分布（区级）：用户数 / 换电柜数 / 今日换电单量 / 今日收入"""
    ulike = _city_like(city)
    today = _today_start_ms()
    now = _now_ms()

    uw = "u.is_del=0" + _oem_where(oem_ids, "u")
    up = ()
    if ulike:
        uw += " AND u.city LIKE %s"
        up = (ulike,)
    uf = _flt(args, USER_COLUMNS)
    if uf:
        uw += uf.and_clause()
    urows = db.query(
        f"SELECT COALESCE(NULLIF(u.area,''),'未知') area, COUNT(*) c "
        f"FROM t_user u WHERE {uw} AND u.area<>'' GROUP BY area ORDER BY c DESC LIMIT 30", up)
    umap = {r["area"]: int(r["c"] or 0) for r in urows}

    exw = "e.is_del=0" + _oem_where(oem_ids, "e")
    exp = ()
    if ulike:
        exw += " AND (s.city LIKE %s OR e.last_location_address LIKE %s)"
        exp = (ulike, ulike)
    exf = _flt(args, {"city": "s.city", "area": "s.area", "agency_id": "e.agency_id",
                      "site_id": "e.site_id", "brand_id": "e.brand_id", "device_sn": "e.device_sn"})
    if exf:
        exw += exf.and_clause()
    exrows = db.query(
        f"SELECT COALESCE(NULLIF(s.area,''),'未知') area, COUNT(*) c "
        f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
        f"WHERE {exw} AND s.area<>'' GROUP BY area ORDER BY c DESC LIMIT 30", exp)
    exmap = {r["area"]: int(r["c"] or 0) for r in exrows}

    # 今日单量 / 收入：订单 join 用户取区（今日时间窗已收窄，性能可控）
    ow = "o.is_del=0 AND u.is_del=0" + _oem_where(oem_ids, "o")
    op = ()
    if ulike:
        ow += " AND u.city LIKE %s"
        op = (ulike,)
    of = _flt(args, {"city": "u.city", "area": "u.area", "time": "o.create_time",
                     "agency_id": "o.agency_id", "battery_product_id": "o.battery_product_id",
                     "user_phone": "o.take_user_phone", "device_sn": "o.bike_sn"})
    if of:
        ow += of.and_clause()
    orows = db.query(
        f"SELECT COALESCE(NULLIF(u.area,''),'未知') area, COUNT(*) cnt, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o JOIN t_user u ON o.take_user_id=u.id "
        f"WHERE {ow} AND o.create_time>{today} AND o.create_time<={now} "
        f"GROUP BY area ORDER BY cnt DESC LIMIT 30", op)

    areas = sorted(set(list(umap.keys()) + list(exmap.keys()) + [r["area"] for r in orows]))
    out = []
    for area in areas:
        o = next((r for r in orows if r["area"] == area), None)
        out.append({
            "area": area,
            "users": umap.get(area, 0),
            "exchanges": exmap.get(area, 0),
            "orders_today": int((o or {}).get("cnt") or 0),
            "income_today": round(float((o or {}).get("fee") or 0), 2),
        })
    out.sort(key=lambda x: -(x["orders_today"] + x["users"]))
    return out[:15]


def dist(oem_ids=None, city=None, args=None):
    """网点类型分布（柜 device_type）+ 电池状态分布 + 柜在线状态分布"""
    ulike = _city_like(city)

    exw = "e.is_del=0" + _oem_where(oem_ids, "e")
    exp = ()
    if ulike:
        exw += " AND (s.city LIKE %s OR e.last_location_address LIKE %s)"
        exp = (ulike, ulike)
    exf = _flt(args, {"city": "s.city", "area": "s.area", "agency_id": "e.agency_id",
                      "site_id": "e.site_id", "brand_id": "e.brand_id", "device_sn": "e.device_sn"})
    if exf:
        exw += exf.and_clause()
    types = db.query(
        f"SELECT e.device_type_id tid, COUNT(*) c, "
        f"COALESCE(NULLIF(d.device_product_model_name,''), d.device_product_name, '未知类型') name "
        f"FROM t_exchange e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
        f"LEFT JOIN t_device_type d ON d.id=e.device_type_id "
        f"WHERE {exw} GROUP BY e.device_type_id, name ORDER BY c DESC LIMIT 10", exp)

    btw = "b.is_del=0" + _oem_where(oem_ids, "b")
    btp = ()
    if ulike:
        btw += " AND b.last_location_address LIKE %s"
        btp = (ulike,)
    btf = _flt(args, BATTERY_COLUMNS)
    if btf:
        btw += btf.and_clause()
    bstatus = db.query(
        f"SELECT COALESCE(NULLIF(b.battery_status,''),'unknown') st, COUNT(*) c "
        f"FROM t_battery b WHERE {btw} GROUP BY st ORDER BY c DESC", btp)

    return {
        "exchange_types": [{"name": r["name"], "count": int(r["c"] or 0)} for r in types],
        "battery_status": [{"key": r["st"],
                            "name": BATTERY_STATUS_CN.get(r["st"], UNKNOWN_CN if r["st"] == "unknown" else r["st"]),
                            "count": int(r["c"] or 0)} for r in bstatus],
    }


def trend(oem_ids=None, city=None, months=12, args=None):
    """近 N 月趋势：换电单量 / 收入 / 活跃用户（按城市过滤 + 统一维度筛选）"""
    ow = "o.is_del=0" + _oem_where(oem_ids, "o")
    params = ()
    if _city_like(city):
        ow += " AND o.t_city_name LIKE %s"
        params = (_city_like(city),)
    of = _flt(args, ORDER_COLUMNS)
    if of:
        ow += of.and_clause()
    start = _now_ms() - months * 30 * DAY_MS
    rows = db.query(
        f"SELECT DATE_FORMAT(FROM_UNIXTIME(o.create_time/1000), '%%Y-%%m') ym, "
        f"COUNT(*) cnt, COUNT(DISTINCT o.take_user_id) users, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{start} "
        f"GROUP BY ym ORDER BY ym", params)
    return [{
        "month": r["ym"],
        "exchange_count": int(r["cnt"] or 0),
        "active_users": int(r["users"] or 0),
        "fee": round(float(r["fee"] or 0), 2),
    } for r in rows]


def top_cities(oem_ids=None, days=30, args=None):
    """换电城市排行榜 Top 5（近 N 天；支持统一维度筛选）"""
    ow = "o.is_del=0" + _oem_where(oem_ids, "o")
    of = _flt(args, ORDER_COLUMNS)
    if of:
        ow += of.and_clause()
    start = _now_ms() - days * DAY_MS
    rows = db.query(
        f"SELECT COALESCE(NULLIF(o.t_city_name,''),'未知城市') city, COUNT(*) cnt, "
        f"COUNT(DISTINCT o.take_user_id) users, "
        f"COALESCE(SUM(o.real_pay_price),0)+COALESCE(SUM(o.expend_power_fee),0) fee "
        f"FROM t_exchange_order o WHERE {ow} AND o.create_time>{start} "
        f"GROUP BY city ORDER BY cnt DESC LIMIT 5")
    return [{
        "city": r["city"],
        "orders": int(r["cnt"] or 0),
        "users": int(r["users"] or 0),
        "fee": round(float(r["fee"] or 0), 2),
    } for r in rows]
