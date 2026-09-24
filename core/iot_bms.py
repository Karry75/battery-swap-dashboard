# -*- coding: utf-8 -*-
"""物联网库 BMS 故障位接入层（dudubox-online.bms_monitor_message）

- 数据源：MongoDB 物联网库（.env 的 IOT_MONGO_URI / IOT_MONGO_DB，只读账号）
- 位标志：bms_fault1~5 的按位标志，解码为 "组.位"（如 1.3）
- 映射：config/bms_alarm_map.yaml（6 类告警 <- 位），文件改动热生效
- 关联：按电池 SN 关联业务库 cb_battery.oem_id，用于“客户”维度筛选
- 容错：物联网库不可用时返回 ok=False + error，调用方自行降级（不抛异常、不阻塞整页）
"""
import logging
import os
import threading
import time

import yaml

import config.settings as settings
from core import db

logger = logging.getLogger("board.iot_bms")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(BASE_DIR, "config", "bms_alarm_map.yaml")
FAULT_FIELDS = ["bms_fault%d" % i for i in range(1, 6)]
TTL = int(os.environ.get("IOT_BMS_TTL", "180") or 180)          # 快照缓存秒数
SN_CHUNK = 200                                                   # SN 关联业务库的分片大小

_lock = threading.Lock()
_cache = {"ts": 0.0, "data": None}
_map_cache = {"mtime": None, "data": None}


# ---------------------------------------------------------------- 配置
def _uri():
    return os.environ.get("IOT_MONGO_URI", "") or settings.get("iot.mongo_uri", "")


def _dbname():
    return os.environ.get("IOT_MONGO_DB", "") or settings.get("iot.mongo_db", "dudubox-online")


