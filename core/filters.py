# -*- coding: utf-8 -*-
"""统一多维筛选模块（board_filter_upgrade）

把前端统一的筛选 query 参数翻译为 SQL WHERE 片段，筛选最终落到 ADB 聚合查询。

统一 query 参数（前端筛选器固定参数名）：
    start / end            时间范围（毫秒时间戳或 'YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS'）
                           作用于 columns["time"]（各统计主表流水时间：创建/上报时间）。
    op_start / op_end      业务时间范围，作用于 columns["op_time"]（如网点开业/关闭、协议业务期）。
    act_start / act_end    协议激活时间范围，作用于 columns["activation_time"]。
    stop_start / stop_end  协议终止时间范围，作用于 columns["stop_time"]。
    city / area / street / community  城市 / 区域 / 街道 / 社区（模糊匹配）
    agency_id              代理商ID（逗号分隔多选 → IN）
    battery_product_id     电池产品ID（逗号分隔多选 → IN）
    site_id                网点ID（逗号分隔多选 → IN）
    user_phone             消费者手机号（模糊）
    agreement_id           协议ID（精确）
    device_sn              设备SN（模糊，柜/电池/车辆共用）
    employee_id            门店业务员ID（逗号分隔多选 → IN）
    merchant_id            商户ID（逗号分隔多选 → IN）
    brand_id               电池品牌ID（逗号分隔多选 → IN）
    bu_id                  事业线ID（逗号分隔多选 → IN）

约束（AnalyticDB）：
    - 不参数化 LIMIT/OFFSET，本模块不涉及分页，仅生成 WHERE。
    - LIKE 用 '%%{kw}%%' 双百分号。
"""
import datetime
import time

_TIME_HINT = ("start", "end")


