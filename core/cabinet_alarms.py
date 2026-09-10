# -*- coding: utf-8 -*-
"""换电柜告警计算：烟感 / 水浸 / 仓位

- 烟感(smoke)：监控事件'换电柜烟感告警' + 实时 smoke=1 兜底
- 水浸(flooded)：监控事件'换电柜水浸告警' + 实时 flooded=1 / water=doing 兜底
- 仓位(slot)：监控事件'换电柜满仓' + 实时故障仓位(status=error)兜底
事件与实时按 exchange_id 去重（事件优先）
"""
from core import db
from core.customers import get_customer_map
from core.utils import ts_to_str
import config.settings as settings

T = settings.get("database.tables", {})
MONITOR_EVENT = T.get("monitor_event", "cb_monitor_ex_event")
MONITOR_EVENT_EXCHANGE = T.get("monitor_event_exchange", "cb_monitor_ex_event_exchange")
EXCHANGE = T.get("exchange", "cb_exchange")
EXCHANGE_LAST_UPLOAD = T.get("exchange_last_upload", "cb_exchange_last_upload")
EXCHANGE_STATUS = T.get("exchange_status", "cb_exchange_status")
EXCHANGE_LAST_STORE = T.get("exchange_last_store", "cb_exchange_last_store")

PRIORITY = settings.get("priority.exchange", {})

_customer_map = None


def _customers():
    global _customer_map
    if _customer_map is None:
        _customer_map = get_customer_map()
    return _customer_map


def _oem_filter(oem_ids, alias="e"):
    if not oem_ids:
        return ""
    ids = ",".join(str(int(i)) for i in oem_ids)
    return f" AND {alias}.oem_id IN ({ids})"


def _event_exchange_alarms(names, alarm_type, alarm_name, priority, oem_ids=None):
    """通用：事件表未解除机柜类事件，join 机柜事件明细"""
    placeholders = ",".join(["%s"] * len(names))
    rows = db.query(
        f"""
        SELECT e.id, e.oem_id, e.agency_name, e.level, e.create_time,
               ee.exchange_id, ee.exchange_sn, ee.store_id, ee.site_name, ee.address, ee.city, ee.area
        FROM {MONITOR_EVENT} e
        LEFT JOIN {MONITOR_EVENT_EXCHANGE} ee ON ee.ex_event_id = e.id
        WHERE e.is_del=0 AND e.status='init'
          AND e.name IN ({placeholders}){_oem_filter(oem_ids)}
        ORDER BY e.create_time DESC
        """,
        names,
    )
    cmap = _customers()
    out = []
    for r in rows:
        loc = r.get("site_name") or r.get("address") or ""
        store = f"仓位{r.get('store_id')}" if r.get("store_id") else ""
        out.append({
            "device_type": "exchange",
            "event_id": r.get("id"),
            "device_id": r.get("exchange_id"),
            "device_sn": r.get("exchange_sn"),
            "customer_id": r.get("oem_id"),
            "customer_name": cmap.get(str(r.get("oem_id")), ""),
            "alarm_type": alarm_type,
            "alarm_name": alarm_name,
            "priority": priority,
            "level": r.get("level") or "normal",
            "time": ts_to_str(r.get("create_time")),
            "desc": f"{store} 位置:{loc or '未知'}".strip(),
            "source": "event",
            "extra": {"agency_name": r.get("agency_name"), "site_name": r.get("site_name"),
                      "address": r.get("address"), "city": r.get("city"), "area": r.get("area")},
        })
    return out