def alarm_map():
    """读取 6 类告警 <- 故障位 映射（按 mtime 热更新）"""
    try:
        mtime = os.path.getmtime(MAP_PATH)
    except OSError:
        return {"classes": [], "source": {}}
    if _map_cache["mtime"] != mtime:
        with open(MAP_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _map_cache["data"] = data
        _map_cache["mtime"] = mtime
    return _map_cache["data"]


# ---------------------------------------------------------------- 解码
def _bits_of(doc):
    """bms_fault1~5 -> ["1.3", "4.6", ...]"""
    out = []
    for gi, field in enumerate(FAULT_FIELDS, start=1):
        raw = doc.get(field)
        if not raw:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        for b in range(8):
            if val & (1 << b):
                out.append("%d.%d" % (gi, b))
    return out


def _fnum(v):
    return v if isinstance(v, (int, float)) else None


def _rng(vals, fmt="%.1f"):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return "-"
    return (fmt + " ~ " + fmt) % (min(vals), max(vals))


# ---------------------------------------------------------------- 拉取
def _fetch_docs():
    from pymongo import MongoClient  # 延迟导入：未装 pymongo 不影响其他板块

    client = MongoClient(_uri(), serverSelectionTimeoutMS=6000,
                         connectTimeoutMS=6000, socketTimeoutMS=30000)
    try:
        coll = client[_dbname()]["bms_monitor_message"]
        query = {"$or": [{f: {"$gt": 0}} for f in FAULT_FIELDS]}
        proj = {"sn": 1, "base_datetime": 1, "status": 1, "bms_soc": 1,
                "bms_cell_max_temp": 1, "bms_cell_min_volt": 1, "bms_cell_max_volt": 1,
                "bms_work_status": 1, "bms_chg": 1, "tracker_location_address": 1}
        proj.update({f: 1 for f in FAULT_FIELDS})
        return list(coll.find(query, proj))
    finally:
        client.close()


def _battery_owner_map(sns):
    """电池 SN -> {oem_id, online_status, battery_status}（业务库 cb_battery，分片查询，失败返回 {}）"""
    out = {}
    if not sns:
        return out
    table = settings.get("database.tables", {}).get("battery", "t_battery")
    sns = sorted(sns)
    for i in range(0, len(sns), SN_CHUNK):
        chunk = sns[i:i + SN_CHUNK]
        marks = ",".join(["%s"] * len(chunk))
        try:
            rows = db.query(
                "SELECT device_sn, oem_id, online_status, battery_status "
                "FROM %s WHERE is_del=0 AND device_sn IN (%s)" % (table, marks),
                tuple(chunk),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("battery owner map 查询失败: %s", exc)
            return out
        for r in rows:
            out[str(r.get("device_sn"))] = {
                "oem_id": str(r.get("oem_id") or ""),
                "online_status": r.get("online_status") or "",
                "battery_status": r.get("battery_status") or "",
            }
    return out


def _customer_names():
    try:
        from core.customers import get_customer_map
        return get_customer_map()
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- 快照
def snapshot():
    """物联网库 BMS 故障位快照（带 TTL 缓存）

    ok=False 时 error 给出原因，前端据此如实展示，不阻断其他板块。
    """
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < TTL:
        return _cache["data"]

    result = {
        "ok": False, "error": None, "name": "电池 BMS 告警（物联网库实时上报）",
        "source": "物联网库 %s.bms_monitor_message" % _dbname(),
        "classes": [], "bits": [], "batteries": [],
        "docs": 0, "sns": 0, "first_time": "-", "last_time": "-",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "confidence_note": "故障位含义依据遥测特征推断，未经厂商协议确认；改 config/bms_alarm_map.yaml 可修正",
    }
    if not _uri():
        result["error"] = "未配置 IOT_MONGO_URI"
        return result

    try:
        docs = _fetch_docs()
    except Exception as exc:  # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        logger.warning("物联网库读取失败: %s", result["error"])
        _cache.update(ts=now, data=result)
        return result

    # ---- 按位聚合 ----
    per_bit = {}
    per_sn = {}
    for d in docs:
        bits = _bits_of(d)
        if not bits:
            continue
        sn = str(d.get("sn") or "")
        ts = str(d.get("base_datetime") or "")
        for b in bits:
            rec = per_bit.setdefault(b, {"bit": b, "sns": set(), "docs": 0,
                                         "temp": [], "vmin": [], "vmax": [], "last": ""})
            rec["sns"].add(sn)
            rec["docs"] += 1
            t = _fnum(d.get("bms_cell_max_temp"))
            if t is not None and t > 0:
                rec["temp"].append(t)
            v = _fnum(d.get("bms_cell_min_volt"))
            if v is not None and v > 0:
                rec["vmin"].append(v)
            v = _fnum(d.get("bms_cell_max_volt"))
            if v is not None and 2000 < v < 4500:
                rec["vmax"].append(v)
            rec["last"] = max(rec["last"], ts)
        s = per_sn.setdefault(sn, {"sn": sn, "bits": set(), "last": "", "soc": None,
                                   "temp": None, "status": "", "addr": ""})
        s["bits"].update(bits)
        s["last"] = max(s["last"], ts)
        s["soc"] = d.get("bms_soc")
        s["temp"] = d.get("bms_cell_max_temp")
        s["status"] = d.get("status") or ""
        s["addr"] = d.get("tracker_location_address") or ""

    # ---- 位实况 ----
    bits_rows = []
    for b, rec in per_bit.items():
        gi, bi = (int(x) for x in b.split("."))
        bits_rows.append({
            "bit": b, "group": gi, "index": bi,
            "batteries": len(rec["sns"]), "records": rec["docs"],
            "temp_range": _rng(rec["temp"], "%.1f"),
            "vmin_range": _rng(rec["vmin"], "%.0f"),
            "vmax_range": _rng(rec["vmax"], "%.0f"),
            "last_time": rec["last"] or "-",
        })
    bits_rows.sort(key=lambda x: (x["group"], x["index"]))

    # ---- 6 类告警 ----
    amap = alarm_map()
    classes = []
    hit_sns = set()
    for cls in amap.get("classes", []):
        bits = [str(x) for x in cls.get("bits", []) or []]
        sns, recs, last = set(), 0, ""
        for b in bits:
            rec = per_bit.get(b)
            if not rec:
                continue
            sns |= rec["sns"]
            recs += rec["docs"]
            last = max(last, rec["last"])
        hit_sns |= sns
        classes.append({
            "name": cls.get("name"), "bits": bits, "bit_text": ", ".join(bits) or "-",
            "batteries": len(sns), "records": recs, "last_time": last or "-",
            "confidence": cls.get("confidence") or "todo",
            "evidence": cls.get("evidence") or "",
            "pending": not bool(bits),
            "source": "物联网库故障位 %s" % (", ".join(bits) if bits else "-"),
        })

    # ---- 命中电池明细（关联业务库客户） ----
    owner = _battery_owner_map(hit_sns)
    cmap = _customer_names()
    bat_rows = []
    cls_of_bit = {}
    for cls in classes:
        for b in cls["bits"]:
            cls_of_bit.setdefault(b, []).append(cls["name"])
    for sn in hit_sns:
        s = per_sn.get(sn) or {}
        names = []
        for b in sorted(s.get("bits", [])):
            names.extend(cls_of_bit.get(b, []))
        names = list(dict.fromkeys(names))
        o = owner.get(sn) or {}
        bat_rows.append({
            "sn": sn or "-",
            "classes": "、".join(names) or "-",
            "class_count": len(names),
            "bit_count": len(s.get("bits", [])),
            "bits": ", ".join(sorted(s.get("bits", []))),
            "oem_id": o.get("oem_id", ""),
            "customer_name": cmap.get(o.get("oem_id", ""), "-"),
            "online_status": o.get("online_status") or s.get("status") or "-",
            "battery_status": o.get("battery_status", ""),
            "soc": s.get("soc"), "temp": s.get("temp"),
            "addr": s.get("addr") or "-",
            "last_time": s.get("last") or "-",
        })
    bat_rows.sort(key=lambda x: (-x["class_count"], -x["bit_count"]))

    times = sorted(str(d.get("base_datetime") or "") for d in docs if d.get("base_datetime"))
    result.update({
        "ok": True,
        "classes": classes,
        "bits": bits_rows,
        "batteries": bat_rows[:200],
        "docs": len(docs),
        "sns": len(per_sn),
        "first_time": times[0] if times else "-",
        "last_time": times[-1] if times else "-",
    })
    _cache.update(ts=now, data=result)
    return result


def filtered(oem_ids=None):
    """按客户范围过滤后的快照视图（oem_ids 为空表示全量）"""
    snap = snapshot()
    if not snap.get("ok"):
        return snap
    if not oem_ids:
        return snap
    sel = set(str(int(x)) for x in oem_ids)
    out = dict(snap)
    keep_cls = []
    for cls in snap["classes"]:
        bits = set(cls["bits"])
        bts = [b for b in snap["batteries"] if b["oem_id"] in sel and (set(b["bits"].split(", ")) & bits)]
        uniq = {b["sn"] for b in bts}
        recs = sum(b["bit_count"] for b in bts)
        keep_cls.append(dict(cls, batteries=len(uniq), records=recs))
    out["classes"] = keep_cls
    out["batteries"] = [b for b in snap["batteries"] if b["oem_id"] in sel]
    out["sns"] = len(out["batteries"])
    return out