def parse_ms(v, end=False):
    """把 毫秒时间戳 / YYYY-MM-DD / YYYY-MM-DD HH:MM:SS 解析为毫秒时间戳。

    end=True 时日期补到当天 23:59:59.999，否则补到 00:00:00.000。
    返回 int（毫秒）；解析失败返回 None。
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # 纯数字（无连字符的毫秒/秒时间戳）：支持 10 位（秒）与 13 位（毫秒）
    if s.isdigit():
        try:
            n = int(s)
            if 10**11 <= n < 10**13:      # 10位 秒 -> 毫秒
                return n * 1000
            return n                        # 已是毫秒
        except (TypeError, ValueError):
            return None
    # 日期字符串
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    if end:
        if len(s) <= 10:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
    return int(dt.timestamp() * 1000)


class FilterSet:
    """依据 columns 声明的字段映射，把统一筛选参数翻译为 SQL WHERE 片段。

    columns 例（订单表）：
        {
          "time":            "o.create_time",
          "city":            "o.site_city",
          "area":            "o.site_area",
          "street":          "o.site_street",
          "agency_id":       "o.agency_id",
          "battery_product_id": "o.battery_product_id",
          "site_id":         "o.site_id",
          "user_phone":      "o.take_user_phone",
          "agreement_id":    "o.exchange_agreement_id",
          "device_sn":       "o.bike_sn",
          "employee_id":     "o.sign_site_store_employee_id",
          "merchant_id":     "o.site_distributor_id",
          "brand_id":        "o.battery_brand_id",
        }
    未声明的维度自动忽略（避免把无字段的筛选拼进 SQL）。
    """
    _LIKE_DIMS = ("city", "area", "street", "community", "user_phone", "device_sn")

    def __init__(self, args, columns):
        self.args = args or {}
        self.columns = columns or {}
        self.parts = []
        self._build()

    def _build(self):
        args = self.args
        # 时间范围：支持多组时间列，分别由不同参数对驱动
        for dim, start_key, end_key in (
            ("time", "start", "end"),
            ("op_time", "op_start", "op_end"),
            ("activation_time", "act_start", "act_end"),
            ("stop_time", "stop_start", "stop_end"),
        ):
            col = self.columns.get(dim)
            if not col:
                continue
            _s = parse_ms(args.get(start_key), end=False)
            _e = parse_ms(args.get(end_key), end=True)
            if _s is not None:
                self.parts.append(f"{col}>={_s}")
            if _e is not None:
                self.parts.append(f"{col}<={_e}")
        # 枚举/ID 类（支持逗号分隔多选）
        # 说明：col 支持两种形态
        #   1) 普通列名，如 "b.oem_id" -> 生成 col IN (...)
        #   2) 含 {ids} 占位符的子查询模板（用于无直连列、需经中间表关联的维度），
        #      如电池产品需经 电池型号->系列->产品 关联，模板内用 {ids} 占位
        for dim in ("oem_id", "agency_id", "battery_product_id", "site_id",
                    "employee_id", "merchant_id", "brand_id", "bu_id", "agreement_id"):
            col = self.columns.get(dim)
            if not col:
                continue
            raw = args.get(dim)
            if raw is None or str(raw).strip() == "":
                continue
            vals = [x.strip() for x in str(raw).split(",") if x.strip()]
            if not vals:
                continue
            _ids = [x for x in vals if x.isdigit()]
            if _ids:
                if "{ids}" in col:
                    self.parts.append(col.replace("{ids}", ",".join(_ids)))
                else:
                    self.parts.append(f"{col} IN ({','.join(_ids)})")
        # 模糊类
        for dim in self._LIKE_DIMS:
            col = self.columns.get(dim)
            if not col:
                continue
            raw = args.get(dim)
            if raw is None or str(raw).strip() == "":
                continue
            kw = str(raw).strip()
            if dim == "device_sn" and kw.lower().startswith("sn"):
                kw = kw[2:].strip()
            self.parts.append(f"{col} LIKE '%%{kw}%%'")

    @property
    def has(self):
        return bool(self.parts)

    def and_clause(self):
        return (" AND " + " AND ".join(self.parts)) if self.parts else ""

    def clause(self):
        return " AND ".join(self.parts)

    # ---- 辅助：业务时间范围（协议激活/终止、网点开业/关闭等） ----
    def time_range_values(self, start_key="op_start", end_key="op_end"):
        """解析业务时间范围，返回 (start_ms, end_ms)，用于非主时间列。"""
        return (parse_ms(self.args.get(start_key), end=False),
                parse_ms(self.args.get(end_key), end=True))


def now_ms():
    return int(time.time() * 1000)


# ============================================================================
# 各业务主表统一筛选字段映射
# key=统一筛选维度（与前端筛选器固定参数名一致），value=SQL 列（中文注释标明表别名）。
# 供各 core 模块构造 FilterSet 使用；未声明的维度自动忽略。
# ============================================================================

# 用户表 t_user（别名 u）
USER_COLUMNS = {
    "time": "u.create_time",
    "city": "u.city",
    "area": "u.area",
    "user_phone": "u.phone",
}

# 协议主表 t_exchange_agreement（别名 a）
AGREEMENT_COLUMNS = {
    "time": "a.create_time",
    "activation_time": "a.activation_time",   # 协议激活时间（ms）act_start/act_end
    "stop_time": "a.stop_time",                 # 协议终止时间（ms）stop_start/stop_end
    "city": "a.t_city_name",
    "agency_id": "a.agency_id",
    "battery_product_id": "a.battery_product_id",
    "site_id": "a.site_id",
    "user_phone": "a.user_phone",
    "agreement_id": "a.id",
    "employee_id": "a.sign_site_store_employee_id",
    "merchant_id": "a.sign_site_business_id",
}

# 换电订单表 t_exchange_order（别名 o）
ORDER_COLUMNS = {
    "time": "o.create_time",
    "city": "o.site_city",
    "area": "o.site_area",
    "street": "o.site_street",
    "agency_id": "o.agency_id",
    "battery_product_id": "o.battery_product_id",
    "site_id": "o.site_id",
    "user_phone": "o.take_user_phone",
    "agreement_id": "o.exchange_agreement_id",
    "device_sn": "o.bike_sn",
    "employee_id": "o.sign_site_store_employee_id",
}

# 服务单 t_exchange_service_order（别名 s）
SERVICE_COLUMNS = {
    "time": "s.create_time",
    "city": "s.t_city_name",
    "agency_id": "s.sign_agency_id",
    "battery_product_id": "s.battery_product_id",
    "site_id": "s.sign_site_id",
    "user_phone": "s.buyer_user_phone",
}

# 租期卡 t_user_exchange_rent（别名 r）
RENT_COLUMNS = {
    "time": "r.create_time",
    "battery_product_id": "r.battery_product_id",
}

# 网点表 t_site（别名 s）
SITE_COLUMNS = {
    "time": "s.create_time",
    "op_time": "s.start_open_time",            # 网点开业时间 op_start/op_end
    "city": "s.city",
    "area": "s.area",
    "street": "s.street",
    "community": "s.community",
    "agency_id": "s.agency_id",
    "site_id": "s.id",
    "merchant_id": "s.merchant_id",
    "battery_product_id": "s.battery_product_id",
}

# 工单表 t_work_order（别名 w）
WORK_ORDER_COLUMNS = {
    "time": "w.create_time",
    "city": "w.city",
    "area": "w.area",
    "street": "w.street",
    "community": "w.community",
    "agency_id": "w.agency_id",
}

# 客诉表 t_exchange_order_complaint（别名 c）
COMPLAINT_COLUMNS = {
    "time": "c.create_time",
    "user_phone": "c.user_phone",
    "device_sn": "c.battery_sn",
}

# 换电柜 t_exchange（别名 e；城市/区域/街道/社区经 join t_site 别名 s 关联）
EXCHANGE_COLUMNS = {
    "time": "e.create_time",
    "city": "s.city",
    "area": "s.area",
    "street": "s.street",
    "community": "s.community",
    "agency_id": "e.agency_id",
    "site_id": "e.site_id",
    "brand_id": "e.brand_id",
    "device_sn": "e.device_sn",
    "oem_id": "e.oem_id",                      # 客户(sys_oem.oem_id)
}

# 换电柜实时上报 t_exchange_last_upload（别名 u；客户/城市/网点经 t_exchange x + t_site s 关联）
EXCHANGE_UPLOAD_COLUMNS = {
    "time": "u.last_upload_time",
    "city": "s.city",
    "area": "s.area",
    "street": "s.street",
    "community": "s.community",
    "agency_id": "x.agency_id",
    "site_id": "x.site_id",
    "brand_id": "x.brand_id",
    "device_sn": "u.exchange_sn",
    "oem_id": "u.oem_id",
}

# 电池 t_battery（别名 b；城市/网点无直连列；电池产品经 型号->系列->产品 关联）
# 说明：cb_battery 无 battery_product_id 列，需经 device_type_id 关联 t_battery_model 再经
#      series_id 关联 t_battery_product 得到产品，故此处用子查询模板（{ids} 为产品ID占位符）
BATTERY_COLUMNS = {
    "agency_id": "b.agency_id",
    "brand_id": "b.brand_id",
    "device_sn": "b.device_sn",
    "oem_id": "b.oem_id",
    "battery_product_id": (
        "b.device_type_id IN (SELECT m.device_type_id FROM t_battery_model m "
        "JOIN t_battery_product p ON p.series_id = m.series_id "
        "WHERE p.id IN ({ids}))"
    ),
}

# 财务支出单 t_expense_bill（别名 b）
EXPENSE_COLUMNS = {
    "time": "b.create_time",
    "bu_id": "b.bu_id",
}

# 优惠券 t_coupon（别名 c）
COUPON_COLUMNS = {
    "time": "c.create_time",
    "battery_product_id": "c.battery_product_id",
    "brand_id": "c.battery_brand_id",
}