def _realtime_exchange_alarms(smoke_only=False, flooded_only=False, oem_ids=None):
    """实时状态兜底：cb_exchange_last_upload 烟感/水浸"""
    conds = []
    if smoke_only:
        conds.append("u.smoke='1'")
    if flooded_only:
        conds.append("(u.flooded='1' OR s.water='doing')")
    if not conds:
        return []
    sql = f"""
        SELECT u.exchange_id, u.device_sn, u.smoke, u.flooded, u.last_upload_time, u.oem_id,
               x.last_location_address
        FROM {EXCHANGE_LAST_UPLOAD} u
        LEFT JOIN {EXCHANGE} x ON x.id = u.exchange_id
        LEFT JOIN {EXCHANGE_STATUS} s ON s.exchange_id = u.exchange_id AND s.is_del=0
        WHERE u.is_del=0 AND ({" OR ".join(conds)}){_oem_filter(oem_ids, 'u')}
        ORDER BY u.last_upload_time DESC
    """
    rows = db.query(sql)
    cmap = _customers()
    out = []
    for r in rows:
        alarms = []
        if smoke_only and r.get("smoke") == "1":
            alarms.append(("smoke", "烟感告警", PRIORITY.get("smoke", 1)))
        if flooded_only and r.get("flooded") == "1":
            alarms.append(("flooded", "水浸告警", PRIORITY.get("flooded", 1)))
        for atype, aname, prio in alarms:
            out.append({
                "device_type": "exchange",
                "device_id": r.get("exchange_id"),
                "device_sn": r.get("device_sn"),
                "customer_id": r.get("oem_id"),
                "customer_name": cmap.get(str(r.get("oem_id")), ""),
                "alarm_type": atype,
                "alarm_name": aname,
                "priority": prio,
                "level": "high",
                "time": ts_to_str(r.get("last_upload_time")),
                "desc": f"实时状态触发 位置:{r.get('last_location_address') or '未知'}",
                "source": "realtime",
                "extra": {"address": r.get("last_location_address")},
            })
    return out


def smoke_alarms(oem_ids=None):
    """烟感告警：事件 + 实时，按 exchange_id 去重"""
    merged = {}
    for a in _event_exchange_alarms(
        ["换电柜烟感告警"], "smoke", "烟感告警", PRIORITY.get("smoke", 1), oem_ids
    ):
        merged.setdefault(f"smoke-{a['device_id']}", a)
    for a in _realtime_exchange_alarms(smoke_only=True, oem_ids=oem_ids):
        merged.setdefault(f"smoke-{a['device_id']}", a)
    return list(merged.values())


def flooded_alarms(oem_ids=None):
    """水浸告警：事件 + 实时，按 exchange_id 去重"""
    merged = {}
    for a in _event_exchange_alarms(
        ["换电柜水浸告警"], "flooded", "水浸告警", PRIORITY.get("flooded", 1), oem_ids
    ):
        merged.setdefault(f"flooded-{a['device_id']}", a)
    for a in _realtime_exchange_alarms(flooded_only=True, oem_ids=oem_ids):
        merged.setdefault(f"flooded-{a['device_id']}", a)
    return list(merged.values())


def slot_alarms(oem_ids=None):
    """仓位告警：事件(满仓) + 实时故障仓位(status=error)"""
    merged = {}
    for a in _event_exchange_alarms(
        ["换电柜满仓"], "slot", "仓位告警", PRIORITY.get("slot", 2), oem_ids
    ):
        merged.setdefault(f"slot-{a['device_id']}-{a['event_id']}", a)

    rows = db.query(
        f"""
        SELECT ls.exchange_id, ls.device_sn, ls.number, ls.status, ls.battery_sn, ls.soc,
               ls.voltage, ls.update_time, ls.oem_id, x.last_location_address
        FROM {EXCHANGE_LAST_STORE} ls
        LEFT JOIN {EXCHANGE} x ON x.id = ls.exchange_id
        WHERE ls.is_del=0 AND ls.status='error'{_oem_filter(oem_ids, 'ls')}
        ORDER BY ls.update_time DESC
        """
    )
    cmap = _customers()
    for r in rows:
        key = f"slot-{r.get('exchange_id')}-{r.get('number')}"
        merged[key] = {
            "device_type": "exchange",
            "device_id": r.get("exchange_id"),
            "device_sn": r.get("device_sn"),
            "customer_id": r.get("oem_id"),
            "customer_name": cmap.get(str(r.get("oem_id")), ""),
            "alarm_type": "slot",
            "alarm_name": "仓位告警",
            "priority": PRIORITY.get("slot", 2),
            "level": "normal",
            "time": ts_to_str(r.get("update_time")),
            "desc": f"仓位{r.get('number')} 故障（status=error），电池:{r.get('battery_sn') or '无'}",
            "source": "realtime",
            "extra": {"store_number": r.get("number"), "status": r.get("status"), "address": r.get("last_location_address")},
        }
    return list(merged.values())


def exchange_alarms(oem_ids=None):
    """汇总机柜三类告警，按优先级+时间排序"""
    out = []
    out += smoke_alarms(oem_ids)
    out += flooded_alarms(oem_ids)
    out += slot_alarms(oem_ids)
    out.sort(key=lambda x: (x.get("priority", 9), x.get("time") or ""))
    return out


def exchange_alarm_count(oem_ids=None):
    from collections import Counter
    cnt = Counter()
    for a in exchange_alarms(oem_ids):
        cnt[a["alarm_type"]] += 1
    return cnt
