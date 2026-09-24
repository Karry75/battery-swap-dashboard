# -*- coding: utf-8 -*-
"""业务库字段值 -> 中文含义（集中定义，供各看板模块共享）

取值域均来自业务库实际 GROUP BY 统计结果，禁止凭猜测扩充。
"""

# 网点状态：cb_site.site_status
SITE_STATUS_CN = {"on": "已开业", "off": "已停业"}

# 网点审核进度：cb_site.audit_progress
AUDIT_PROGRESS_CN = {
    "have_opened": "已开业", "closed": "已关闭", "wait_open": "待开业",
    "wait_install": "待安装", "not_cooperation": "未合作", "wait_audit": "待审核",
}

# 电池状态：cb_battery.battery_status
BATTERY_STATUS_CN = {"none": "未使用", "using": "使用中", "maintain": "维修中", "scrap": "报废"}

# 电池在线状态：cb_battery.online_status
ONLINE_STATUS_CN = {"online": "在线", "offline": "离线"}

# 免押/取电状态：cb_user_exchange_deposit.take_battery_status
DEPOSIT_STATUS_CN = {"init": "未取电", "take": "已取电", "back": "已归还"}

# 电池类型：cb_battery.type
BATTERY_TYPE_CN = {"normal": "正常"}

UNKNOWN_CN = "未知"


def cn(mapping, value, dft="-"):
    """把库中英文枚举值就地映射为中文；未收录值原样返回（不臆造）。"""
    k = "" if value is None else str(value).strip()
    if not k:
        return dft
    return mapping.get(k, k)
