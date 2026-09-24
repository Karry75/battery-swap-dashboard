# -*- coding: utf-8 -*-
"""看板统计聚合：总览 / 按客户 / 告警分类"""
from collections import defaultdict, Counter
from core import db
from core.customers import get_customer_map, get_customers
from core.battery_alarms import battery_alarms
from core.cabinet_alarms import exchange_alarms, board_alarm_counts
from core import iot_bms
import config.settings as settings

T = settings.get("database.tables", {})
BATTERY = T.get("battery", "t_battery")
EXCHANGE = T.get("exchange", "t_exchange")
BATTERY_SERIES = T.get("battery_series", "t_battery_series")

# 字段值 -> 中文含义（集中定义于 core/cn_labels.py，库中真实取值域）
from core.cn_labels import (  # noqa: F401
    SITE_STATUS_CN, AUDIT_PROGRESS_CN, BATTERY_STATUS_CN,
    ONLINE_STATUS_CN, DEPOSIT_STATUS_CN, BATTERY_TYPE_CN, UNKNOWN_CN, cn as cn_label,
)

# 任务指定的 6 类电池 BMS 告警（业务库若无独立事件源则标注“数据源待接入”）
BMS_ALARM_CLASSES = [
    "软件单体严重过放保护", "软件电芯热扩散告警", "软件放电高温保护",
    "高温预警", "软件充电高温保护", "单体电芯过充",
]

_customer_map = None
_bms_probe_cache = None


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


def _eff_oem(oem_ids, args):
    """生效客户范围 = 权限范围 ∩ 界面“客户”筛选（oem_id）

    界面未选客户时返回权限范围；界面选了客户但权限范围为空（admin 全量）时直接用所选客户。
    """
    if not args:
        return oem_ids
    raw = str(args.get("oem_id") or "").strip()
    if not raw:
        return oem_ids
    sel = [int(x) for x in raw.split(",") if x.strip().isdigit()]
    if not sel:
        return oem_ids
    if not oem_ids:
        return sel
    inter = [i for i in sel if i in list(oem_ids)]
    return inter or sel


def device_totals(oem_ids=None, args=None):
    """设备总量与在线/离线（电池支持代理商/品牌/电池产品；换电柜支持城市/网点/代理商/品牌）"""
    oem_ids = _eff_oem(oem_ids, args)
    bq = f"SELECT COUNT(*) total, SUM(b.online_status='online') online, SUM(b.online_status='offline') offline " \
         f"FROM {BATTERY} b WHERE b.is_del=0{_oem_filter(oem_ids, 'b')}"
    eq = f"SELECT COUNT(*) total, SUM(e.online_status='online') online, SUM(e.online_status='offline') offline " \
         f"FROM {EXCHANGE} e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 " \
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


def alarm_summary(oem_ids=None, args=None):
    """告警分类计数：电池三类 + 机柜三类 + 检测板六类"""
    oem_ids = _eff_oem(oem_ids, args)
    batt = defaultdict(int)
    for a in battery_alarms(oem_ids):
        batt[a["alarm_type"]] += 1
    exch = defaultdict(int)
    for a in exchange_alarms(oem_ids):
        exch[a["alarm_type"]] += 1
    board = board_alarm_counts(oem_ids, args)
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
        "board": board,
    }


def summary(oem_ids=None, args=None):
    """看板总览（设备量/告警/客户均继承统一筛选维度的客户范围）"""
    totals = device_totals(oem_ids, args)
    alarms = alarm_summary(oem_ids, args)
    customers = get_customers()
    return {
        "customers": {"total": len(customers), "enabled": len([c for c in customers if c.get("status") == "on"])},
        "device": totals,
        "alarm": alarms,
    }


