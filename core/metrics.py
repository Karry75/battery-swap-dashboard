# -*- coding: utf-8 -*-
"""看板统计聚合：总览 / 按客户 / 告警分类"""
from collections import defaultdict
from core import db
from core.customers import get_customer_map, get_customers
from core.battery_alarms import battery_alarms
from core.cabinet_alarms import exchange_alarms
import config.settings as settings

T = settings.get("database.tables", {})
BATTERY = T.get("battery", "cb_battery")
EXCHANGE = T.get("exchange", "cb_exchange")

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


def device_totals(oem_ids=None, args=None):
    """设备总量与在线/离线（电池支持代理商/品牌；换电柜支持城市/网点/代理商/品牌）"""
    bq = f"SELECT COUNT(*) total, SUM(b.online_status='online') online, SUM(b.online_status='offline') offline " \
         f"FROM {BATTERY} b WHERE b.is_del=0{_oem_filter(oem_ids, 'b')}"
    eq = f"SELECT COUNT(*) total, SUM(e.online_status='online') online, SUM(e.online_status='offline') offline " \
         f"FROM {EXCHANGE} e LEFT JOIN cb_site s ON s.id=e.site_id AND s.is_del=0 " \
         f"WHERE e.is_del=0{_oem_filter(oem_ids, 'e')}"
    if args:
        from core.filters import FilterSet, BATTERY_COLUMNS, EXCHANGE_COLUMNS
        bt_f = FilterSet(args, BATTERY_COLUMNS)
        if bt_f.has:
            bq += bt_f.and_clause()
        ex_f = FilterSet(args, EXCHANGE_COLUMNS)
        if ex_f.has:
            eq += ex_f.and_clause()
    b = db.query(bq)[0]
    e = db.query(eq)[0]
    return {
        "battery": {"total": int(b["total"] or 0), "online": int(b["online"] or 0), "offline": int(b["offline"] or 0)},
        "exchange": {"total": int(e["total"] or 0), "online": int(e["online"] or 0), "offline": int(e["offline"] or 0)},
    }


def alarm_summary(oem_ids=None):
    """告警分类计数"""
    batt = defaultdict(int)
    for a in battery_alarms(oem_ids):
        batt[a["alarm_type"]] += 1
    exch = defaultdict(int)
    for a in exchange_alarms(oem_ids):
        exch[a["alarm_type"]] += 1
    return {
        "battery": {
            "hungry": batt.get("hungry", 0),
            "unrecognized": batt.get("unrecognized", 0),
            "break_charge": batt.get("break_charge", 0),
            "total": sum(batt.values()),
        },
        "exchange": {
            "smoke": exch.get("smoke", 0),
            "flooded": exch.get("flooded", 0),
            "slot": exch.get("slot", 0),
            "total": sum(exch.values()),
        },
    }


def summary(oem_ids=None, args=None):
    """看板总览（设备量支持设备维度筛选；告警/客户为全量）"""
    totals = device_totals(oem_ids, args)
    alarms = alarm_summary(oem_ids)
    customers = get_customers()
    return {
        "customers": {"total": len(customers), "enabled": len([c for c in customers if c.get("status") == "on"])},
        "device": totals,
        "alarm": alarms,
    }


def customer_stats(oem_ids=None):
    """按客户统计：设备数量/在线离线/告警数"""
    cmap = _customers()
    stat = defaultdict(lambda: {
        "battery": {"total": 0, "online": 0, "offline": 0},
        "exchange": {"total": 0, "online": 0, "offline": 0},
        "battery_alarm": 0,
        "exchange_alarm": 0,
    })

    for r in db.query(
        f"SELECT oem_id, COUNT(*) total, SUM(online_status='online') online, SUM(online_status='offline') offline "
        f"FROM {BATTERY} WHERE is_del=0{_oem_filter(oem_ids)} GROUP BY oem_id"
    ):
        s = stat[r["oem_id"]]
        s["battery"]["total"] = int(r["total"] or 0)
        s["battery"]["online"] = int(r["online"] or 0)
        s["battery"]["offline"] = int(r["offline"] or 0)

    for r in db.query(
        f"SELECT oem_id, COUNT(*) total, SUM(online_status='online') online, SUM(online_status='offline') offline "
        f"FROM {EXCHANGE} WHERE is_del=0{_oem_filter(oem_ids)} GROUP BY oem_id"
    ):
        s = stat[r["oem_id"]]
        s["exchange"]["total"] = int(r["total"] or 0)
        s["exchange"]["online"] = int(r["online"] or 0)
        s["exchange"]["offline"] = int(r["offline"] or 0)

    for a in battery_alarms(oem_ids):
        stat[a["customer_id"]]["battery_alarm"] += 1
    for a in exchange_alarms(oem_ids):
        stat[a["customer_id"]]["exchange_alarm"] += 1

    rows = []
    for oid, s in stat.items():
        rows.append({
            "customer_id": oid,
            "customer_name": cmap.get(str(oid), "未分配客户" if oid in (0, "0", None) else f"客户#{oid}"),
            **s,
        })
    rows.sort(key=lambda x: x["customer_name"])
    return rows
