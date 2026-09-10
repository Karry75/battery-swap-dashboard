# -*- coding: utf-8 -*-
"""设备列表查询：换电柜管理 / 电池管理（分页 + 筛选 + 统计）

数据源：
- t_exchange（换电柜主表：在线状态/位置/上报时间）+ t_exchange_last_upload（名称/烟感/水浸/火警）+ t_exchange_last_store（仓位聚合）
- t_battery（电池主表：SN/状态/位置/所在柜）+ t_battery_last_upload（电量/电压/充电，每电池取最新一条）
"""
from core import db
from core.customers import get_customer_map
import config.settings as settings

T = settings.get("database.tables", {})
BATTERY = T.get("battery", "t_battery")
EXCHANGE = T.get("exchange", "t_exchange")
BATTERY_UPLOAD = T.get("battery_last_upload", "t_battery_last_upload")
EXCHANGE_UPLOAD = T.get("exchange_last_upload", "t_exchange_last_upload")
EXCHANGE_LAST_STORE = T.get("exchange_last_store", "t_exchange_last_store")

_customer_map = None


def _customers():
    global _customer_map
    if _customer_map is None:
        _customer_map = get_customer_map()
    return _customer_map


def _oem_filter(oem_ids, alias=""):
    if not oem_ids:
        return ""
    prefix = f"{alias}." if alias else ""
    ids = ",".join(str(int(i)) for i in oem_ids)
    return f" AND {prefix}oem_id IN ({ids})"


def _page_args(args):
    page = max(1, int(args.get("page", 1)))
    page_size = min(200, max(1, int(args.get("page_size", 50))))
    return page, page_size


def _keyword_like(kw):
    # pymysql 会把 % 当格式化占位符，SQL 字面量中需用 %% 转义
    return f"%{kw}%".replace("%", "%%")


def _attach_customer(items):
    cmap = _customers()
    for it in items:
        oid = it.get("oem_id")
        it["customer_name"] = cmap.get(str(oid), "未分配客户" if oid in (0, "0", None) else f"客户#{oid}")
    return items


# ---------- 换电柜 ----------
def exchange_list(oem_ids=None, status="", keyword="", page=1, page_size=50, args=None):
    """换电柜管理列表 + 统计（支持城市/区域/网点/代理商/品牌/SN 等维度筛选）"""
    from core.filters import FilterSet, EXCHANGE_COLUMNS
    joins = " LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
    where = f"e.is_del=0{_oem_filter(oem_ids, 'e')}"
    if status in ("online", "offline"):
        where += f" AND e.online_status='{status}'"
    if keyword:
        kw = _keyword_like(keyword)
        where += f" AND (e.device_sn LIKE '{kw}' OR u.device_name LIKE '{kw}' OR e.last_location_address LIKE '{kw}')"
    if args:
        fs = FilterSet(args, EXCHANGE_COLUMNS)
        if fs.has:
            where += fs.and_clause()

    # 统计（同筛选）
    stats = db.query(
        f"SELECT COUNT(*) total, SUM(e.online_status='online') online, SUM(e.online_status='offline') offline "
        f"FROM {EXCHANGE} e LEFT JOIN {EXCHANGE_UPLOAD} u ON u.exchange_id=e.id AND u.is_del=0 "
        f"{joins} WHERE {where}"
    )[0]

    rows = db.query(
        f"SELECT e.id, e.oem_id, e.device_sn, e.online_status, e.last_location_address, "
        f"       e.site_placement, e.last_upload_time, "
        f"       u.device_name, u.smoke, u.flooded, u.fire, "
        f"       s.slot_total, s.slot_full, s.slot_charging, s.slot_empty "
        f"FROM {EXCHANGE} e "
        f"LEFT JOIN {EXCHANGE_UPLOAD} u ON u.exchange_id=e.id AND u.is_del=0 "
        f"LEFT JOIN (SELECT exchange_id, COUNT(*) slot_total, "
        f"            SUM(status='full') slot_full, SUM(status='charging') slot_charging, SUM(status='empty') slot_empty "
        f"           FROM {EXCHANGE_LAST_STORE} WHERE is_del=0 GROUP BY exchange_id) s ON s.exchange_id=e.id "
        f"{joins} WHERE {where} ORDER BY e.last_upload_time DESC LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    )
    _attach_customer(rows)
    for r in rows:
        for k in ("slot_total", "slot_full", "slot_charging", "slot_empty"):
            r[k] = int(r[k] or 0)
    total = int(stats["total"] or 0)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": {
            "total": total,
            "online": int(stats["online"] or 0),
            "offline": int(stats["offline"] or 0),
        },
        "items": rows,
    }


# ---------- 电池 ----------
def battery_list(oem_ids=None, status="", keyword="", power_min="", power_max="", page=1, page_size=50, args=None):
    """电池管理列表 + 统计（支持代理商/品牌/SN 等维度筛选）"""
    from core.filters import FilterSet, BATTERY_COLUMNS
    where = f"b.is_del=0{_oem_filter(oem_ids, 'b')}"
    if status in ("online", "offline"):
        where += f" AND b.online_status='{status}'"
    if keyword:
        kw = _keyword_like(keyword)
        where += (f" AND (b.device_sn LIKE '{kw}' OR b.last_upload_exchange_sn LIKE '{kw}' "
                  f"OR b.last_location_address LIKE '{kw}')")
    if power_min.isdigit():
        where += f" AND CAST(u.power AS SIGNED) >= {int(power_min)}"
    if power_max.isdigit():
        where += f" AND CAST(u.power AS SIGNED) <= {int(power_max)}"
    if args:
        fs = FilterSet(args, BATTERY_COLUMNS)
        if fs.has:
            where += fs.and_clause()

    latest = (f"SELECT battery_id, MAX(update_time) mt FROM {BATTERY_UPLOAD} "
              f"WHERE is_del=0 GROUP BY battery_id")
    upload = (f"SELECT u.battery_id, u.power, u.voltage, u.charging, u.update_time "
              f"FROM {BATTERY_UPLOAD} u JOIN ({latest}) m "
              f"ON u.battery_id=m.battery_id AND u.update_time=m.mt "
              f"WHERE u.is_del=0 "
              f"GROUP BY u.battery_id, u.power, u.voltage, u.charging, u.update_time")

    stats = db.query(
        f"SELECT COUNT(*) total, SUM(b.online_status='online') online, SUM(b.online_status='offline') offline "
        f"FROM {BATTERY} b LEFT JOIN ({upload}) u ON u.battery_id=b.id "
        f"WHERE {where}"
    )[0]

    rows = db.query(
        f"SELECT b.id, b.oem_id, b.device_sn, b.battery_status, b.online_status, b.type, "
        f"       b.last_upload_exchange_sn, b.last_location_address, b.supplier_name, "
        f"       b.last_battery_upload_time, "
        f"       u.power, u.voltage, u.charging, u.update_time AS upload_time "
        f"FROM {BATTERY} b "
        f"LEFT JOIN ({upload}) u ON u.battery_id=b.id "
        f"WHERE {where} ORDER BY b.last_battery_upload_time DESC LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    )
    _attach_customer(rows)
    total = int(stats["total"] or 0)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": {
            "total": total,
            "online": int(stats["online"] or 0),
            "offline": int(stats["offline"] or 0),
        },
        "items": rows,
    }