def customer_stats(oem_ids=None, args=None):
    """按客户统计：设备数量/在线离线/告警数（支持客户/设备维度筛选）"""
    oem_ids = _eff_oem(oem_ids, args)
    cmap = _customers()
    bw = ""
    ew = ""
    if args:
        from core.filters import FilterSet, BATTERY_COLUMNS, EXCHANGE_COLUMNS
        bt_f = FilterSet(args, BATTERY_COLUMNS)
        if bt_f.has:
            bw = bt_f.and_clause()
        ex_f = FilterSet(args, EXCHANGE_COLUMNS)
        if ex_f.has:
            ew = ex_f.and_clause()

    stat = defaultdict(lambda: {
        "battery": {"total": 0, "online": 0, "offline": 0},
        "exchange": {"total": 0, "online": 0, "offline": 0},
        "battery_alarm": 0,
        "exchange_alarm": 0,
    })

    for r in db.query(
        f"SELECT b.oem_id, COUNT(*) total, SUM(b.online_status='online') online, SUM(b.online_status='offline') offline "
        f"FROM {BATTERY} b WHERE b.is_del=0{_oem_filter(oem_ids, 'b')}{bw} GROUP BY b.oem_id"
    ):
        s = stat[r["oem_id"]]
        s["battery"]["total"] = int(r["total"] or 0)
        s["battery"]["online"] = int(r["online"] or 0)
        s["battery"]["offline"] = int(r["offline"] or 0)

    for r in db.query(
        f"SELECT e.oem_id, COUNT(*) total, SUM(e.online_status='online') online, SUM(e.online_status='offline') offline "
        f"FROM {EXCHANGE} e LEFT JOIN t_site s ON s.id=e.site_id AND s.is_del=0 "
        f"WHERE e.is_del=0{_oem_filter(oem_ids, 'e')}{ew} GROUP BY e.oem_id"
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


# ================= 紧急告警中心 =================
def battery_distribution(oem_ids=None, args=None):
    """电池总体分布：总量/在线/离线、柜内与柜外（含柜内在线）、状态分布（中文映射）"""
    oem_ids = _eff_oem(oem_ids, args)
    where = f"b.is_del=0{_oem_filter(oem_ids, 'b')}"
    if args:
        from core.filters import FilterSet, BATTERY_COLUMNS
        bt_f = FilterSet(args, BATTERY_COLUMNS)
        if bt_f.has:
            where += bt_f.and_clause()

    in_expr = "(b.last_upload_exchange_sn IS NOT NULL AND b.last_upload_exchange_sn<>'')"
    r = db.query(
        f"SELECT COUNT(*) total, "
        f"SUM(b.online_status='online') online, SUM(b.online_status='offline') offline, "
        f"SUM({in_expr}) inside_cnt, SUM(NOT {in_expr}) outside_cnt, "
        f"SUM({in_expr} AND b.online_status='online') inside_online, "
        f"SUM({in_expr} AND b.online_status='offline') inside_offline "
        f"FROM {BATTERY} b WHERE {where}"
    )[0]

    stat_rows = db.query(
        f"SELECT b.battery_status st, COUNT(*) c FROM {BATTERY} b WHERE {where} GROUP BY b.battery_status"
    )
    status = []
    for sr in stat_rows:
        key = (sr["st"] or "").strip() or "unknown"
        status.append({
            "key": key,
            "name": BATTERY_STATUS_CN.get(key, key if key != "unknown" else "未知"),
            "count": int(sr["c"] or 0),
        })
    status.sort(key=lambda x: -x["count"])

    return {
        "total": int(r["total"] or 0),
        "online": int(r["online"] or 0),
        "offline": int(r["offline"] or 0),
        "inside": int(r["inside_cnt"] or 0),
        "outside": int(r["outside_cnt"] or 0),
        "inside_online": int(r["inside_online"] or 0),
        "inside_offline": int(r["inside_offline"] or 0),
        "status": status,
        "inside_rule": "柜内 = last_upload_exchange_sn 非空；柜外 = last_upload_exchange_sn 为空",
    }


def bms_alarm_probe():
    """尽力在业务库定位 6 类电池 BMS 告警来源（结果缓存，仅探测一次）

    探测路径（逐条独立执行，单条 SQL 报错只记录原因，不影响其余来源）：
      1) cb_battery_upload.errors —— 电池整机上报故障 JSON
      2) cb_battery_last_upload.source_data —— 电池最近上报源数据
      3) cb_monitor_ex_event.name —— 异常事件表全部事件名
    三条来源命中数全为 0，即判定业务库确无该 6 类告警语义，前端据实标注“数据源待接入”。
    """
    global _bms_probe_cache
    if _bms_probe_cache is not None:
        return _bms_probe_cache

    out = {
        "available": False,
        "sources": [],
        "counts": {},
        "event_names": [],
        "note": "业务库未找到 6 类 BMS 告警对应字段/事件，数据源待接入",
    }

    def _one(sql, params=None, tag=""):
        """单条探测：失败仅记录原因并返回 None（不抛出、不重试）"""
        try:
            return db.query(sql, params)
        except Exception as exc:  # noqa: BLE001
            out.setdefault("errors", []).append(
                "%s %s: %s" % (tag, type(exc).__name__, str(exc)[:120]))
            return None

    up = T.get("battery_upload", "cb_battery_upload")
    blu = T.get("battery_last_upload", "cb_battery_last_upload")
    evt = T.get("monitor_event", "cb_monitor_ex_event")
    _phys = lambda name: (getattr(settings, "SCHEMA_MAP", None) or {}).get(name, name)  # noqa: E731

    for tbl, col, label in ((up, "errors", "电池整机上报 errors 字段"),
                            (blu, "source_data", "电池最近上报 source_data")):
        rows = _one("SELECT COUNT(*) c FROM %s WHERE %s IS NOT NULL AND %s<>'' AND %s<>'[]'"
                    % (tbl, col, col, col), tag=tbl)
        if rows is None:
            continue
        out["sources"].append({"table": _phys(tbl), "column": col, "label": label,
                               "rows": int(rows[0]["c"] or 0)})
        for name in BMS_ALARM_CLASSES:
            hit = _one("SELECT COUNT(*) c FROM %s WHERE %s LIKE %%s" % (tbl, col),
                       ("%" + name + "%",), tag=tbl)
            if hit:
                out["counts"][name] = out["counts"].get(name, 0) + int(hit[0]["c"] or 0)

    rows = _one("SELECT name n, COUNT(*) c FROM %s WHERE is_del=0 GROUP BY name ORDER BY c DESC LIMIT 60" % evt,
                tag=evt)
    if rows is not None:
        out["sources"].append({"table": _phys(evt), "column": "name", "label": "异常事件表事件名",
                               "rows": int(sum(int(r["c"] or 0) for r in rows))})
        out["event_names"] = [str(r["n"]) for r in rows]
        for name in BMS_ALARM_CLASSES:
            hit = [r for r in rows if name in str(r["n"])]
            if hit:
                out["counts"][name] = out["counts"].get(name, 0) + int(hit[0]["c"] or 0)

    out["available"] = any(v > 0 for v in out["counts"].values())
    if out["available"]:
        out["note"] = "已在业务库定位到 BMS 告警语义来源"
    else:
        out["note"] = "业务库异常事件表 %d 类事件名及上报故障字段均不含该 6 类 BMS 告警，数据源待接入" % len(out["event_names"])
    _bms_probe_cache = out
    return out


def emergency_center(oem_ids=None, args=None):
    """紧急告警中心：电池规模/柜内外分布/紧急告警电池/紧急告警事项（含 6 类 BMS 告警标注）

    支持按客户(oem_id)、电池产品(battery_product_id)等统一筛选维度过滤。
    """
    oem_ids = _eff_oem(oem_ids, args)
    dist = battery_distribution(oem_ids, args)

    alarms = battery_alarms(oem_ids)
    # 客户筛选下进一步收敛告警明细
    if args and str(args.get("oem_id") or "").strip():
        sel = set(str(int(x)) for x in str(args.get("oem_id")).split(",") if x.strip().isdigit())
        alarms = [a for a in alarms if str(a.get("customer_id")) in sel]

    item_cnt = Counter()
    bat_map = {}
    no_sn = 0
    for a in alarms:
        aname = a.get("alarm_name") or a.get("alarm_type") or "未知告警"
        item_cnt[aname] += 1
        sn = a.get("device_sn") or (f"ID:{a.get('device_id')}" if a.get("device_id") else "")
        if not sn:  # 事件明细缺失 SN（左连接未命中），不计入电池排行，单独计数
            no_sn += 1
            continue
        rec = bat_map.setdefault(sn, {"sn": sn, "types": set(), "count": 0,
                                      "customer_name": a.get("customer_name") or ""})
        rec["types"].add(a.get("alarm_type"))
        rec["count"] += 1
    items = [{"name": k, "count": v} for k, v in item_cnt.most_common()]
    bat_rows = sorted(bat_map.values(), key=lambda x: (-len(x["types"]), -x["count"]))
    batteries = [{
        "rank": i + 1, "sn": r["sn"], "kinds": len(r["types"]),
        "count": r["count"], "customer_name": r["customer_name"],
    } for i, r in enumerate(bat_rows[:15])]

    # 检测板六类告警：先算，避免 BMS 探测异常波及其余板块
    board = board_alarm_counts(oem_ids, args)

    # 6 类 BMS 告警：主源为物联网库故障位；物联网库不可用时回退业务库探测并如实标注
    io = {"ok": False, "error": None, "classes": [], "bits": [], "batteries": [], "docs": 0, "sns": 0}
    try:
        io = iot_bms.filtered(oem_ids)
    except Exception as exc:  # noqa: BLE001
        io["error"] = "%s: %s" % (type(exc).__name__, exc)
    bms = []
    if io.get("ok"):
        for c in io["classes"]:
            bms.append({
                "name": c["name"], "count": int(c["batteries"]), "records": int(c["records"]),
                "bits": c["bits"], "bit_text": c["bit_text"], "source": c["source"],
                "confidence": c["confidence"], "evidence": c.get("evidence", ""),
                "last_time": c["last_time"], "pending": bool(c.get("pending")),
            })
        missing = [n for n in BMS_ALARM_CLASSES if n not in [c["name"] for c in io["classes"]]]
        for n in missing:  # 映射文件未覆盖的类别，如实标注
            bms.append({"name": n, "count": None, "records": 0, "bits": [], "bit_text": "-",
                        "source": "映射未配置", "confidence": "todo", "last_time": "-", "pending": True})
        bms_note = ("数据源：物联网库 bms_monitor_message（故障位实时上报，命中 %s 块电池 / %s 条记录，"
                    "窗口 %s ~ %s），已按客户维度关联业务库电池归属" % (
                        io["sns"], io["docs"], io["first_time"], io["last_time"]))
        bms_ok = True
    else:
        probe = {"available": False, "counts": {}, "sources": [], "event_names": [], "note": ""}
        try:
            probe = bms_alarm_probe()
        except Exception as exc:  # noqa: BLE001
            probe["note"] = "BMS 来源探测异常(%s)" % type(exc).__name__
        for name in BMS_ALARM_CLASSES:
            cnt = probe["counts"].get(name)
            if probe["available"] and cnt:
                bms.append({"name": name, "count": int(cnt), "records": 0, "bits": [], "bit_text": "-",
                            "source": "业务库定位", "confidence": "mid", "last_time": "-", "pending": False})
            else:
                bms.append({"name": name, "count": None, "records": 0, "bits": [], "bit_text": "-",
                            "source": "数据源待接入", "confidence": "todo", "last_time": "-", "pending": True})
        bms_note = "物联网库不可用（%s）；业务库无独立事件源，数据源待接入" % (io.get("error") or "未配置")
        bms_ok = False

    return {
        "battery": {
            "total": dist["total"], "online": dist["online"], "offline": dist["offline"],
            "inside": dist["inside"], "outside": dist["outside"],
            "inside_online": dist["inside_online"], "inside_offline": dist["inside_offline"],
        },
        "battery_status": dist["status"],
        "battery_inside_rule": dist["inside_rule"],
        "emergency": {
            "battery_count": len(bat_map),
            "item_count": len(items),
            "alarm_total": len(alarms),
            "no_sn_alarm_count": no_sn,
            "items": items,
            "batteries": batteries,
        },
        "bms": bms,
        "bms_note": bms_note,
        "bms_ok": bms_ok,
        "bms_error": io.get("error"),
        "bms_source": io.get("source") or "物联网库 bms_monitor_message",
        "bms_fetched_at": io.get("fetched_at") or "-",
        "bms_confidence_note": io.get("confidence_note") or "",
        "bms_bits": io.get("bits") or [],
        "bms_batteries": io.get("batteries") or [],
        "bms_totals": {
            "docs": io.get("docs") or 0, "sns": io.get("sns") or 0,
            "first_time": io.get("first_time") or "-", "last_time": io.get("last_time") or "-",
        },
        "bms_sources": [], "bms_event_names": [],
        "board": board,
    }
