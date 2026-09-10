# -*- coding: utf-8 -*-
"""筛选维度选项数据（board_filter_upgrade）

为前端筛选器提供基于库真实字段的下拉选项：
城市/区域/街道/社区、代理商、电池产品、网点、业务员、商户、品牌、事业线。
全部实时查 ADB，带 oem_ids 权限过滤。选项接口见 /api/filters/options。
"""
from core import db


def _oem_in(oem_ids, col="oem_id"):
    if oem_ids:
        return f" AND {col} IN ({','.join(map(str, oem_ids))})"
    return ""


def _rows(sql):
    try:
        return db.query(sql) or []
    except Exception:  # noqa: BLE001 单类维度过期时降级为空
        return []


def city_options(oem_ids=None):
    """城市列表：t_site.city + t_exchange_order.site_city 去重合并"""
    out = {}
    _o = _oem_in(oem_ids)
    for r in _rows(f"SELECT DISTINCT city FROM t_site WHERE is_del=0 AND city IS NOT NULL AND city<>''{_o}"):
        if r.get("city"):
            out[r["city"]] = r["city"]
    for r in _rows(f"SELECT DISTINCT site_city FROM t_exchange_order WHERE is_del=0 AND site_city IS NOT NULL AND site_city<>''{_o} LIMIT 2000"):
        if r.get("site_city"):
            out[r["site_city"]] = r["site_city"]
    return [{"value": k, "label": k} for k in sorted(out)]


def area_options(oem_ids=None, city=""):
    """区域列表：t_site.area；可选按城市过滤"""
    w = "s.is_del=0 AND s.area IS NOT NULL AND s.area<>'' "
    if oem_ids:
        w += _oem_in(oem_ids, "s.oem_id")
    if city:
        w += f" AND s.city LIKE '%%{city}%%'"
    rows = _rows(f"SELECT DISTINCT s.area FROM t_site s WHERE {w} LIMIT 1000")
    out = {r["area"] for r in rows if r.get("area")}
    return [{"value": k, "label": k} for k in sorted(out)]


def street_options(oem_ids=None):
    """街道列表：t_site.street"""
    w = "is_del=0 AND street IS NOT NULL AND street<>''" + _oem_in(oem_ids)
    rows = _rows(f"SELECT DISTINCT street FROM t_site WHERE {w} LIMIT 1000")
    out = {r["street"] for r in rows if r.get("street")}
    return [{"value": k, "label": k} for k in sorted(out)]


def community_options(oem_ids=None):
    """社区列表：t_site.community"""
    w = "is_del=0 AND community IS NOT NULL AND community<>''" + _oem_in(oem_ids)
    rows = _rows(f"SELECT DISTINCT community FROM t_site WHERE {w} LIMIT 1000")
    out = {r["community"] for r in rows if r.get("community")}
    return [{"value": k, "label": k} for k in sorted(out)]


def agency_options(oem_ids=None):
    """代理商列表：t_exchange_order.agency_id/agency_name + t_site.agency_id"""
    out = {}
    _o = _oem_in(oem_ids)
    for r in _rows(f"SELECT DISTINCT agency_id, agency_name FROM t_exchange_order "
                   f"WHERE is_del=0 AND agency_id IS NOT NULL AND agency_id<>'' AND agency_name IS NOT NULL AND agency_name<>''{_o} LIMIT 2000"):
        _id, _name = r.get("agency_id"), r.get("agency_name")
        if _id is not None and str(_id).strip():
            out[str(_id)] = _name or str(_id)
    return [{"value": k, "label": v} for k, v in sorted(out.items(), key=lambda x: str(x[1]))]


def battery_product_options(oem_ids=None):
    """电池产品列表：t_battery_product"""
    w = "is_del=0" + _oem_in(oem_ids)
    rows = _rows(f"SELECT id, name, code FROM t_battery_product WHERE {w} LIMIT 1000")
    return [{"value": str(r["id"]), "label": (r.get("name") or r.get("code") or f"#{r['id']}")}
            for r in rows if r.get("id") is not None]


def battery_brand_options(oem_ids=None):
    """电池品牌列表：t_battery_brand"""
    w = "is_del=0" + _oem_in(oem_ids)
    rows = _rows(f"SELECT id, name FROM t_battery_brand WHERE {w} LIMIT 1000")
    return [{"value": str(r["id"]), "label": (r.get("name") or f"#{r['id']}")}
            for r in rows if r.get("id") is not None]


def bus_unit_options(oem_ids=None):
    """事业线列表：t_business_unit"""
    w = "is_del=0" + _oem_in(oem_ids)
    rows = _rows(f"SELECT id, name FROM t_business_unit WHERE {w} LIMIT 1000")
    return [{"value": str(r["id"]), "label": (r.get("name") or f"#{r['id']}")}
            for r in rows if r.get("id") is not None]


def site_options(oem_ids=None, keyword=""):
    """网点列表：t_site（量大约束 2000 条）"""
    w = "is_del=0" + _oem_in(oem_ids)
    if keyword:
        w += f" AND name LIKE '%%{keyword}%%'"
    rows = _rows(f"SELECT id, name, city, area, address FROM t_site WHERE {w} "
                 f"ORDER BY create_time DESC LIMIT 2000")
    return [{"value": str(r["id"]), "label": (r.get("name") or f"网点#{r['id']}"),
             "city": r.get("city") or "", "area": r.get("area") or ""}
            for r in rows if r.get("id") is not None]


def employee_options(oem_ids=None):
    """门店业务员列表：t_site_store_employee"""
    w = "is_del=0" + _oem_in(oem_ids)
    rows = _rows(f"SELECT id, name, serve_site_id, serve_site_name, merchant_id "
                 f"FROM t_site_store_employee WHERE {w} LIMIT 2000")
    return [{"value": str(r["id"]), "label": (r.get("name") or f"业务员#{r['id']}"),
             "site_name": r.get("serve_site_name") or ""}
            for r in rows if r.get("id") is not None]


def merchant_options(oem_ids=None):
    """商户列表：t_merchant"""
    w = "is_del=0" + _oem_in(oem_ids)
    rows = _rows(f"SELECT id, name, merchant_id FROM t_merchant WHERE {w} LIMIT 2000")
    return [{"value": str(r["id"]), "label": (r.get("name") or f"商户#{r['id']}")}
            for r in rows if r.get("id") is not None]


def options(oem_ids=None, city=""):
    """汇总全部维度选项（/api/filters/options）"""
    return {
        "cities": city_options(oem_ids),
        "areas": area_options(oem_ids, city),
        "streets": street_options(oem_ids),
        "communities": community_options(oem_ids),
        "agencies": agency_options(oem_ids),
        "battery_products": battery_product_options(oem_ids),
        "battery_brands": battery_brand_options(oem_ids),
        "bus_units": bus_unit_options(oem_ids),
        "sites": site_options(oem_ids),
        "employees": employee_options(oem_ids),
        "merchants": merchant_options(oem_ids),
    }
