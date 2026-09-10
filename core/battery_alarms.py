# -*- coding: utf-8 -*-
"""电池告警计算：饿死 / 无法识别 / 断充

- 饿死(hungry)：实时状态表计算——电量0%且电压低于阈值（默认40V）
- 无法识别(unrecognized)：监控事件'换电柜未识别电池'（电池未到位）
- 断充(break_charge)：监控事件'换电柜断充'（本身有电压但充电中断）
"""
from core import db
from core.customers import get_customer_map
from core.utils import ts_to_str, safe_float
import config.settings as settings

T = settings.get("database.tables", {})
BATTERY_LAST_UPLOAD = T.get("battery_last_upload", "t_battery_last_upload")
BATTERY = T.get("battery", "t_battery")
MONITOR_EVENT = T.get("monitor_event", "t_monitor_ex_event")
MONITOR_EVENT_BATTERY = T.get("monitor_event_battery", "t_monitor_ex_event_battery")

PRIORITY = settings.get("priority.battery", {})
HUNGRY_CFG = settings.get("alarm.battery.hungry", {})

_customer_map = None


def _customers():
    global _customer_map
    if _customer_map is None:
        _customer_map = get_customer_map()
    return _customer_map


def _oem_filter(oem_ids, alias="e"):
    """构造 oem 范围过滤；None/空 表示全部"""
    if not oem_ids:
        return ""
    ids = ",".join(str(int(i)) for i in oem_ids)
    return f" AND {alias}.oem_id IN ({ids})"


def hungry_alarms(oem_ids=None):
    """电池饿死：电量=0% 且 电压低于阈值（欠压）"""
    if not HUNGRY_CFG.get("enabled", True):
        return []
    th = HUNGRY_CFG.get("voltage_threshold", 40.0)
    pval = HUNGRY_CFG.get("power_value", "0")
    rows = db.query(
        f"""
        SELECT b.battery_id, b.battery_sn, b.power, b.voltage, b.charging, b.discharge,
               b.update_time, bt.battery_status, bt.online_status, bt.last_location_address,
               b.oem_id
        FROM {BATTERY_LAST_UPLOAD} b
        LEFT JOIN {BATTERY} bt ON bt.id = b.battery_id
        WHERE b.is_del=0 AND b.power=%s
          AND b.voltage REGEXP '^[0-9]+(\\.[0-9]+)?$'
          AND CAST(b.voltage AS DECIMAL(10,2)) < %s{_oem_filter(oem_ids, 'b')}
        ORDER BY CAST(b.voltage AS DECIMAL(10,2)) ASC
        """,
        (pval, th),
    )
    cmap = _customers()
    out = []
    for r in rows:
        v = safe_float(r.get("voltage"))
        charging = "充电中" if r.get("charging") == "on" else "未充电"
        out.append({
            "device_type": "battery",
            "device_id": r.get("battery_id"),
            "device_sn": r.get("battery_sn"),
            "customer_id": r.get("oem_id"),
            "customer_name": cmap.get(str(r.get("oem_id")), ""),
            "alarm_type": "hungry",
            "alarm_name": "电池饿死",
            "priority": PRIORITY.get("hungry", 1),
            "level": "high",
            "time": ts_to_str(r.get("update_time")),
            "desc": f"电量0% 电压{v}V（{charging}）",
            "source": "realtime",
            "extra": {
                "battery_status": r.get("battery_status"),
                "online_status": r.get("online_status"),
                "address": r.get("last_location_address"),
            },
        })
    return out


def _event_battery_alarms(names, alarm_type, alarm_name, priority, oem_ids=None):
    """通用：从监控事件表查询未解除电池类事件，join 电池事件明细"""
    placeholders = ",".join(["%s"] * len(names))
    rows = db.query(
        f"""
        SELECT e.id, e.oem_id, e.agency_name, e.level, e.create_time,
               eb.battery_id, eb.battery_sn, eb.exchange_sn, eb.site_name,
               eb.belong_name, eb.power, eb.address
        FROM {MONITOR_EVENT} e
        LEFT JOIN {MONITOR_EVENT_BATTERY} eb ON eb.ex_event_id = e.id
        WHERE e.is_del=0 AND e.status='init'
          AND e.name IN ({placeholders}){_oem_filter(oem_ids)}
        ORDER BY e.create_time DESC
        """,
        names,
    )
    cmap = _customers()
    out = []
    for r in rows:
        loc = r.get("site_name") or r.get("address") or r.get("belong_name") or ""
        out.append({
            "device_type": "battery",
            "event_id": r.get("id"),
            "device_id": r.get("battery_id"),
            "device_sn": r.get("battery_sn"),
            "customer_id": r.get("oem_id"),
            "customer_name": cmap.get(str(r.get("oem_id")), ""),
            "alarm_type": alarm_type,
            "alarm_name": alarm_name,
            "priority": priority,
            "level": r.get("level") or "normal",
            "time": ts_to_str(r.get("create_time")),
            "desc": f"电量{r.get('power')}% 位置:{loc or '未知'}",
            "source": "event",
            "extra": {"agency_name": r.get("agency_name"), "site_name": r.get("site_name"), "address": r.get("address")},
        })
    return out


def unrecognized_alarms(oem_ids=None):
    """电池无法识别（未到位）：监控事件'换电柜未识别电池'"""
    return _event_battery_alarms(
        ["换电柜未识别电池"],
        "unrecognized",
        "电池无法识别",
        PRIORITY.get("unrecognized", 1),
        oem_ids,
    )


def break_charge_alarms(oem_ids=None):
    """电池断充：监控事件'换电柜断充'"""
    return _event_battery_alarms(
        ["换电柜断充"],
        "break_charge",
        "电池断充",
        PRIORITY.get("break_charge", 2),
        oem_ids,
    )


def battery_alarms(oem_ids=None):
    """汇总电池三类告警，按优先级+时间排序"""
    out = []
    out += hungry_alarms(oem_ids)
    out += unrecognized_alarms(oem_ids)
    out += break_charge_alarms(oem_ids)
    out.sort(key=lambda x: (x.get("priority", 9), x.get("time") or ""))
    return out


def battery_alarm_count(oem_ids=None):
    """按告警类型计数，用于看板/客户维度"""
    from collections import Counter
    cnt = Counter()
    for a in battery_alarms(oem_ids):
        cnt[a["alarm_type"]] += 1
    return cnt
