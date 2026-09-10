# 换电运营平台 · 多板块数据看板

面向两轮车换电 / 租车业务的运营数据看板系统。从 AnalyticDB（MySQL 协议）业务库只读抽取
换电柜、电池、用户、网点、销售、财务等数据，汇总为多板块看板；内置**断库容灾缓存**，
业务库不可达时可回放最近一次成功数据，保证看板不白屏。

## 功能板块

| 板块 | 说明 |
|------|------|
| 数据大屏 | 全屏可视化大屏（运营核心指标） |
| 数据总览 | 运营总览 / 城市维度 / 网点维度 / 设备维度 / 财务维度 / 换电密集分布 / 用户车辆密集分布 |
| 用户看板 | 用户数据总览 / 增长分析 / 单用户视图 / 用户分布地图 / 用户基本表 / 实时全量查询 |
| 销售看板 | 销售总览 / 网点销售情况 / 业务销售业绩 / 套餐购买明细 / 协议签约明细 / 名下网点列表 |
| 网点看板 | 网点总览 / 收支对账单 / 网点评估与发展 / 网点基本表 / 网点销售业绩 / 单网点视图 |
| 设备资产看板 | 换电柜 / 电池 / 车辆 / 仓库 / 流通 / 调拨 / 出入库 / 故障 |
| 优惠券看板 | 优惠券发放与核销概览 |
| 财务看板 | 收入趋势 / 支出明细 / 押金明细 |
| 运维看板 | 设备汇总 / 告警明细（电池饿死、断充、烟感、水浸、仓位） |
| 人员看板 | 人员业绩 / 工单 |
| 客服服务台 | 实时查询 / 投诉工单 |
| 深度分析 | 换电高峰 / 首次取电 / 电池龄 / 支出对比 |

## 技术栈

- 后端：Python 3 / Flask（应用工厂 + Blueprint）
- 数据源：AnalyticDB for MySQL（只读，PyMySQL）
- 缓存：SQLite 本地查询缓存（`board_cache.db`，断库回放）
- 用户体系：SQLite 内置用户库（`board.db`，密码哈希 + 角色权限）
- 前端：原生 HTML / CSS / JavaScript + ECharts（本地化，无需外网 CDN）

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 按实际环境填写数据库凭据
python -m scripts.init_db     # 初始化内置用户库（创建初始管理员）
python app.py                 # 启动，默认 http://0.0.0.0:8092
```

浏览器访问 `http://<本机IP>:8092`，使用 `.env` 中配置的管理员账号登录。

## 配置

### 数据库凭据（.env，已在 .gitignore 中排除）

```
DB_HOST=your_host
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_business_db     # 业务库
DB_BASE=your_base_db         # 基础库（客户主数据）
BOARD_HOST=0.0.0.0
BOARD_PORT=8092
SECRET_KEY=随机字符串
ADMIN_USER=admin
ADMIN_PASSWORD=初始管理员密码
```

凭据仅由 `config/settings.py` 在内存中读取，不写入日志、不回显前端、不落库。

### 业务配置（config/config.yaml）

- `database.tables`：逻辑名 → 物理表名映射
- `alarm.battery.hungry.voltage_threshold`：电池饿死判定电压阈值
- `priority`：告警优先级
- `event_type_map`：事件类型 → 业务告警名称

## 断库容灾（核心机制）

业务库不可达时，看板仍可展示**最后一次成功查询的数据**：

1. **稳定缓存 key**：`core/cache.py` 将查询 SQL 与参数归一化（毫秒时间戳字面量替换为固定占位）
   后取 SHA1，保证同一业务查询在不同时刻生成相同 key。
2. **成功即落盘**：`core/db.py` 每次查询成功后将结果 upsert 进本地 SQLite 缓存（上限 3000 条，
   自动淘汰最旧）。
3. **失败即回放**：查询失败时回退最近一次成功结果，并在响应中标记 `cached: true` 及
   `cached_at`；同时对连接失败做短时熔断，避免断库期间每次请求都等待超时。
4. **前端兜底**：`web/js/app.js` 统一请求封装在「网络错误 / 非 JSON / 业务码异常」三种情况下
   回放浏览器 localStorage 中的最后成功结果，并显示降级横幅，不白屏、不报错。

> 断库期间仅能看历史数据；恢复连接后首次加载即自动刷新缓存。

## 角色与权限

| 角色 | 说明 |
|------|------|
| 管理员 admin | 全部数据 + 用户/角色管理 |
| 客户经理 manager | 仅查看其客户范围（oem_ids）内数据 |
| 查看者 viewer | 只读看板 |

权限点按板块划分（如 `overview:view`、`user:view`、`sales:view`…），支持在「角色管理」中自定义角色。

## API 概览

| 分组 | 路径前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/auth/*` | 登录 / 登出 / 当前用户 |
| 总览 | `/api/overview/*`、`/api/dashboard/*` | 运营总览、趋势、城市/网点/设备/财务维度 |
| 用户 | `/api/users/*` | 用户汇总、增长、明细、分层、协议、订单 |
| 销售 | `/api/sales/*` | 销售汇总、网点排名、员工业绩、套餐、协议 |
| 网点 | `/api/sites/*` | 网点汇总、列表、订单 |
| 设备资产 | `/api/assets/*`、`/api/devices/*` | 换电柜、电池、调拨、工单 |
| 财务 | `/api/finance/*` | 收支趋势、支出明细、押金 |
| 运维/告警 | `/api/alarms`、`/api/service/*` | 告警明细、服务台查询、投诉 |
| 分析 | `/api/insights/*` | 换电高峰、首次取电、电池龄 |
| 大屏 | `/api/bigscreen/*` | 大屏聚合数据 |
| 系统 | `/api/health`、`/api/filters/options` | 连通性检查、筛选项字典 |

## 目录结构

```
board/
├── app.py                  # Flask 入口（应用工厂）
├── config/                 # settings.py（.env 加载）+ config.yaml（业务配置）
├── core/                   # db 只读访问层 / cache 断库缓存 / 各板块统计逻辑
├── auth/                   # 内置用户库：用户、角色、权限、登录装饰器
├── api/routes.py           # REST API
├── web/                    # 前端（index.html / js / css / ECharts）
└── scripts/init_db.py      # 初始化用户库
```

## 安全说明

- 数据库凭据仅存于 `.env`，代码零硬编码，日志与前端不回显
- 内置用户库为独立 SQLite，密码哈希存储，与业务库凭据隔离
- 业务数据缓存与用户库均已在 `.gitignore` 中排除，不会被提交
- 服务默认监听 0.0.0.0，建议通过防火墙/白名单限制访问来源；公网部署请前置 HTTPS

## 许可

内部业务系统源码，未附带开源许可，请勿外传。
