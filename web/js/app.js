/* 换电运营平台 - 前端逻辑（SPA：分组菜单 + 全板块路由） */
const ALARM_META = {
  hungry:        { name: '电池饿死',     prio: 1, cls: 'tag-p0' },
  unrecognized:  { name: '电池无法识别', prio: 1, cls: 'tag-p0' },
  break_charge:  { name: '电池断充',     prio: 2, cls: 'tag-p1' },
  smoke:         { name: '烟感告警',     prio: 1, cls: 'tag-p0' },
  flooded:       { name: '水浸告警',     prio: 1, cls: 'tag-p0' },
  slot:          { name: '仓位告警',     prio: 2, cls: 'tag-p1' },
};
const DEVICE_NAMES = { battery: '电池', exchange: '换电柜' };

/* alarm-stats 接口返回 dict（如 {hungry:n, ..., total:n}），转为数组并剔除 total */
function dictToArr(d) {
  return Object.entries(d || {}).filter(([k]) => k !== 'total').map(([type, count]) => ({ type, count }));
}

/* 数据库不可达时的统一错误提示 HTML */
function dbErrorHtml(e) {
  const msg = String((e && e.message) || '');
  const dbDown = /ConnectionError|OperationalError|Can't connect|connect(ed|ion) timed|数据库|Lock wait/i.test(msg);
  return dbDown
    ? `<div class="td-empty">
        <div style="font-size:15px;font-weight:600;margin-bottom:8px">业务数据库连接异常</div>
        <div class="muted">当前无法连接 AnalyticDB 业务库，且本地暂无可用缓存数据。</div>
        <div class="muted" style="margin-bottom:14px">请检查数据库网络（阿里云白名单 / VPN / 专线）后刷新；恢复后首次加载即自动建立本地缓存，断库时可回放。</div>
        <button class="btn btn-primary" onclick="location.reload()">重试</button></div>`
    : `<div class="td-empty">加载失败：${esc(msg)}</div>`;
}

/* ---------- 菜单配置（按旧看板扁平布局：数据总览下平铺各看板，运维看板保留子板块） ---------- */
const PERM_META = [
  { key: 'overview:view', name: '数据总览' },
  { key: 'user:view', name: '用户看板' },
  { key: 'sales:view', name: '销售看板' },
  { key: 'site:view', name: '网点看板' },
  { key: 'asset:view', name: '设备资产看板' },
  { key: 'coupon:view', name: '优惠券看板' },
  { key: 'dashboard:view', name: '运维看板' },
  { key: 'staff:view', name: '人员看板' },
  { key: 'finance:view', name: '财务看板' },
  { key: 'service:view', name: '客服服务台' },
  { key: 'analysis:view', name: '深度分析' },
  { key: 'alarm:handle', name: '告警处理' },
  { key: 'admin:user', name: '用户/角色管理' },
];
const MENUS = [
  { key: 'bigscreen', name: '数据大屏', component: 'bigscreen', icon: '📊' },
  {
    key: 'overview', name: '数据总览', type: 'group', icon: '📈', perm: 'overview:view', children: [
      { key: 'ops-overview', name: '运营总览', component: 'overview', perm: 'overview:view' },
      { key: 'city-dim', name: '城市维度', component: 'cityDim', perm: 'overview:view' },
      { key: 'site-dim', name: '网点维度', component: 'siteDim', perm: 'overview:view' },
      { key: 'device-dim', name: '设备维度', component: 'deviceDim', perm: 'overview:view' },
      { key: 'finance-dim', name: '财务维度', component: 'financeDim', perm: 'overview:view' },
      { key: 'exchange-heat', name: '换电密集分布', component: 'exchangeHeat', perm: 'overview:view' },
      { key: 'user-bike-heat', name: '用户车辆密集分布', component: 'userBikeHeat', perm: 'overview:view' },
    ],
  },
  {
    key: 'user', name: '用户看板', type: 'group', icon: '👥', perm: 'user:view', children: [
      { key: 'user-overview', name: '用户数据总览', component: 'userOverview', perm: 'user:view' },
      { key: 'user-growth', name: '增长分析', component: 'userGrowth', perm: 'user:view' },
      { key: 'user-detail', name: '单用户视图', component: 'userDetail', perm: 'user:view' },
      { key: 'user-map', name: '用户分布地图', component: 'userMap', perm: 'user:view' },
      { key: 'user-tables', name: '用户基本表', component: 'userTables', perm: 'user:view' },
      { key: 'user-query', name: '实时全量查询', component: 'userQuery', perm: 'user:view' },
    ],
  },
  {
    key: 'sales', name: '销售看板', type: 'group', icon: '💰', perm: 'sales:view', children: [
      { key: 'sales-overview', name: '销售总览', component: 'salesBoard', perm: 'sales:view' },
      { key: 'sales-site', name: '网点销售情况', component: 'salesSite', perm: 'sales:view' },
      { key: 'sales-staff', name: '业务销售业绩', component: 'salesStaff', perm: 'sales:view' },
      { key: 'sales-package', name: '套餐购买明细', component: 'salesPackage', perm: 'sales:view' },
      { key: 'sales-agreement', name: '协议签约明细', component: 'salesAgreement', perm: 'sales:view' },
      { key: 'sales-site-list', name: '名下网点列表', component: 'salesSiteList', perm: 'sales:view' },
    ],
  },
  {
    key: 'site', name: '网点看板', type: 'group', icon: '🏪', perm: 'site:view', children: [
      { key: 'site-overview', name: '网点总览', component: 'siteBoard', perm: 'site:view' },
      { key: 'site-statement', name: '网点收支对账单', component: 'siteStatement', perm: 'site:view' },
      { key: 'site-eval', name: '网点评估与发展', component: 'siteEval', perm: 'site:view' },
      { key: 'site-tables', name: '网点基本表', component: 'siteTables', perm: 'site:view' },
      { key: 'site-sales', name: '网点销售业绩', component: 'siteSales', perm: 'site:view' },
      { key: 'site-detail', name: '单网点视图', component: 'siteDetail', perm: 'site:view' },
    ],
  },
  {
    key: 'asset', name: '设备资产看板', type: 'group', icon: '🔋', perm: 'asset:view', children: [
      { key: 'asset-exchange', name: '换电柜', component: 'assetExchange', perm: 'asset:view' },
      { key: 'asset-battery', name: '电池', component: 'assetBattery', perm: 'asset:view' },
      { key: 'asset-bike', name: '车辆', component: 'assetBike', perm: 'asset:view' },
      { key: 'asset-warehouse', name: '仓库', component: 'assetWarehouse', perm: 'asset:view' },
      { key: 'asset-flow', name: '流通', component: 'assetFlow', perm: 'asset:view' },
      { key: 'asset-transfer', name: '调拨', component: 'assetTransfer', perm: 'asset:view' },
      { key: 'asset-inout', name: '出入库', component: 'assetInout', perm: 'asset:view' },
      { key: 'asset-fault', name: '故障', component: 'assetFault', perm: 'asset:view' },
    ],
  },
  { key: 'coupon', name: '优惠券看板', component: 'couponBoard', icon: '🎟️', perm: 'coupon:view' },
  {
    key: 'ops', name: '运维看板', type: 'group', icon: '🛠️', perm: 'dashboard:view', children: [
      { key: 'dashboard', name: '设备总览看板', component: 'dashboard', perm: 'dashboard:view' },
      { key: 'exchange', name: '换电柜管理', component: 'exchange', perm: 'dashboard:view' },
      { key: 'battery', name: '电池管理', component: 'battery', perm: 'dashboard:view' },
      { key: 'alarm', name: '设备预警', component: 'alarm', perm: 'dashboard:view' },
    ],
  },
  { key: 'staff', name: '人员看板', component: 'staffBoard', icon: '🧑‍💼', perm: 'staff:view' },
  { key: 'finance', name: '财务看板', component: 'financeBoard', icon: '💳', perm: 'finance:view' },
  { key: 'service-desk', name: '客服服务台', component: 'serviceDesk', icon: '📞', perm: 'service:view' },
  { key: 'deep-analysis', name: '深度分析', component: 'deepAnalysis', icon: '🔍', perm: 'analysis:view' },
  { key: 'risk-monitor', name: '风险监控', component: 'riskMonitor', icon: '⚠️' },
  { key: 'decision', name: '经营决策', component: 'decision', icon: '🧭' },
  { key: 'command', name: '大屏指挥', component: 'command', icon: '🖥️' },
];

/* ---------- 统一多维筛选（board_filter_upgrade） ----------
  每个数据菜单声明可用筛选维度；筛选值存于 window.__filters[routeKey]，
  渲染时在页面顶部生成筛选工具栏，applyFilters 后重新 render()，
  api() 对 /api/* GET 请求自动把当前菜单的筛选参数拼入 URL，
  后端 FilterSet 落到 SQL WHERE 聚合，而非前端假过滤。 */
const FILTER_META = {
  time:       { label: '时间范围',   type: 'range', k: ['start', 'end'] },
  op_time:    { label: '开业/关闭',  type: 'range', k: ['op_start', 'op_end'] },
  act_time:   { label: '激活时间',   type: 'range', k: ['act_start', 'act_end'] },
  stop_time:  { label: '终止时间',   type: 'range', k: ['stop_start', 'stop_end'] },
  city:       { label: '城市',       type: 'select', k: 'city',         src: 'cities' },
  area:       { label: '区域',       type: 'select', k: 'area',         src: 'areas' },
  street:     { label: '街道',       type: 'select', k: 'street',       src: 'streets' },
  community:  { label: '社区',       type: 'select', k: 'community',    src: 'communities' },
  agency:     { label: '代理商',     type: 'select', k: 'agency_id',    src: 'agencies' },
  battery_product: { label: '电池产品', type: 'select', k: 'battery_product_id', src: 'battery_products' },
  site:       { label: '网点',       type: 'select', k: 'site_id',      src: 'sites' },
  employee:   { label: '业务员',     type: 'select', k: 'employee_id',  src: 'employees' },
  merchant:   { label: '商户',       type: 'select', k: 'merchant_id',  src: 'merchants' },
  brand:      { label: '电池品牌',   type: 'select', k: 'brand_id',     src: 'battery_brands' },
  bu:         { label: '事业线',     type: 'select', k: 'bu_id',        src: 'bus_units' },
  user_phone: { label: '手机号',     type: 'text',   k: 'user_phone',   ph: '输入手机号' },
  agreement_id: { label: '协议ID',   type: 'text',   k: 'agreement_id', ph: '输入协议ID' },
  device_sn:  { label: '设备SN',     type: 'text',   k: 'device_sn',    ph: '输入设备SN' },
};
const TIME_KEYS = ['start', 'end', 'op_start', 'op_end', 'act_start', 'act_end', 'stop_start', 'stop_end'];
const FILTER_SKIP = ['/api/auth/', '/api/admin/', '/api/filters/options', '/api/health', '/api/devices/export'];

const FILTER_DEFS = {
  bigscreen: ['city', 'agency', 'battery_product', 'site', 'time'],
  'ops-overview': ['city', 'area', 'agency', 'battery_product', 'site', 'time'],
  'city-dim': ['city', 'area', 'agency', 'battery_product', 'site', 'time'],
  'site-dim': ['city', 'area', 'street', 'agency', 'site', 'time'],
  'device-dim': ['city', 'area', 'agency', 'battery_product', 'site', 'time'],
  'finance-dim': ['time'],
  'exchange-heat': ['city', 'area', 'agency', 'site', 'time'],
  'user-bike-heat': ['city', 'area', 'agency', 'time'],
  'user-overview': ['city', 'area', 'agency', 'battery_product', 'site', 'user_phone', 'agreement_id', 'time', 'act_time', 'stop_time'],
  'user-growth': ['time'],
  'user-detail': ['user_phone'],
  'user-map': ['city', 'area', 'agency', 'time'],
  'user-tables': ['city', 'area', 'agency', 'user_phone', 'time'],
  'user-query': ['user_phone', 'agreement_id', 'time'],
  'sales-overview': ['city', 'area', 'agency', 'battery_product', 'site', 'employee', 'time'],
  'sales-site': ['city', 'area', 'agency', 'site', 'time'],
  'sales-staff': ['city', 'agency', 'employee', 'time'],
  'sales-package': ['city', 'agency', 'site', 'employee', 'merchant', 'time'],
  'sales-agreement': ['city', 'agency', 'battery_product', 'site', 'employee', 'merchant', 'agreement_id', 'user_phone', 'time', 'act_time', 'stop_time'],
  'sales-site-list': ['city', 'area', 'agency', 'site', 'time'],
  'site-overview': ['city', 'area', 'street', 'community', 'agency', 'merchant', 'site', 'time', 'op_time'],
  'site-statement': ['time'],
  'site-eval': ['city', 'area', 'agency', 'site', 'time'],
  'site-tables': ['city', 'area', 'street', 'community', 'agency', 'merchant', 'site', 'time', 'op_time'],
  'site-sales': ['city', 'area', 'agency', 'site', 'time'],
  'site-detail': ['site', 'time'],
  'asset-exchange': ['city', 'area', 'street', 'community', 'agency', 'site', 'device_sn', 'brand', 'time'],
  'asset-battery': ['city', 'area', 'agency', 'battery_product', 'brand', 'device_sn', 'time'],
  'asset-bike': ['city', 'area', 'agency', 'time'],
  'asset-warehouse': ['device_sn', 'time'],
  'asset-flow': ['time'],
  'asset-transfer': ['time'],
  'asset-inout': ['time'],
  'asset-fault': ['city', 'area', 'agency', 'site', 'time'],
  coupon: ['battery_product', 'brand', 'time'],
  dashboard: ['city', 'area', 'agency', 'battery_product', 'site', 'time'],
  exchange: ['city', 'area', 'agency', 'site', 'device_sn', 'time'],
  battery: ['city', 'area', 'agency', 'battery_product', 'brand', 'device_sn', 'time'],
  alarm: ['city', 'area', 'device_sn', 'time'],
  staff: ['city', 'area', 'agency', 'site', 'time'],
  finance: ['bu', 'time'],
  'service-desk': ['city', 'agency', 'user_phone', 'agreement_id', 'time'],
  'deep-analysis': ['city', 'agency', 'battery_product', 'site', 'time'],
  'risk-monitor': ['city', 'area', 'agency', 'site', 'time'],
  decision: ['city', 'area', 'agency', 'battery_product', 'site', 'time'],
  command: ['city', 'area', 'agency', 'site', 'time'],
};

window.__filters = {};
window.__filterOptions = {};
let __filterOptPromise = null;

function withFilter(url) {
  if (!url.startsWith('/api/')) return url;
  if (FILTER_SKIP.some(p => url.startsWith(p))) return url;
  const key = window.__routeKey || '';
  const vals = window.__filters[key];
  if (!vals) return url;
  const existing = new Set((url.split('?')[1] || '').split('&').map(s => s.split('=')[0]).filter(Boolean));
  const pairs = [];
  Object.entries(vals).forEach(([k, v]) => {
    v = String(v == null ? '' : v).trim();
    if (v === '' || existing.has(k)) return;
    if (TIME_KEYS.includes(k) && v.includes('T')) {
      v = v.replace('T', ' ');
      if (v.length <= 16) v += ':00';
    }
    pairs.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
  });
  if (!pairs.length) return url;
  return url + (url.includes('?') ? '&' : '?') + pairs.join('&');
}

async function ensureFilterOptions() {
  if (!__filterOptPromise) {
    __filterOptPromise = api('/api/filters/options')
      .then(d => { Object.assign(window.__filterOptions, d || {}); })
      .catch(() => {});
  }
  return __filterOptPromise;
}

function filterBarHtml(key, defs) {
  const vals = window.__filters[key] || {};
  const rows = defs.map(d => {
    const m = FILTER_META[d];
    if (!m) return '';
    if (m.type === 'range') {
      return `<input type="datetime-local" class="input-sm" id="flt_${key}_${m.k[0]}" value="${esc(vals[m.k[0]] || '')}" title="${m.label}起">
              <span class="muted" style="line-height:30px">~</span>
              <input type="datetime-local" class="input-sm" id="flt_${key}_${m.k[1]}" value="${esc(vals[m.k[1]] || '')}" title="${m.label}止">`;
    }
    if (m.type === 'text') {
      return `<input class="input-sm" id="flt_${key}_${m.k}" placeholder="${esc(m.label)}" value="${esc(vals[m.k] || '')}">`;
    }
    const opts = window.__filterOptions[m.src] || [];
    return `<select id="flt_${key}_${m.k}"><option value="">${esc(m.label)}：全部</option>${opts.map(o =>
      `<option value="${esc(o.value)}" ${String(vals[m.k]) === String(o.value) ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
  }).join('');
  return `<div class="filters" style="flex-wrap:wrap;gap:6px;margin-bottom:10px">${rows}
    <button class="btn btn-primary" onclick="applyFilters('${key}')">应用筛选</button>
    <button class="btn btn-ghost-dark" onclick="resetFilters('${key}')">重置</button>
    <span class="muted" style="line-height:30px">筛选基于库真实字段，落入后端 SQL 聚合</span></div>`;
}

window.applyFilters = function (key) {
  const defs = FILTER_DEFS[key] || [];
  const vals = {};
  defs.forEach(d => {
    const m = FILTER_META[d];
    if (!m) return;
    if (m.type === 'range') m.k.forEach(k => { const el = document.getElementById('flt_' + key + '_' + k); vals[k] = el ? el.value.trim() : ''; });
    else { const el = document.getElementById('flt_' + key + '_' + m.k); vals[m.k] = el ? el.value.trim() : ''; }
  });
  window.__filters[key] = vals;
  render();
};
window.resetFilters = function (key) {
  window.__filters[key] = {};
  render();
};

let currentUser = null;
let charts = {};
let pageState = {};

/* ---------- 前端本地缓存（最后一次成功数据兜底） ----------
  成功拉取的 GET 接口数据按 URL 持久化到 localStorage；
  此后接口超时/网络断开/返回异常态时，回放最后一次成功数据，
  避免离线或断库时板块空白或显示"数据库异常"。 */
const LS_CACHE_KEY = 'board_api_cache_v1';
const LS_CACHE_MAX = 600;
const LS_CACHE_MAX_BYTES = 4 * 1024 * 1024;

function lsCacheRead(url) {
  try {
    const raw = localStorage.getItem(LS_CACHE_KEY);
    if (!raw) return null;
    const map = JSON.parse(raw);
    const hit = map[url];
    if (!hit) return null;
    return { data: hit.d, at: hit.t };
  } catch (e) { return null; }
}

function lsCacheWrite(url, data) {
  try {
    let map = {};
    try { map = JSON.parse(localStorage.getItem(LS_CACHE_KEY)) || {}; } catch (e) { map = {}; }
    map[url] = { d: data, t: new Date().toLocaleString('zh-CN', { hour12: false }) };
    let keys = Object.keys(map);
    // 条目超限：保留最近写入的（全局时间倒序裁剪）
    if (keys.length > LS_CACHE_MAX) {
      keys = keys.sort((a, b) => (map[a].t < map[b].t ? 1 : -1));
      keys.slice(LS_CACHE_MAX).forEach(k => delete map[k]);
    }
    try {
      localStorage.setItem(LS_CACHE_KEY, JSON.stringify(map));
    } catch (e) {
      // 容量超限（如 localStorage 受限）：降级只保留最新一条，尽量不丢看板
      const cur = map[url];
      localStorage.setItem(LS_CACHE_KEY, JSON.stringify({ [url]: cur }));
    }
  } catch (e) { /* 静默失败，不影响主流程 */ }
}

async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const cacheable = method === 'GET';
  if (cacheable) path = withFilter(path);
  let resp;
  try {
    resp = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch (err) {
    // 网络断开 / 超时 / 无法解析：GET 接口回放最后一次成功数据
    if (!cacheable) throw err;
    const cached = lsCacheRead(path);
    if (cached) {
      showBanner('离线或接口异常，当前展示最后一次成功数据（' + cached.at + '）');
      return cached.data;
    }
    throw err;
  }
  let json;
  try {
    json = await resp.json();
  } catch (err) {
    // 网关/服务异常返回非 JSON（如 502 HTML）：GET 接口回放最后一次成功数据
    if (!cacheable) throw err;
    const cached = lsCacheRead(path);
    if (cached) {
      showBanner('接口异常，当前展示最后一次成功数据（' + cached.at + '）');
      return cached.data;
    }
    throw err;
  }
  if (resp.status === 401) { window.location.href = '/login.html'; throw new Error('未登录'); }
  if (json.code !== 0) {
    if (!cacheable) throw new Error(json.msg || '请求失败');
    const cached = lsCacheRead(path);
    if (cached) {
      showBanner('接口异常（' + (json.msg || json.code) + '），当前展示最后一次成功数据（' + cached.at + '）');
      return cached.data;
    }
    throw new Error(json.msg || '请求失败');
  }
  // 成功：写本地缓存（仅 GET）
  if (cacheable) lsCacheWrite(path, json.data);
  if (json.cached) showBanner('业务数据库连接异常，当前展示最近一次缓存数据（' + (json.cached_at || '') + '）');
  return json.data;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function fmtTs(t) {
  if (!t) return '-';
  const n = Number(t);
  if (!n || n <= 0) return '-';
  return new Date(n > 1e12 ? n : n * 1000).toLocaleString('zh-CN', { hour12: false });
}

function showBanner(text) {
  const el = document.getElementById('connBanner');
  if (text) { el.textContent = text; el.style.display = 'block'; }
  else { el.style.display = 'none'; }
}

function tag(text, cls) { return `<span class="tag ${cls}">${esc(text)}</span>`; }
function statusTag(v) { return v === 'online' ? tag('在线', 'tag-ok') : tag('离线', 'tag-off'); }
function money(v) { return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

/* ---------- 菜单渲染 ---------- */
function menuVisible(node) {
  if (node.perm && !(currentUser.permissions || []).includes(node.perm)) return false;
  if (node.children) return node.children.some(menuVisible);
  return true;
}

function flatMenu(nodes, path = []) {
  const out = [];
  nodes.forEach(n => {
    const p = [...path, n];
    if (n.component) out.push({ node: n, path: p });
    if (n.children) out.push(...flatMenu(n.children, p));
  });
  return out;
}

function renderMenu() {
  const nav = document.getElementById('sideNav');
  const current = currentRoute();
  let html = '';
  MENUS.filter(menuVisible).forEach(node => {
    if (node.type === 'group') {
      const hasActive = flatMenu(node.children).some(({ node: n }) => n.key === current.key);
      const open = hasActive || node.key === 'overview';
      html += `<div class="menu-group ${open ? 'open' : ''}">
        <div class="menu-group-title" onclick="groupClick('${node.key}', this)">${esc(node.name)}</div>
        <div class="menu-group-body">${renderMenuItems(node.children, current.key)}</div>
      </div>`;
    } else {
      html += `<div class="menu-item ${node.key === current.key ? 'active' : ''}" onclick="navigate('${node.key}')">
        <span class="menu-text">${esc(node.name)}</span>${node.placeholder ? '<span class="menu-badge">建设中</span>' : ''}</div>`;
    }
  });
  nav.innerHTML = html;
  document.getElementById('userMini').innerHTML = currentUser ? esc(currentUser.display_name || currentUser.username) : '';
}

function renderMenuItems(nodes, activeKey) {
  let html = '';
  nodes.forEach(node => {
    if (node.type === 'group') {
      const hasActive = flatMenu(node.children).some(({ node: n }) => n.key === activeKey);
      html += `<div class="menu-group ${hasActive ? 'open' : ''}">
        <div class="menu-group-title sub" onclick="toggleGroup(this)">${esc(node.name)}</div>
        <div class="menu-group-body">${renderMenuItems(node.children, activeKey)}</div>
      </div>`;
    } else {
      html += `<div class="menu-item ${node.key === activeKey ? 'active' : ''}" onclick="navigate('${node.key}')">
        <span class="menu-text">${esc(node.name)}</span>${node.placeholder ? '<span class="menu-badge">建设中</span>' : ''}</div>`;
    }
  });
  return html;
}

function toggleGroup(el) { el.parentElement.classList.toggle('open'); }

function groupClick(key, el) {
  el.parentElement.classList.toggle('open');
  const found = flatMenu(MENUS).find(x => x.node.key === key);
  if (found && found.node.component) navigate(key);
}

function currentRoute() {
  const h = location.hash.replace(/^#\//, '') || 'dashboard';
  return { key: h };
}

function navigate(key) {
  location.hash = '/' + key;
}

window.addEventListener('hashchange', render);
window.toggleGroup = toggleGroup;
window.navigate = navigate;

/* ---------- 通用组件 ---------- */
function kpiGrid(cards) {
  return `<div class="kpi-grid">${cards.map(c => `
    <div class="kpi"><div class="label">${esc(c.label)}</div>
    <div class="value ${c.cls || ''}">${esc(c.value)}</div></div>`).join('')}</div>`;
}

function filterBar(fields) {
  return `<div class="filters">${fields.map(f => {
    if (f.type === 'select') return `<select id="${f.id}" onchange="${f.onchange || ''}">${(f.options || []).map(o => `<option value="${o[0]}">${esc(o[1])}</option>`).join('')}</select>`;
    return `<input class="${f.sm ? 'input-sm' : 'input'}" id="${f.id}" placeholder="${esc(f.placeholder || '')}" value="${esc(f.value || '')}" onkeydown="if(event.key==='Enter'){${f.onenter || ''}}">`;
  }).join('')}
  <button class="btn btn-primary" onclick="${fields[0].onsearch || ''}">查询</button>
  <button class="btn btn-ghost-dark" onclick="${fields[0].onexport || ''}">导出</button></div>`;
}

function pager(total, page, pageSize, fn) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return `<div class="pager"><span>共 ${total} 条 / 第 ${page}/${pages} 页</span>
    <button class="btn btn-ghost-dark" ${page <= 1 ? 'disabled' : ''} onclick="${fn}(${page - 1})">上一页</button>
    <button class="btn btn-ghost-dark" ${page >= pages ? 'disabled' : ''} onclick="${fn}(${page + 1})">下一页</button></div>`;
}

function tableHtml(headers, rows, empty = '暂无数据') {
  if (!rows.length) return `<div class="card"><div class="td-empty">${empty}</div></div>`;
  return `<div class="card table-wrap"><table class="table"><thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function card(title, inner, extra = '') {
  return `<div class="card"><div class="card-head"><h3>${title}</h3>${extra}</div>${inner}</div>`;
}

function chartBox(title, height = 300) {
  const id = 'chart_' + Math.random().toString(36).slice(2, 8);
  setTimeout(() => { const el = document.getElementById(id); if (el) el._chartTitle = title; }, 0);
  return `<div class="card"><div class="card-head"><h3>${title}</h3></div><div id="${id}" class="chart" style="height:${height}px"></div></div>`;
}

function drawChart(elId, option) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!charts[elId]) charts[elId] = echarts.init(el);
  charts[elId].setOption(option, true);
}

function disposeCharts() {
  Object.values(charts).forEach(c => c.dispose());
  charts = {};
}

/* ---------- 渲染入口 ---------- */
async function render() {
  const route = currentRoute();
  window.__routeKey = route.key;
  document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
  renderMenu();
  const page = document.getElementById('page');
  /* 统一筛选工具栏：所有带 FILTER_DEFS 的菜单顶部注入，选择后 applyFilters 重渲染 */
  const defs = FILTER_DEFS[route.key] || [];
  let host = document.getElementById('filterBarHost');
  if (!host) { host = document.createElement('div'); host.id = 'filterBarHost'; page.before(host); }
  if (defs.length) { try { await ensureFilterOptions(); } catch (e) {} host.innerHTML = filterBarHtml(route.key, defs); }
  else host.innerHTML = '';
  page.innerHTML = '<div class="loading">加载中...</div>';
  showBanner('');
  const comp = routeComp(route.key);
  document.getElementById('breadcrumb').textContent = nodeName(route.key);
  disposeCharts();
  try {
    if (!comp) {
      const names = nodeName(route.key).split(' / ');
      const title = names.length > 1 ? names[names.length - 1] : '';
      return page.innerHTML = placeholderHtml(title, title ? '该板块内容待补充，可继续提供需求' : '');
    }
    await comp.component(page, route.key);
  } catch (e) {
    console.error(e);
    page.innerHTML = dbErrorHtml(e);
  }
}

function routeComp(key) {
  const map = {};
  flatMenu(MENUS).forEach(({ node }) => { if (node.component) map[node.key] = node.component; });
  return map[key] ? { component: COMPONENTS[map[key]], breadcrumb: nodeName(key) } : null;
}

function nodeName(key) {
  const found = flatMenu(MENUS).find(x => x.node.key === key);
  if (!found) return '换电运营平台';
  return found.path.map(p => p.name).join(' / ');
}

function placeholderHtml(title, sub) {
  return `<div class="placeholder-card"><div class="placeholder-icon">🚧</div>
    <div class="placeholder-title">${esc(title || '建设中')}</div>
    <div class="placeholder-sub">${esc(sub || '该板块内容待补充，可继续提供需求')}</div></div>`;
}

/* ================= 板块渲染器 ================= */

function bsShort(city) {
return String(city || '').replace(/^(北京市|上海市|天津市|重庆市|河北省|山西省|辽宁省|吉林省|黑龙江省|江苏省|浙江省|安徽省|福建省|江西省|山东省|河南省|湖北省|湖南省|广东省|海南省|四川省|贵州省|云南省|陕西省|甘肃省|青海省|台湾省|内蒙古自治区|广西壮族自治区|西藏自治区|宁夏回族自治区|新疆维吾尔自治区|香港特别行政区|澳门特别行政区)/, '') || city;
}
const COMPONENTS = {

  /* ---- 数据总览 ---- */
  async overview(el) {
    const [s, trend, city, regions, device] = await Promise.all([
      api('/api/overview/summary'), api('/api/overview/monthly-trend?months=12'),
      api('/api/overview/city-dimension'), api('/api/overview/regions'),
      api('/api/overview/device-dimension'),
    ]);
    const d = s.devices || {};
    el.innerHTML = kpiGrid([
      { label: '累计用户', value: s.total_users, cls: 'blue' },
      { label: '换电柜数', value: d.exchange_total, cls: 'blue' },
      { label: '电池总数', value: d.battery_total, cls: 'blue' },
      { label: '今日换电单量', value: s.today_exchange, cls: 'ok' },
      { label: '今日换电收入', value: '¥' + money(s.today_fee), cls: 'ok' },
      { label: '今日活跃用户', value: s.today_users, cls: 'blue' },
      { label: '今日新增用户', value: s.today_new_users, cls: 'ok' },
      { label: '昨日换电单量', value: s.yesterday_exchange, cls: 'warn' },
    ]) + `<div class="grid-2">` + chartBox('近12月换电趋势', 300) + chartBox('城市分布TOP10', 300) + `</div>`
      + `<div class="grid-2">` + chartBox('区域网点分布', 260) + chartBox('设备在线状态', 260) + `</div>`
      + card('区域维度明细', tableHtml(['城市', '用户数', '换电柜', '近30天换电', '近30天活跃用户', '近30天里程(km)'],
        (regions || []).slice(0, 20).map(c => [esc(c.city || '-'), c.users, c.exchange_count, c.exchange_30d, c.active_users_30d, money(c.mileage_30d)])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: { trigger: 'axis' }, grid: { left: 60, right: 60, bottom: 30 },
        xAxis: { type: 'category', data: trend.map(t => t.month) },
        yAxis: [{ type: 'value' }, { type: 'value' }],
        series: [
          { name: '换电单量', type: 'bar', data: trend.map(t => t.exchange_count), itemStyle: { color: '#2563eb' } },
          { name: '收入(元)', type: 'line', yAxisIndex: 1, data: trend.map(t => t.fee), itemStyle: { color: '#16a34a' } },
        ],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: city.slice(0, 10).map(c => c.city) },
        yAxis: { type: 'value' },
        series: [{ name: '换电次数', type: 'bar', data: city.slice(0, 10).map(c => c.exchange_count), itemStyle: { color: '#2563eb' } }],
      });
      drawChart(firstChartId(el, 2), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: regions.slice(0, 10).map(c => c.city) },
        yAxis: { type: 'value' },
        series: [{ name: '换电柜数', type: 'bar', data: regions.slice(0, 10).map(c => c.exchange_count), itemStyle: { color: '#16a34a' } }],
      });
      drawChart(firstChartId(el, 3), {
        tooltip: {},
        series: [{ type: 'pie', radius: '55%', data: [
          { name: '换电柜在线', value: d.exchange_online }, { name: '换电柜离线', value: (d.exchange_total || 0) - (d.exchange_online || 0) },
          { name: '电池在线', value: d.battery_online }, { name: '电池离线', value: (d.battery_total || 0) - (d.battery_online || 0) },
        ] }],
      });
    }, 0);
  },

  /* ---- 用户看板 ---- */
  async userBoard(el) {
    const s = await api('/api/users/summary');
    el.innerHTML = kpiGrid([
      { label: '用户总数', value: s.user_total, cls: 'blue' },
      { label: '本月新增', value: s.new_30d, cls: 'ok' },
      { label: '活跃用户(30d)', value: s.active_30d, cls: 'ok' },
      { label: '协议总数', value: s.agreement_total, cls: 'blue' },
      { label: '押金在押', value: money(s.deposit_total), cls: 'warn' },
      { label: '套餐在用', value: s.rent_total, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('近6月新增用户', 280) + chartBox('城市用户TOP10', 280) + `</div>`
      + `<div class="filters" style="margin-bottom:10px">
          <input class="input" id="user_kw" placeholder="手机号/姓名">
          <button class="btn btn-primary" onclick="loadUserList(1)">查询</button>
          <button class="btn btn-ghost-dark" onclick="loadUserList(1)">刷新</button></div>
        <div id="user_list_box"></div>`;
    const trend = await api('/api/overview/monthly-trend?months=6');
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, xAxis: { type: 'category', data: trend.map(t => t.month) }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: trend.map(t => t.order_count), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, xAxis: { type: 'category', data: (s.city_rank || []).map(c => c.city) }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: (s.city_rank || []).map(c => c.cnt), itemStyle: { color: '#16a34a' } }] });
    }, 0);
    window.loadUserList = async (page = 1) => {
      const kw = document.getElementById('user_kw').value;
      const d = await api(`/api/users/list?page=${page}&keyword=${encodeURIComponent(kw)}`);
      document.getElementById('user_list_box').innerHTML =
        tableHtml(['ID', '手机号', '用户名', '性别', '状态', '城市', '注册时间', '更新时间'],
          d.items.map(u => [u.id, esc(u.phone), esc(u.username || '-'), esc(u.gender || '-'), u.user_status === 'on' ? '正常' : '停用', esc(u.city || '-'), fmtTs(u.create_time), fmtTs(u.update_time)]))
        + pager(d.total, d.page, d.page_size, 'loadUserList');
    };
    loadUserList(1);
  },

  /* ---- 用户看板 · 用户数据总览 ---- */
  async userOverview(el) {
    const [s, lc, cd, tier] = await Promise.all([
      api('/api/users/summary'), api('/api/users/lifecycle'), api('/api/users/city-detail'), api('/api/users/tier'),
    ]);
    const tierRows = [
      ['换电频次-高频(≥30次)', tier.frequency.high, tier.total_users],
      ['换电频次-中频(10~29次)', tier.frequency.medium, tier.total_users],
      ['换电频次-低频(1~9次)', tier.frequency.low, tier.total_users],
      ['消费价值-高(≥50元)', tier.value.high, tier.total_users],
      ['消费价值-中(10~50元)', tier.value.medium, tier.total_users],
      ['消费价值-低(<10元)', tier.value.low, tier.total_users],
    ];
    el.innerHTML = kpiGrid([
      { label: '用户总数', value: s.user_total, cls: 'blue' },
      { label: '本月新增', value: s.new_30d, cls: 'ok' },
      { label: '活跃用户(30d)', value: s.active_30d, cls: 'ok' },
      { label: '协议总数', value: s.agreement_total, cls: 'blue' },
      { label: '押金在押', value: money(s.deposit_total), cls: 'warn' },
      { label: '套餐在用', value: s.rent_total, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('协议生命周期分布', 300) + chartBox('城市用户TOP10', 300) + `</div>`
      + `<div class="grid-2">` + chartBox('用户频次分层(30d)', 280) + chartBox('用户价值分层(30d)', 280) + `</div>`
      + card('用户分层明细(30d)', tableHtml(['分层', '用户数', '占比'],
          tierRows.map(r => [esc(r[0]), r[1], (r[2] ? (r[1] * 100 / r[2]).toFixed(1) : 0) + '%'])))
      + card('城市分布明细', tableHtml(['城市', '用户数', '活跃用户(30d)', '协议数', '近30天换电次数'],
        (cd.items || []).slice(0, 20).map(c => [esc(c.city || '-'), c.users, c.active_users, c.agreements, c.exchange_30d])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: {}, legend: { bottom: 0 },
        series: [{ type: 'pie', radius: '60%', data: (lc.items || []).map(x => ({ name: x.name, value: x.count })) }],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: (s.city_rank || []).slice(0, 10).map(c => c.city) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: (s.city_rank || []).slice(0, 10).map(c => c.cnt), itemStyle: { color: '#2563eb' } }],
      });
      drawChart(firstChartId(el, 2), {
        tooltip: {}, legend: { bottom: 0 },
        series: [{ type: 'pie', radius: '60%', data: [
          { name: '高频', value: tier.frequency.high }, { name: '中频', value: tier.frequency.medium }, { name: '低频', value: tier.frequency.low },
        ] }],
      });
      drawChart(firstChartId(el, 3), {
        tooltip: {}, legend: { bottom: 0 },
        series: [{ type: 'pie', radius: '60%', data: [
          { name: '高价值', value: tier.value.high }, { name: '中价值', value: tier.value.medium }, { name: '低价值', value: tier.value.low },
        ] }],
      });
    }, 0);
  },

  /* ---- 用户看板 · 增长分析 ---- */
  async userGrowth(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <select id="ug_months">
          <option value="6">近6月</option><option value="12">近12月</option>
        </select>
        <button class="btn btn-primary" onclick="loadUserGrowth()">查询</button></div>
      <div id="ug_box"></div>`;
    window.loadUserGrowth = async () => {
      const months = document.getElementById('ug_months').value;
      const d = await api('/api/users/growth?months=' + months);
      document.getElementById('ug_box').innerHTML =
        `<div class="grid-2">` + chartBox('新增用户趋势', 300) + chartBox('注册来源分布', 300) + `</div>`
        + card('月度新增明细', tableHtml(['月份', '新增用户数'],
          (d.trend || []).map(t => [esc(t.month), t.cnt])))
        + card('注册来源分布', tableHtml(['注册来源', '用户数'],
          (d.register_source || []).map(r => [esc(r.register_source || '-'), r.cnt])));
      setTimeout(() => {
        drawChart(firstChartId(document.getElementById('ug_box'), 0), {
          tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
          xAxis: { type: 'category', data: (d.trend || []).map(t => t.month) },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: (d.trend || []).map(t => t.cnt), itemStyle: { color: '#2563eb' } }],
        });
        drawChart(firstChartId(document.getElementById('ug_box'), 1), {
          tooltip: {}, legend: { bottom: 0 },
          series: [{ type: 'pie', radius: '60%', data: (d.register_source || []).map(r => ({ name: r.register_source, value: r.cnt })) }],
        });
      }, 0);
    };
    loadUserGrowth();
  },

  /* ---- 用户看板 · 单用户视图 ---- */
  async userDetail(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="ud_phone" placeholder="手机号">
        <button class="btn btn-primary" onclick="loadUserDetail()">查询</button></div>
      <div id="ud_box"></div>`;
    window.loadUserDetail = async () => {
      const phone = document.getElementById('ud_phone').value.trim();
      const box = document.getElementById('ud_box');
      if (!phone) { box.innerHTML = '<div class="td-empty">请输入手机号</div>'; return; }
      const d = await api('/api/users/detail?phone=' + encodeURIComponent(phone));
      if (!d.user) { box.innerHTML = '<div class="td-empty">未找到该手机号对应的用户</div>'; return; }
      const u = d.user;
      const orders = d.orders || {};
      box.innerHTML =
        kpiGrid([
          { label: '用户ID', value: u.id, cls: 'blue' },
          { label: '手机号', value: u.phone, cls: 'blue' },
          { label: '用户名', value: u.username || '-', cls: 'blue' },
          { label: '客户', value: u.customer_name || '-', cls: 'blue' },
          { label: '累计订单', value: orders.total || 0, cls: 'ok' },
          { label: '30天订单', value: orders.cnt_30d || 0, cls: 'ok' },
          { label: '累计消费', value: '¥' + money(orders.total_fee), cls: 'warn' },
          { label: '30天消费', value: '¥' + money(orders.fee_30d), cls: 'warn' },
        ])
        + card('基本信息', tableHtml(['性别', '城市', '区域', '状态', '注册来源', '注册时间', '更新时间'],
          [[esc(u.gender || '-'), esc(u.city || '-'), esc(u.area || '-'),
            u.user_status === 'on' ? '正常' : '停用', esc(u.register_source || '-'),
            esc(u.create_time || '-'), esc(u.update_time || '-')]]))
        + card('协议列表', tableHtml(['ID', '类型', '城市', '押金状态', '押金(元)', '租期到期', '生效时间', '状态'],
          (d.agreements || []).map(a => [a.id, esc(a.type || '-'), esc(a.sys_city_name || '-'),
            esc(a.deposit_status || '-'), money(a.deposit_real_fee),
            esc(a.rent_expire_time || '-'), esc(a.activation_time || '-'), esc(a.status_text || a.status)])))
        + card('租期卡', tableHtml(['套餐', '有效天数', '永久有效', '卡状态', '到期时间', '创建时间'],
          (d.rents || []).map(r => [esc(r.package_name || '-'), r.valid_days != null ? r.valid_days : '-',
            r.is_permanent_valid == 1 ? '是' : '否', esc(r.status_text || r.card_status),
            esc(r.expire_time || '-'), esc(r.create_time || '-')])));
    };
  },

  /* ---- 用户看板 · 用户分布地图 ---- */
  async userMap(el) {
    const d = await api('/api/users/city-detail');
    el.innerHTML = `<div class="grid-2">` + chartBox('城市用户TOP15', 320) + chartBox('近30天换电TOP15', 320) + `</div>`
      + card('城市分布明细', tableHtml(['城市', '用户数', '活跃用户(30d)', '协议数', '近30天换电次数'],
        (d.items || []).map(c => [esc(c.city || '-'), c.users, c.active_users, c.agreements, c.exchange_30d])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: (d.items || []).slice(0, 15).map(c => c.city), axisLabel: { rotate: 30 } },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: (d.items || []).slice(0, 15).map(c => c.users), itemStyle: { color: '#2563eb' } }],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: (d.items || []).slice(0, 15).map(c => c.city), axisLabel: { rotate: 30 } },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: (d.items || []).slice(0, 15).map(c => c.exchange_30d), itemStyle: { color: '#16a34a' } }],
      });
    }, 0);
  },

  /* ---- 用户看板 · 用户基本表 ---- */
  async userTables(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="ut_kw" placeholder="手机号/姓名">
        <select id="ut_city"><option value="">全部城市</option></select>
        <button class="btn btn-primary" onclick="loadUserTables(1)">查询</button>
        <button class="btn btn-ghost-dark" onclick="loadUserTables(1)">刷新</button></div>
      <div id="ut_box"></div>`;
    const d0 = await api('/api/users/city-detail');
    const citySel = document.getElementById('ut_city');
    (d0.items || []).slice(0, 50).forEach(c => { const o = document.createElement('option'); o.value = c.city; o.textContent = c.city; citySel.appendChild(o); });
    window.loadUserTables = async (page = 1) => {
      const kw = document.getElementById('ut_kw').value;
      const city = document.getElementById('ut_city').value;
      const d = await api(`/api/users/list?page=${page}&keyword=${encodeURIComponent(kw)}&city=${encodeURIComponent(city)}`);
      document.getElementById('ut_box').innerHTML =
        tableHtml(['ID', '手机号', '用户名', '性别', '状态', '城市', '注册来源', '注册时间', '更新时间'],
          d.items.map(u => [u.id, esc(u.phone), esc(u.username || '-'), esc(u.gender || '-'),
            u.user_status === 'on' ? '正常' : '停用', esc(u.city || '-'), esc(u.register_source || '-'),
            esc(u.create_time || '-'), esc(u.update_time || '-')]))
        + pager(d.total, d.page, d.page_size, 'loadUserTables');
    };
    loadUserTables(1);
  },

  /* ---- 用户看板 · 实时全量查询 ---- */
  async userQuery(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="uq_kw" placeholder="手机号/姓名">
        <button class="btn btn-primary" onclick="loadUserQueryList(1)">用户</button>
        <button class="btn btn-ghost-dark" onclick="loadUserQueryAgreements(1)">协议</button>
        <button class="btn btn-ghost-dark" onclick="loadUserQueryRents(1)">租期卡</button>
        <button class="btn btn-ghost-dark" onclick="loadUserQueryOrders(1)">订单</button></div>
      <div id="uq_box"></div>`;
    window.loadUserQueryList = async (page = 1) => {
      const kw = document.getElementById('uq_kw').value;
      const d = await api(`/api/users/list?page=${page}&keyword=${encodeURIComponent(kw)}`);
      document.getElementById('uq_box').innerHTML =
        tableHtml(['ID', '手机号', '用户名', '性别', '状态', '城市', '注册来源', '注册时间'],
          d.items.map(u => [u.id, esc(u.phone), esc(u.username || '-'), esc(u.gender || '-'),
            u.user_status === 'on' ? '正常' : '停用', esc(u.city || '-'), esc(u.register_source || '-'),
            esc(u.create_time || '-')]))
        + pager(d.total, d.page, d.page_size, 'loadUserQueryList');
    };
    window.loadUserQueryAgreements = async (page = 1) => {
      const kw = document.getElementById('uq_kw').value;
      const d = await api(`/api/users/agreements?page=${page}&user_phone=${encodeURIComponent(kw)}`);
      document.getElementById('uq_box').innerHTML =
        tableHtml(['ID', '用户', '手机号', '城市', '押金状态', '租期到期', '生效时间', '状态'],
          d.items.map(a => [a.id, esc(a.user_name || '-'), esc(a.user_phone || '-'), esc(a.sys_city_name || '-'),
            esc(a.deposit_status || '-'), esc(a.rent_expire_time || '-'), esc(a.activation_time || '-'), esc(a.status_text || a.status)]))
        + pager(d.total, d.page, d.page_size, 'loadUserQueryAgreements');
    };
    window.loadUserQueryRents = async (page = 1) => {
      const kw = document.getElementById('uq_kw').value;
      const d = await api(`/api/users/rents?page=${page}&user_phone=${encodeURIComponent(kw)}`);
      document.getElementById('uq_box').innerHTML =
        tableHtml(['套餐', '有效天数', '永久有效', '卡状态', '到期时间', '创建时间'],
          d.items.map(r => [esc(r.package_name || '-'), r.valid_days != null ? r.valid_days : '-',
            r.is_permanent_valid == 1 ? '是' : '否', esc(r.status_text || r.card_status),
            esc(r.expire_time || '-'), esc(r.create_time || '-')]))
        + pager(d.total, d.page, d.page_size, 'loadUserQueryRents');
    };
    window.loadUserQueryOrders = async (page = 1) => {
      const kw = document.getElementById('uq_kw').value;
      const d = await api(`/api/users/orders?page=${page}&user_phone=${encodeURIComponent(kw)}`);
      document.getElementById('uq_box').innerHTML =
        tableHtml(['订单号', '用户', '手机号', '城市', '网点', '实付(元)', '状态', '首次', '里程', '时间'],
          d.items.map(o => [o.id, esc(o.take_user_name || '-'), esc(o.take_user_phone || '-'),
            esc(o.sys_city_name || '-'), esc(o.site_name || '-'), money(o.real_pay_price),
            esc(o.order_status || '-'), o.is_first_take == 1 ? '是' : '否',
            o.mileage != null ? o.mileage : '-', fmtTs(o.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadUserQueryOrders');
    };
    loadUserQueryList(1);
  },

  /* ---- 销售看板 ---- */
  async salesBoard(el) {
    const [s, siteRank, staffRank] = await Promise.all([
      api('/api/sales/summary'), api('/api/sales/site-rank?limit=15'), api('/api/sales/staff-rank?limit=15'),
    ]);
    el.innerHTML = kpiGrid([
      { label: '近30天换电单量', value: s.exchange_count, cls: 'blue' },
      { label: '近30天换电收入', value: '¥' + money(s.exchange_fee), cls: 'ok' },
      { label: '近30天套餐服务费', value: '¥' + money(s.service_order_fee), cls: 'ok' },
      { label: '近30天新增协议', value: s.new_agreement, cls: 'blue' },
      { label: '近30天套餐单量', value: s.service_order_count, cls: 'warn' },
    ]) + `<div class="grid-2">` + chartBox('网点销售TOP15', 320) + chartBox('业务员签约TOP15', 320) + `</div>`
      + card('网点销售排行', tableHtml(['排名', '网点', '换电单量', '收入(元)'],
        siteRank.map((r, i) => [i + 1, esc(r.site_name), r.exchange_count, money(r.fee)])))
      + card('业务员签约排行', tableHtml(['排名', '业务员', '签约数'],
        staffRank.map((r, i) => [i + 1, esc(r.business_name || '未知'), r.agreement_count])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, xAxis: { type: 'category', data: siteRank.map(r => r.site_name) }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: siteRank.map(r => r.exchange_count), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, xAxis: { type: 'category', data: staffRank.map(r => r.business_name || '未知') }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: staffRank.map(r => r.agreement_count), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 网点看板 ---- */
  async siteBoard(el) {
    const s = await api('/api/sites/summary');
    el.innerHTML = kpiGrid([
      { label: '网点总数', value: s.site_total, cls: 'blue' },
      { label: '在营网点', value: s.site_open, cls: 'ok' },
      { label: '停业网点', value: s.site_closed, cls: 'warn' },
      { label: '独立电表', value: s.site_meter, cls: 'blue' },
      { label: '24小时营业', value: s.site_allday, cls: 'ok' },
      { label: '处理中工单', value: s.work_order_doing, cls: 'warn' },
    ]) + `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="site_kw" placeholder="网点名称/编号">
        <select id="site_type"><option value="">全部类型</option><option value="exchange">换电网点</option><option value="sale">销售网点</option><option value="mixed">综合网点</option><option value="repair">维修网点</option></select>
        <button class="btn btn-primary" onclick="loadSiteList(1)">查询</button></div>
      <div id="site_list_box"></div>`;
    window.loadSiteList = async (page = 1) => {
      const kw = document.getElementById('site_kw').value;
      const type = document.getElementById('site_type').value;
      const d = await api(`/api/sites/list?page=${page}&keyword=${encodeURIComponent(kw)}&type=${type}`);
      document.getElementById('site_list_box').innerHTML =
        tableHtml(['ID', '网点名称', '城市', '类型', '状态', '负责人', '联系电话', '地址'],
          d.items.map(x => [x.id, esc(x.name), esc(x.city || '-'), esc(x.type_text || x.type), esc(x.site_status), esc(x.contact_person_name || '-'), esc(x.contact_person_tel || '-'), esc(x.address || '-')]))
        + pager(d.total, d.page, d.page_size, 'loadSiteList');
    };
    loadSiteList(1);
  },

  /* ---- 设备资产看板 ---- */
  async assetBoard(el) {
    const [s, bt] = await Promise.all([api('/api/assets/summary'), api('/api/assets/battery-status')]);
    el.innerHTML = kpiGrid([
      { label: '换电柜', value: `${s.exchange.total}`, cls: 'blue' },
      { label: '换电柜在线', value: s.exchange.online, cls: 'ok' },
      { label: '电池总数', value: s.battery.total, cls: 'blue' },
      { label: '电池在线', value: s.battery.online, cls: 'ok' },
      { label: '电池异常', value: s.battery.fault, cls: 'warn' },
      { label: '车辆总数', value: s.bike.total, cls: 'blue' },
      { label: '车辆在线', value: s.bike.online, cls: 'ok' },
      { label: '网点数', value: s.site.total, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('电池状态分布', 300) + chartBox('资产构成', 300) + `</div>`
      + `<div class="filters" style="margin-bottom:10px">
          <input class="input" id="tr_kw" placeholder="电池SN">
          <select id="tr_type"><option value="">全部流转类型</option><option value="1">换柜流转</option><option value="2">维修流转</option></select>
          <button class="btn btn-primary" onclick="loadTransfer(1)">查询流转记录</button>
          <button class="btn btn-ghost-dark" onclick="loadWorkOrder(1)">查看工单</button></div>
        <div id="asset_box"></div>`;
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, xAxis: { type: 'category', data: bt.map(b => b.status) }, yAxis: { type: 'value' }, series: [{ type: 'pie', radius: '60%', data: bt.map(b => ({ name: b.status, value: b.count })) }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: [{ name: '换电柜', value: s.exchange.total }, { name: '电池', value: s.battery.total }, { name: '车辆', value: s.bike.total }, { name: '网点', value: s.site.total }] }] });
    }, 0);
    window.loadTransfer = async (page = 1) => {
      const kw = document.getElementById('tr_kw').value;
      const type = document.getElementById('tr_type').value;
      const d = await api(`/api/assets/transfer-logs?page=${page}&keyword=${encodeURIComponent(kw)}&transfer_type=${type}`);
      document.getElementById('asset_box').innerHTML =
        tableHtml(['ID', '电池SN', '流转类型', '流转状态', '流入', '流出', '时间'],
          d.items.map(x => [x.id, esc(x.battery_device_sn), esc(x.transfer_type), esc(x.transfer_status || '-'), esc(x.inflow_name || '-'), esc(x.outflow_name || '-'), fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadTransfer');
    };
    window.loadWorkOrder = async (page = 1) => {
      const d = await api(`/api/assets/work-orders?page=${page}`);
      document.getElementById('asset_box').innerHTML =
        tableHtml(['工单号', '事件类型', '事件名称', '地址', '状态', '优先级', '创建人', '处理人', '创建时间', '处理结束'],
          d.items.map(x => [esc(x.event_id || x.id), esc(x.event_type || '-'), esc(x.event_name || '-'), esc(x.address || '-'), esc(x.status || '-'), esc(x.priority || '-'), esc(x.creator_name || '-'), esc(x.handler_name || '-'), fmtTs(x.create_time), fmtTs(x.handle_stop_time)]))
        + pager(d.total, d.page, d.page_size, 'loadWorkOrder');
    };
    loadTransfer(1);
  },

  /* ---- 优惠券看板 ---- */
  async couponBoard(el) {
    const s = await api('/api/coupons/summary');
    el.innerHTML = kpiGrid([
      { label: '优惠券总数', value: s.coupon_total, cls: 'blue' },
      { label: '生效中', value: s.on, cls: 'ok' },
      { label: '已停用', value: s.off, cls: 'warn' },
    ]) + `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="coupon_kw" placeholder="券名称">
        <select id="coupon_status"><option value="">全部状态</option><option value="on">生效中</option><option value="off">已停用</option></select>
        <button class="btn btn-primary" onclick="loadCoupon(1)">查询</button></div>
      <div id="coupon_box"></div>`;
    window.loadCoupon = async (page = 1) => {
      const kw = document.getElementById('coupon_kw').value;
      const st = document.getElementById('coupon_status').value;
      const d = await api(`/api/coupons/list?page=${page}&keyword=${encodeURIComponent(kw)}&status=${st}`);
      document.getElementById('coupon_box').innerHTML =
        tableHtml(['券名称', '渠道', '抵扣类型', '抵扣规则', '状态', '创建人', '有效天数', '创建时间'],
          d.items.map(x => [esc(x.title || '-'), esc(x.channel || '-'), esc(x.deduct_type || '-'), esc(x.deduct_rule || '-'), x.coupon_status === 'on' ? '生效中' : '已停用', esc(x.creator_name || '-'), x.valid_days != null ? x.valid_days : '-', fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadCoupon');
    };
    loadCoupon(1);
  },

  /* ---- 人员看板 ---- */
  async staffBoard(el) {
    const s = await api('/api/staff/summary');
    el.innerHTML = kpiGrid([
      { label: '业务人员', value: s.total_staff, cls: 'blue' },
    ]) + card('业务员签约排名', tableHtml(['排名', '业务员', '签约数'],
      (s.staff_rank || []).map((r, i) => [i + 1, esc(r.name), r.agreement_count])))
      + `<div class="filters" style="margin-bottom:10px">
          <input class="input" id="staff_kw" placeholder="处理人姓名">
          <button class="btn btn-primary" onclick="loadStaffOrder(1)">查询工单</button></div>
        <div id="staff_box"></div>`;
    window.loadStaffOrder = async (page = 1) => {
      const kw = document.getElementById('staff_kw').value;
      const d = await api(`/api/staff/work-orders?page=${page}&solve_user=${encodeURIComponent(kw)}`);
      document.getElementById('staff_box').innerHTML =
        tableHtml(['工单号', '事件类型', '事件名称', '地址', '状态', '创建人', '处理人', '创建时间', '处理结束'],
          d.items.map(x => [esc(x.event_id || x.id), esc(x.event_type || '-'), esc(x.event_name || '-'), esc(x.address || '-'), x.status, esc(x.creator_name || '-'), esc(x.handler_name || '-'), fmtTs(x.create_time), fmtTs(x.handle_stop_time)]))
        + pager(d.total, d.page, d.page_size, 'loadStaffOrder');
    };
    loadStaffOrder(1);
  },

  /* ---- 财务看板 ---- */
  async financeBoard(el) {
    const [s, trend, types] = await Promise.all([
      api('/api/finance/summary'), api('/api/finance/income-trend?months=12'), api('/api/finance/expense-types'),
    ]);
    el.innerHTML = kpiGrid([
      { label: '近30天收入', value: '¥' + money(s.income_fee), cls: 'ok' },
      { label: '近30天利润', value: '¥' + money(s.profit_fee), cls: 'blue' },
      { label: '近30天支出', value: '¥' + money(s.expense_fee), cls: 'warn' },
      { label: '近30天订单', value: s.income_count, cls: 'blue' },
      { label: '近30天费用单', value: s.expense_count, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('近12月收支趋势', 300) + chartBox('费用类型分布', 300) + `</div>`
      + `<div class="filters" style="margin-bottom:10px">
          <input class="input" id="exp_kw" placeholder="商户名称/电话">
          <button class="btn btn-primary" onclick="loadExpense(1)">查询支出</button>
          <button class="btn btn-ghost-dark" onclick="loadDeposit(1)">查看押金</button></div>
        <div id="finance_box"></div>`;
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: { trigger: 'axis' }, legend: {}, xAxis: { type: 'category', data: trend.map(t => t.month) }, yAxis: { type: 'value' }, series: [
        { name: '收入', type: 'bar', data: trend.map(t => t.income), itemStyle: { color: '#2563eb' } },
        { name: '利润', type: 'line', data: trend.map(t => t.profit || 0), itemStyle: { color: '#16a34a' } },
      ] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: types.map(t => ({ name: t.fee_type, value: t.fee })) }] });
    }, 0);
    window.loadExpense = async (page = 1) => {
      const kw = document.getElementById('exp_kw').value;
      const d = await api(`/api/finance/expense-list?page=${page}&keyword=${encodeURIComponent(kw)}`);
      document.getElementById('finance_box').innerHTML =
        tableHtml(['费用名称', '费用类型', '说明', '对方单位', '金额', '单据状态', '创建时间'],
          d.items.map(x => [esc(x.expense_name || '-'), esc(x.expense_type || '-'), esc((x.expense_description || '').slice(0, 30)), esc(x.out_unit_name || '-'), '¥' + money(x.fee), esc(x.bill_status || '-'), fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadExpense');
    };
    window.loadDeposit = async (page = 1) => {
      const d = await api(`/api/finance/deposit-list?page=${page}`);
      document.getElementById('finance_box').innerHTML =
        tableHtml(['ID', '用户', '手机号', '押金状态', '押金金额', '是否已退', '是否冻结', '创建时间'],
          d.items.map(x => [x.id, esc(x.username || '-'), esc(x.phone || '-'), esc(x.take_battery_status || '-'), '¥' + money(x.fee), x.is_withdraw == 1 ? '是' : '否', x.is_freeze == 1 ? '是' : '否', fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadDeposit');
    };
    loadExpense(1);
  },

  /* ---- 客服服务台 ---- */
  async serviceDesk(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="svc_kw" placeholder="手机号/姓名">
        <button class="btn btn-primary" onclick="loadService(1)">用户查询</button>
        <button class="btn btn-ghost-dark" onclick="loadComplaint(1)">客诉记录</button></div>
      <div id="service_box"></div>`;
    window.loadService = async (page = 1) => {
      const kw = document.getElementById('svc_kw').value;
      const d = await api(`/api/service/query?page=${page}&keyword=${encodeURIComponent(kw)}`);
      document.getElementById('service_box').innerHTML =
        tableHtml(['ID', '手机号', '姓名', '城市', '状态', '生效时间'],
          d.items.map(u => [u.id, esc(u.user_phone), esc(u.user_name || '-'), esc(u.sys_city_name || '-'), esc(u.status_text || u.status), fmtTs(u.activation_time)]))
        + pager(d.total, d.page, d.page_size, 'loadService');
    };
    window.loadComplaint = async (page = 1) => {
      const d = await api(`/api/service/complaints?page=${page}`);
      document.getElementById('service_box').innerHTML =
        tableHtml(['单号', '用户', '手机号', '换电柜', '内容', '处理状态', '创建时间'],
          d.items.map(x => [x.id, esc(x.user_name || '-'), esc(x.user_phone || '-'), esc(x.exchange_sn || '-'), esc((x.remark || '').slice(0, 40)), esc(x.operation_status || '-'), fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadComplaint');
    };
    loadService(1);
  },

  /* ---- 深度分析 ---- */
  async deepAnalysis(el) {
    const [peak, ft, age] = await Promise.all([
      api('/api/insights/exchange-peak'), api('/api/insights/first-take'), api('/api/insights/battery-age'),
    ]);
    el.innerHTML = `<div class="grid-2">` + chartBox('换电高峰时段（近7天）', 300) + chartBox('电池使用时长分布', 300) + `</div>`
      + card('新老用户占比', `<div class="kpi-grid">
          <div class="kpi"><div class="label">首次换电用户</div><div class="value ok">${ft.first_take}</div></div>
          <div class="kpi"><div class="label">复购用户</div><div class="value blue">${ft.again}</div></div>
          <div class="kpi"><div class="label">复购占比</div><div class="value warn">${((ft.again || 0) / Math.max(1, ft.first_take + ft.again) * 100).toFixed(1)}%</div></div></div>`)
      + `<div class="filters" style="margin-bottom:10px">
          <button class="btn btn-ghost-dark" onclick="loadInsightOrders(1)">查看近7天换电明细</button></div>
        <div id="insight_box"></div>`;
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, xAxis: { type: 'category', data: peak.map(p => p.hour + '时') }, yAxis: { type: 'value' }, series: [{ type: 'line', smooth: true, data: peak.map(p => p.count), itemStyle: { color: '#2563eb' }, areaStyle: { opacity: .12 } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: age.map(a => ({ name: a.age_range, value: a.count })) }] });
    }, 0);
    window.loadInsightOrders = async (page = 1) => {
      const d = await api(`/api/sales/service-orders?page=${page}`);
      document.getElementById('insight_box').innerHTML =
        tableHtml(['服务单号', '用户', '手机号', '套餐', '状态', '支付金额', '创建时间'],
          d.items.map(x => [esc(x.order_no || x.id), esc(x.user_name || '-'), esc(x.user_phone || '-'), esc(x.package_name || '-'), x.order_status, '¥' + money(x.pay_fee), fmtTs(x.create_time)]))
        + pager(d.total, d.page, d.page_size, 'loadInsightOrders');
    };
  },

  /* ---- 运维看板四板块 ---- */
  async dashboard(el) {
    const [s, cs, as] = await Promise.all([
      api('/api/dashboard/summary'), api('/api/dashboard/customer-stats'), api('/api/dashboard/alarm-stats'),
    ]);
    const d = s.device, b = d.battery, e = d.exchange, ab = s.alarm.battery, ae = s.alarm.exchange;
    el.innerHTML = kpiGrid([
      { label: '电池总数', value: b.total, cls: 'blue' },
      { label: '电池在线', value: b.online, cls: 'ok' },
      { label: '电池离线', value: b.offline, cls: 'warn' },
      { label: '换电柜总数', value: e.total, cls: 'blue' },
      { label: '换电柜在线', value: e.online, cls: 'ok' },
      { label: '换电柜离线', value: e.offline, cls: 'warn' },
      { label: '电池告警', value: ab.total, cls: 'danger' },
      { label: '机柜告警', value: ae.total, cls: 'danger' },
    ]) + `<div class="grid-2">` + chartBox('电池告警分类', 300) + chartBox('机柜告警分类', 300) + `</div>`
      + card('客户设备统计', tableHtml(['客户', '电池数', '换电柜数', '电池告警', '机柜告警'],
        cs.map(c => [esc(c.customer_name), c.battery.total, c.exchange.total, c.battery_alarm, c.exchange_alarm])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: dictToArr(as.battery).map(x => ({ name: ALARM_META[x.type] ? ALARM_META[x.type].name : x.type, value: x.count })) }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: dictToArr(as.exchange).map(x => ({ name: ALARM_META[x.type] ? ALARM_META[x.type].name : x.type, value: x.count })) }] });
    }, 0);
  },

  async exchange(el) {
    el.innerHTML = `<div id="exchange_kpi"></div>
      <div class="filters" style="margin-bottom:10px">
        <select id="ex_status"><option value="">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select>
        <input class="input" id="ex_kw" placeholder="柜号/名称/地址">
        <button class="btn btn-primary" onclick="loadExchange(1)">查询</button>
        <button class="btn btn-ghost-dark" onclick="exportCsv('exchange')">导出</button></div>
      <div id="exchange_box"></div>`;
    window.loadExchange = async (page = 1) => {
      try {
        const st = document.getElementById('ex_status').value;
        const kw = document.getElementById('ex_kw').value;
        const d = await api(`/api/devices/exchanges?page=${page}&status=${st}&keyword=${encodeURIComponent(kw)}`);
        const s = d.stats;
        document.getElementById('exchange_kpi').innerHTML = kpiGrid([
          { label: '换电柜总数', value: s.total, cls: 'blue' },
          { label: '在线', value: s.online, cls: 'ok' },
          { label: '离线', value: s.offline, cls: 'warn' },
        ]);
        document.getElementById('exchange_box').innerHTML =
          tableHtml(['柜号', '设备名称', '客户', '状态', '总仓', '满仓', '充电中', '空仓', '烟感', '水浸', '火警', '摆放位置', '地址', '最后上报'],
            d.items.map(x => [esc(x.device_sn), esc(x.device_name || '-'), esc(x.customer_name), statusTag(x.online_status),
              x.slot_total, x.slot_full, x.slot_charging, x.slot_empty,
              x.smoke === '1' ? tag('告警', 'tag-p0') : '-', x.flooded === '1' ? tag('告警', 'tag-p0') : '-', x.fire === '1' ? tag('告警', 'tag-p0') : '-',
              esc(x.site_placement || '-'), esc(x.last_location_address || '-'), fmtTs(x.last_upload_time)]))
          + pager(d.total, d.page, d.page_size, 'loadExchange');
      } catch (e) {
        console.error(e);
        document.getElementById('exchange_box').innerHTML = dbErrorHtml(e);
      }
    };
    loadExchange(1);
  },

  async battery(el) {
    el.innerHTML = `<div id="battery_kpi"></div>
      <div class="filters" style="margin-bottom:10px">
        <select id="bt_status"><option value="">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select>
        <input class="input-sm" id="bt_pmin" placeholder="电量%低">
        <input class="input-sm" id="bt_pmax" placeholder="电量%高">
        <input class="input" id="bt_kw" placeholder="电池SN/柜号/地址">
        <button class="btn btn-primary" onclick="loadBattery(1)">查询</button>
        <button class="btn btn-ghost-dark" onclick="exportCsv('battery')">导出</button></div>
      <div id="battery_box"></div>`;
    window.loadBattery = async (page = 1) => {
      try {
        const st = document.getElementById('bt_status').value;
        const pmin = document.getElementById('bt_pmin').value;
        const pmax = document.getElementById('bt_pmax').value;
        const kw = document.getElementById('bt_kw').value;
        const d = await api(`/api/devices/batteries?page=${page}&status=${st}&power_min=${pmin}&power_max=${pmax}&keyword=${encodeURIComponent(kw)}`);
        const s = d.stats;
        document.getElementById('battery_kpi').innerHTML = kpiGrid([
          { label: '电池总数', value: s.total, cls: 'blue' },
          { label: '在线', value: s.online, cls: 'ok' },
          { label: '离线', value: s.offline, cls: 'warn' },
        ]);
        document.getElementById('battery_box').innerHTML =
          tableHtml(['电池SN', '客户', '电池状态', '在线', '类型', '电量%', '电压V', '充电', '所在柜', '供应商', '地址', '最后上报'],
            d.items.map(x => [esc(x.device_sn), esc(x.customer_name), esc(x.battery_status || '-'), statusTag(x.online_status),
              esc(x.type || '-'), x.power != null ? x.power : '-', x.voltage != null ? x.voltage : '-',
              x.charging === '1' ? tag('充电中', 'tag-ok') : '-', esc(x.last_upload_exchange_sn || '-'),
              esc(x.supplier_name || '-'), esc(x.last_location_address || '-'), fmtTs(x.last_battery_upload_time)]))
          + pager(d.total, d.page, d.page_size, 'loadBattery');
      } catch (e) {
        console.error(e);
        document.getElementById('battery_box').innerHTML = dbErrorHtml(e);
      }
    };
    loadBattery(1);
  },

  async alarm(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <select id="al_dev"><option value="all">全部设备</option><option value="battery">电池</option><option value="exchange">换电柜</option></select>
        <select id="al_type"><option value="">全部告警类型</option></select>
        <button class="btn btn-primary" onclick="loadAlarm(1)">查询</button>
        <button class="btn btn-ghost-dark" onclick="exportCsv('alarm')">导出</button></div>
      <div id="alarm_box"></div>`;
    const typeSel = document.getElementById('al_type');
    Object.entries(ALARM_META).forEach(([k, v]) => { const o = document.createElement('option'); o.value = k; o.textContent = v.name; typeSel.appendChild(o); });
    window.loadAlarm = async (page = 1) => {
      try {
        const dev = document.getElementById('al_dev').value;
        const type = document.getElementById('al_type').value;
        const d = await api(`/api/alarms?page=${page}&device_type=${dev}&alarm_type=${type}`);
        document.getElementById('alarm_box').innerHTML =
          tableHtml(['类型', '设备', '等级', 'SN', '客户', '位置', '时间'],
            d.items.map(x => { const m = ALARM_META[x.alarm_type] || {}; return [
              tag(m.name || x.alarm_name, m.cls || 'tag-p2'), DEVICE_NAMES[x.device_type] || '-',
              'P' + (m.prio || x.priority || '-'), esc(x.device_sn), esc(x.customer_name || '-'),
              esc(x.location || '-'), fmtTs(x.alarm_time || x.occur_time),
            ]; }))
          + pager(d.total, d.page, d.page_size, 'loadAlarm');
      } catch (e) {
        console.error(e);
        document.getElementById('alarm_box').innerHTML = dbErrorHtml(e);
      }
    };
    loadAlarm(1);
  },

  /* ---- 数据大屏（深蓝科技风 + 城市切换） ---- */

  async bigscreen(el) {
    const CITY = window._bsCity || '深圳市';
    el.innerHTML = `<style>
      .bs-wrap{position:relative;min-height:calc(100vh - 130px);padding:14px 16px 20px;border-radius:12px;
        background:radial-gradient(1200px 500px at 50% -10%, rgba(30,90,220,.35), transparent 60%),
                   linear-gradient(180deg,#0a1633 0%,#050d22 100%);
        border:1px solid rgba(64,158,255,.25);color:#dce8ff;font-family:'Microsoft YaHei',sans-serif}
      .bs-head{display:flex;align-items:center;justify-content:space-between;padding:2px 4px 12px;
        border-bottom:1px solid rgba(64,158,255,.25);margin-bottom:12px}
      .bs-title{font-size:22px;font-weight:700;letter-spacing:4px;text-shadow:0 0 18px rgba(64,158,255,.8)}
      .bs-title small{font-size:12px;letter-spacing:1px;color:#8fb6ff;margin-left:10px;font-weight:400}
      .bs-city{display:flex;align-items:center;gap:8px;font-size:13px;color:#8fb6ff}
      .bs-city select{background:rgba(13,34,84,.8);color:#dce8ff;border:1px solid rgba(64,158,255,.5);border-radius:6px;
        padding:6px 10px;font-size:14px;outline:none;cursor:pointer}
      .bs-col{display:grid;grid-template-columns:230px 1fr 260px;gap:12px;align-items:stretch}
      .bs-panel{background:rgba(13,34,84,.55);border:1px solid rgba(64,158,255,.35);border-radius:8px;
        padding:12px;box-shadow:0 0 18px rgba(20,60,160,.25)}
      .bs-panel h4{margin:0 0 8px;font-size:13px;color:#8fb6ff;letter-spacing:2px;font-weight:600;
        border-left:3px solid #3d8bff;padding-left:8px}
      .bs-kpi{text-align:center;padding:10px 6px;margin-bottom:8px;background:linear-gradient(160deg,rgba(24,58,140,.5),rgba(10,24,60,.6));
        border:1px solid rgba(64,158,255,.3);border-radius:8px}
      .bs-kpi .lb{font-size:12px;color:#8fb6ff;letter-spacing:1px}
      .bs-kpi .vl{font-size:26px;font-weight:700;margin-top:6px;color:#6fd1ff;text-shadow:0 0 12px rgba(64,158,255,.6)}
      .bs-kpi .vl.gold{color:#ffcf6f;text-shadow:0 0 12px rgba(255,200,90,.6)}
      .bs-kpi .vl.green{color:#6fe3a8;text-shadow:0 0 12px rgba(90,220,150,.6)}
      .bs-kpi .vl.pink{color:#ff9ad5;text-shadow:0 0 12px rgba(255,140,210,.5)}
      .bs-kpi .sub{font-size:11px;color:#7d9bd8;margin-top:4px}
      .bs-chart{width:100%;height:230px}
      .bs-table{width:100%;border-collapse:collapse;font-size:12px}
      .bs-table th{background:rgba(30,70,160,.35);color:#9cc2ff;padding:5px 6px;font-weight:600}
      .bs-table td{color:#cfe0ff;padding:5px 6px;border-bottom:1px solid rgba(64,158,255,.12);text-align:right}
      .bs-table td:first-child,.bs-table th:first-child{text-align:left}
      .bs-table tr:hover td{background:rgba(40,90,200,.12)}
      .bs-rank{display:flex;align-items:center;gap:8px;font-size:12px;padding:4px 0;color:#cfe0ff}
      .bs-rank .no{width:18px;height:18px;line-height:18px;text-align:center;border-radius:4px;
        background:rgba(64,158,255,.25);color:#8fc6ff;font-weight:700;flex:none}
      .bs-rank .bar{height:8px;border-radius:4px;background:linear-gradient(90deg,#2d6bff,#45c8ff)}
      .bs-time{font-size:12px;color:#7d9bd8;letter-spacing:1px}
      .bs-foot{display:flex;justify-content:center;gap:24px;margin-top:12px;font-size:12px;color:#7d9bd8}
      .bs-foot b{color:#6fd1ff;font-size:14px}
    </style>
    <div class="bs-wrap">
      <div class="bs-head">
        <div class="bs-title">换电运营 · 数据大屏<small>REAL-TIME OPERATION BOARD</small></div>
        <div class="bs-city">城市：
          <select id="bs_city" onchange="window.bsSwitchCity(this.value)">
            <option value="">全部城市</option>
          </select>
          <span class="bs-time" id="bs_time"></span>
        </div>
      </div>
      <div class="bs-col">
        <div class="bs-panel" style="display:flex;flex-direction:column">
          <div class="bs-kpi"><div class="lb">用户总数</div><div class="vl" id="bs_u">-</div>
            <div class="sub">今日新增 <b id="bs_du">-</b> · 今日活跃 <b id="bs_au">-</b></div></div>
          <div class="bs-kpi"><div class="lb">今日换电单量</div><div class="vl green" id="bs_od">-</div>
            <div class="sub">当日累计订单</div></div>
          <div class="bs-kpi"><div class="lb">今日换电收入(元)</div><div class="vl gold" id="bs_fd">-</div>
            <div class="sub">支付 + 电费</div></div>
          <div class="bs-kpi"><div class="lb">月目标完成度</div><div class="vl pink" id="bs_mr">-</div>
            <div class="sub">本月收入 <b id="bs_mi">-</b> / 月均目标 <b id="bs_mt">-</b></div></div>
          <h4 style="margin-top:auto">设备概况</h4>
          <div style="font-size:12px;color:#cfe0ff;line-height:22px">
            换电柜：<b id="bs_ex">-</b>（在线 <span id="bs_exon" style="color:#6fe3a8">-</span> / 离线 <span id="bs_exoff" style="color:#ff9a9a">-</span>）<br>
            电池总数：<b id="bs_bt">-</b>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div class="bs-panel"><h4>区域分布（用户数 / 今日换电）</h4><div class="bs-chart" id="bs_regionChart"></div></div>
          <div class="bs-panel" style="flex:1"><h4>区域数据明细</h4>
            <table class="bs-table"><thead><tr><th>区域</th><th>用户数</th><th>换电柜</th><th>今日单量</th><th>今日收入(元)</th></tr></thead>
            <tbody id="bs_regionTable"><tr><td colspan="5" style="text-align:center;color:#7d9bd8">加载中...</td></tr></tbody></table>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div class="bs-panel"><h4>网点类型分布</h4><div class="bs-chart" id="bs_typeChart" style="height:160px"></div></div>
          <div class="bs-panel"><h4>电池状态分布</h4><div class="bs-chart" id="bs_batteryChart" style="height:150px"></div></div>
          <div class="bs-panel"><h4>Top5 换电城市</h4><div id="bs_rank"></div></div>
          <div class="bs-panel"><h4>月度收入达标对比(元)</h4><div class="bs-chart" id="bs_goalChart" style="height:150px"></div></div>
        </div>
      </div>
      <div class="bs-foot"><span>今日换电 <b id="bs_foot_od">-</b></span><span>今日收入 <b id="bs_foot_fd">-</b></span>
        <span>本月收入 <b id="bs_foot_mi">-</b></span></div>
    </div>`;
    const t = () => {
      const d = new Date();
      document.getElementById('bs_time').textContent = d.toLocaleString('zh-CN', { hour12: false });
    };
    t(); setInterval(t, 1000);

    window.bsLoadBig = async () => {
      const city = window._bsCity || '';
      const [s, regs, d, tr, top] = await Promise.all([
        api('/api/bigscreen/summary?city=' + encodeURIComponent(city)),
        api('/api/bigscreen/regions?city=' + encodeURIComponent(city)),
        api('/api/bigscreen/dist?city=' + encodeURIComponent(city)),
        api('/api/bigscreen/trend?city=' + encodeURIComponent(city) + '&months=12'),
        api('/api/bigscreen/top-cities?days=30'),
      ]);
      const g = id => document.getElementById(id);
      g('bs_u').textContent = (s.total_users || 0).toLocaleString();
      g('bs_du').textContent = s.today_new_users || 0;
      g('bs_au').textContent = s.today_users || 0;
      g('bs_od').textContent = (s.today_exchange || 0).toLocaleString();
      g('bs_fd').textContent = money(s.today_fee);
      g('bs_mr').textContent = (s.month_target_rate || 0) + '%';
      g('bs_mi').textContent = money(s.month_income);
      g('bs_mt').textContent = money(s.month_target);
      g('bs_ex').textContent = (s.exchanges || {}).total || 0;
      g('bs_exon').textContent = (s.exchanges || {}).online || 0;
      g('bs_exoff').textContent = (s.exchanges || {}).offline || 0;
      g('bs_bt').textContent = (s.battery_total || 0).toLocaleString();
      g('bs_foot_od').textContent = (s.today_exchange || 0).toLocaleString();
      g('bs_foot_fd').textContent = money(s.today_fee);
      g('bs_foot_mi').textContent = money(s.month_income);

      const regsTop = (regs || []).slice(0, 8);
      g('bs_regionTable').innerHTML = regsTop.length ? regsTop.map(r =>
        `<tr><td>${esc(r.area)}</td><td>${r.users.toLocaleString()}</td><td>${r.exchanges}</td><td>${r.orders_today}</td><td>${money(r.income_today)}</td></tr>`).join('')
        : '<tr><td colspan="5" style="text-align:center;color:#7d9bd8">暂无数据</td></tr>';

      drawChart('bs_regionChart', {
        tooltip: { trigger: 'axis' },
        legend: { textStyle: { color: '#8fb6ff' }, top: 0 },
        grid: { left: 50, right: 50, top: 30, bottom: 24 },
        xAxis: { type: 'category', data: regsTop.map(r => r.area), axisLabel: { color: '#9cc2ff' }, axisLine: { lineStyle: { color: 'rgba(64,158,255,.3)' } } },
        yAxis: [
          { type: 'value', name: '用户', axisLabel: { color: '#9cc2ff' }, splitLine: { lineStyle: { color: 'rgba(64,158,255,.15)' } } },
          { type: 'value', name: '单量', axisLabel: { color: '#9cc2ff' }, splitLine: { show: false } },
        ],
        series: [
          { name: '用户数', type: 'bar', data: regsTop.map(r => r.users), barWidth: 14, itemStyle: { color: 'rgba(45,107,255,.75)', borderRadius: [3, 3, 0, 0] } },
          { name: '今日单量', type: 'bar', yAxisIndex: 1, data: regsTop.map(r => r.orders_today), barWidth: 14, itemStyle: { color: 'rgba(69,200,255,.75)', borderRadius: [3, 3, 0, 0] } },
        ],
      });

      const types = (d.exchange_types || []).slice(0, 6);
      drawChart('bs_typeChart', {
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie', radius: ['35%', '72%'], center: ['50%', '52%'],
          label: { color: '#cfe0ff', fontSize: 10 },
          itemStyle: { borderColor: '#0a1633', borderWidth: 2 },
          data: types.map(x => ({ name: x.name, value: x.count })),
        }],
      });

      const bst = (d.battery_status || []).filter(x => x.name !== 'unknown');
      drawChart('bs_batteryChart', {
        tooltip: { trigger: 'item' },
        legend: { textStyle: { color: '#8fb6ff' }, bottom: 0, itemWidth: 12, itemHeight: 8 },
        series: [{
          type: 'pie', radius: ['35%', '68%'], center: ['50%', '46%'],
          label: { show: false },
          itemStyle: { borderColor: '#0a1633', borderWidth: 2 },
          data: bst.map(x => ({ name: x.name === 'using' ? '使用中' : x.name === 'none' ? '空闲' : x.name, value: x.count })),
        }],
      });

      const rank = (top || []).slice(0, 5);
      const maxO = Math.max(1, ...rank.map(r => r.orders));
      g('bs_rank').innerHTML = rank.length ? rank.map((r, i) =>
        `<div class="bs-rank"><span class="no">${i + 1}</span><span style="flex:0 0 88px">${esc(r.city.replace(/省|市|壮族自治区/g, ''))}</span>
         <div class="bar" style="width:${Math.max(6, Math.round(r.orders / maxO * 100))}%"></div>
         <span>${r.orders.toLocaleString()}</span></div>`).join('')
        : '<div style="color:#7d9bd8;font-size:12px">暂无数据</div>';

      const last = tr.length > 1 ? tr[tr.length - 2].fee : 0;
      drawChart('bs_goalChart', {
        tooltip: { trigger: 'axis' },
        grid: { left: 60, right: 20, top: 20, bottom: 24 },
        xAxis: { type: 'category', data: ['本月收入', '月均目标', '上月收入'], axisLabel: { color: '#9cc2ff' }, axisLine: { lineStyle: { color: 'rgba(64,158,255,.3)' } } },
        yAxis: { type: 'value', axisLabel: { color: '#9cc2ff', formatter: v => v >= 10000 ? (v / 10000).toFixed(0) + 'w' : v }, splitLine: { lineStyle: { color: 'rgba(64,158,255,.15)' } } },
        series: [{
          type: 'bar', barWidth: 26,
          data: [
            { value: s.month_income, itemStyle: { color: 'rgba(69,200,255,.85)' } },
            { value: s.month_target, itemStyle: { color: 'rgba(255,207,111,.85)' } },
            { value: last, itemStyle: { color: 'rgba(120,140,255,.6)' } },
          ],
          label: { show: true, position: 'top', color: '#cfe0ff', fontSize: 10, formatter: p => p.value >= 10000 ? (p.value / 10000).toFixed(1) + 'w' : p.value },
        }],
      });
    };

    window.bsSwitchCity = (v) => {
      window._bsCity = v;
      bsLoadBig().catch(e => { console.error(e); });
    };

    try {
      const cities = (await api('/api/bigscreen/cities') || []).filter(c => c.city && c.city !== '未知城市');
      const sel = document.getElementById('bs_city');
      sel.innerHTML = '<option value="">全部城市</option>' + cities.map(c =>
        `<option value="${esc(bsShort(c.city))}" ${bsShort(c.city) === CITY ? 'selected' : ''}>${esc(bsShort(c.city))}</option>`).join('');
      window._bsCity = cities.some(c => bsShort(c.city) === CITY) ? CITY : (cities[0] ? bsShort(cities[0].city) : '');
      await bsLoadBig();
    } catch (e) {
      console.error(e);
      el.querySelector('.bs-col').innerHTML = dbErrorHtml(e);
    }
  },

  /* ---- 风险监控 ---- */
  async riskMonitor(el) {
    const [s, as, alarms] = await Promise.all([
      api('/api/dashboard/summary'), api('/api/dashboard/alarm-stats'), api('/api/alarms?page=1&page_size=20'),
    ]);
    const ab = (s.alarm || {}).battery || {}, ae = (s.alarm || {}).exchange || {};
    const all = [...dictToArr(as.battery), ...dictToArr(as.exchange)];
    const prio = all.reduce((m, x) => { const p = (ALARM_META[x.type] || {}).prio || 2; m[p] = (m[p] || 0) + x.count; return m; }, {});
    el.innerHTML = kpiGrid([
      { label: '电池告警', value: ab.total, cls: 'danger' },
      { label: '机柜告警', value: ae.total, cls: 'danger' },
      { label: 'P1 高危告警', value: prio[1] || 0, cls: 'danger' },
      { label: 'P2 中危告警', value: prio[2] || 0, cls: 'warn' },
      { label: '电池在线', value: ((s.device || {}).battery || {}).online, cls: 'ok' },
      { label: '机柜在线', value: ((s.device || {}).exchange || {}).online, cls: 'ok' },
    ]) + `<div class="grid-2">` + chartBox('告警分类统计', 300) + chartBox('风险等级分布', 300) + `</div>`
      + card('最新告警明细', tableHtml(['类型', '设备', '等级', 'SN', '客户', '位置', '时间'],
        (alarms.items || []).map(x => { const m = ALARM_META[x.alarm_type] || {}; return [
          tag(m.name || x.alarm_name, m.cls || 'tag-p2'), DEVICE_NAMES[x.device_type] || '-',
          'P' + (m.prio || x.priority || '-'), esc(x.device_sn), esc(x.customer_name || '-'),
          esc(x.location || '-'), fmtTs(x.alarm_time || x.occur_time),
        ]; })));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: {}, grid: { left: 90, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: all.map(x => (ALARM_META[x.type] || {}).name || x.type) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: all.map(x => x.count), itemStyle: { color: '#dc2626' } }],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {},
        series: [{ type: 'pie', radius: '60%', data: [
          { name: 'P1 高危', value: prio[1] || 0 }, { name: 'P2 中危', value: prio[2] || 0 },
        ] }],
      });
    }, 0);
  },

  /* ---- 经营决策 ---- */
  async decision(el) {
    const [f, ft, t, peak] = await Promise.all([
      api('/api/finance/summary'), api('/api/finance/income-trend?months=12'),
      api('/api/overview/monthly-trend?months=12'), api('/api/insights/exchange-peak'),
    ]);
    const avgIncome = ft.length ? ft.reduce((a, x) => a + (x.income || 0), 0) / ft.length : 0;
    el.innerHTML = kpiGrid([
      { label: '近30天收入', value: '¥' + money(f.income_fee), cls: 'ok' },
      { label: '近30天利润', value: '¥' + money(f.profit_fee), cls: 'blue' },
      { label: '近30天支出', value: '¥' + money(f.expense_fee), cls: 'warn' },
      { label: '近30天订单', value: f.income_count, cls: 'blue' },
      { label: '近30天费用单', value: f.expense_count, cls: 'blue' },
      { label: '月均收入(12月)', value: '¥' + money(avgIncome), cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('近12月收支与利润', 320) + chartBox('换电高峰时段', 320) + `</div>`
      + card('月度业务趋势', tableHtml(['月份', '换电单量', '收入(元)', '利润(元)'],
        ft.map(x => { const mt = t.find(y => y.month === x.month); return [
          esc(x.month), mt ? mt.exchange_count : '-', money(x.income), money(x.profit || 0),
        ]; })));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: { trigger: 'axis' }, legend: {}, grid: { left: 70, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: ft.map(x => x.month) },
        yAxis: { type: 'value' },
        series: [
          { name: '收入', type: 'bar', data: ft.map(x => x.income), itemStyle: { color: '#2563eb' } },
          { name: '支出', type: 'bar', data: ft.map(x => x.expense || 0), itemStyle: { color: '#f59e0b' } },
          { name: '利润', type: 'line', data: ft.map(x => x.profit || 0), itemStyle: { color: '#16a34a' } },
        ],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {}, grid: { left: 60, right: 20, bottom: 30 },
        xAxis: { type: 'category', data: peak.map(p => p.hour + '时') },
        yAxis: { type: 'value' },
        series: [{ type: 'line', smooth: true, data: peak.map(p => p.count), itemStyle: { color: '#2563eb' }, areaStyle: { opacity: .12 } }],
      });
    }, 0);
  },

  /* ---- 大屏指挥 ---- */
  async command(el) {
    const [regions, assets, ds, alarms] = await Promise.all([
      api('/api/overview/regions'), api('/api/assets/summary'),
      api('/api/dashboard/summary'), api('/api/alarms?page=1&page_size=10'),
    ]);
    const e = (ds.device || {}).exchange || {}, b = (ds.device || {}).battery || {};
    const ab = ((ds.alarm || {}).battery || {}).total || 0, ae = ((ds.alarm || {}).exchange || {}).total || 0;
    el.innerHTML = kpiGrid([
      { label: '换电柜在线', value: e.online, cls: 'ok' },
      { label: '换电柜离线', value: e.offline, cls: 'warn' },
      { label: '电池在线', value: b.online, cls: 'ok' },
      { label: '电池离线', value: b.offline, cls: 'warn' },
      { label: '电池异常', value: (assets.battery || {}).fault, cls: 'danger' },
      { label: '车辆总数', value: (assets.bike || {}).total, cls: 'blue' },
      { label: '网点总数', value: (assets.site || {}).total, cls: 'blue' },
      { label: '告警总数', value: ab + ae, cls: 'danger' },
    ]) + `<div class="grid-2">` + chartBox('区域网点与换电分布 TOP12', 320) + chartBox('资产在线构成', 320) + `</div>`
      + card('最新告警', tableHtml(['类型', '设备', 'SN', '客户', '位置', '时间'],
        (alarms.items || []).slice(0, 10).map(x => { const m = ALARM_META[x.alarm_type] || {}; return [
          tag(m.name || x.alarm_name, m.cls || 'tag-p2'), DEVICE_NAMES[x.device_type] || '-',
          esc(x.device_sn), esc(x.customer_name || '-'), esc(x.location || '-'), fmtTs(x.alarm_time || x.occur_time),
        ]; })));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), {
        tooltip: {}, legend: {}, grid: { left: 60, right: 60, bottom: 40 },
        xAxis: { type: 'category', data: regions.slice(0, 12).map(r => r.city), axisLabel: { rotate: 30 } },
        yAxis: [{ type: 'value' }, { type: 'value' }],
        series: [
          { name: '换电柜', type: 'bar', data: regions.slice(0, 12).map(r => r.exchange_count), itemStyle: { color: '#2563eb' } },
          { name: '30天换电', type: 'line', yAxisIndex: 1, data: regions.slice(0, 12).map(r => r.exchange_30d), itemStyle: { color: '#16a34a' } },
        ],
      });
      drawChart(firstChartId(el, 1), {
        tooltip: {},
        series: [{ type: 'pie', radius: '60%', data: [
          { name: '电池在线', value: b.online }, { name: '电池离线', value: b.offline },
          { name: '机柜在线', value: e.online }, { name: '机柜离线', value: e.offline },
        ] }],
      });
    }, 0);
  },

  /* ---- 数据总览 · 城市维度 ---- */
  async cityDim(el) {
    const d = (await api('/api/overview/city-dimension')) || [];
    const top = [...d].sort((a, b) => b.exchange_count - a.exchange_count);
    el.innerHTML = kpiGrid([
      { label: '覆盖城市', value: top.length, cls: 'blue' },
      { label: '累计换电(次)', value: top.reduce((a, x) => a + (x.exchange_count || 0), 0).toLocaleString(), cls: 'blue' },
      { label: '累计收入(元)', value: money(top.reduce((a, x) => a + (x.fee || 0), 0)), cls: 'ok' },
      { label: '活跃用户', value: top.reduce((a, x) => a + (x.active_users || 0), 0).toLocaleString(), cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('城市换电 TOP10', 320) + chartBox('城市收入 TOP10', 320) + `</div>`
      + card('城市维度明细', tableHtml(['城市', '活跃用户', '换电次数', '收入(元)', '利润(元)'],
        top.map(x => [esc(bsShort(x.city)), (x.active_users || 0).toLocaleString(), (x.exchange_count || 0).toLocaleString(), money(x.fee), money(x.profit_fee)])));
    setTimeout(() => {
      const c10 = top.slice(0, 10);
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: c10.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: c10.map(x => x.exchange_count), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: c10.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: c10.map(x => x.fee), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 数据总览 · 网点维度 ---- */
  async siteDim(el) {
    const [s, regions, list] = await Promise.all([
      api('/api/sites/summary'), api('/api/overview/regions'), api('/api/sites/list?page=1&page_size=20'),
    ]);
    const r = (regions || []).slice(0, 12);
    el.innerHTML = kpiGrid([
      { label: '网点总数', value: s.site_total, cls: 'blue' },
      { label: '在营', value: s.site_open, cls: 'ok' },
      { label: '停业', value: s.site_closed, cls: 'warn' },
      { label: '处理中工单', value: s.work_order_doing, cls: 'danger' },
    ]) + `<div class="grid-2">` + chartBox('区域网点分布', 320) + chartBox('区域30天换电', 320) + `</div>`
      + card('网点样本', tableHtml(['网点名称', '城市', '区域', '类型', '状态', '联系人', '地址'],
        (list.items || []).map(x => [esc(x.name), esc(x.city), esc(x.area || '-'), esc(String(x.type_text ?? x.type)), x.site_status === 'on' ? tag('在营', 'tag-ok') : tag('停业', 'tag-off'), esc(x.contact_person_name || '-'), esc(x.address || '-')])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: r.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: r.map(x => x.site_count), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: r.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: r.map(x => x.exchange_30d), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 数据总览 · 设备维度 ---- */
  async deviceDim(el) {
    const [d, bs] = await Promise.all([api('/api/overview/device-dimension'), api('/api/assets/battery-status')]);
    const b = d.battery || {}, e = d.exchange || {}, k = d.bike || {}, s = d.site || {};
    el.innerHTML = kpiGrid([
      { label: '换电柜', value: e.total, cls: 'blue' }, { label: '柜在线', value: e.online, cls: 'ok' }, { label: '柜离线', value: e.offline, cls: 'warn' },
      { label: '电池', value: b.total, cls: 'blue' }, { label: '电池在线', value: b.online, cls: 'ok' }, { label: '电池离线', value: b.offline, cls: 'warn' },
      { label: '车辆', value: k.total, cls: 'blue' }, { label: '网点', value: s.total, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('设备在线构成', 320) + chartBox('电池状态分布', 320) + `</div>`
      + card('电池状态明细', tableHtml(['状态', '数量'], (bs || []).map(x => [esc(x.status || x.name), (x.count || 0).toLocaleString()])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: [
        { name: '柜在线', value: e.online }, { name: '柜离线', value: e.offline },
        { name: '电池在线', value: b.online }, { name: '电池离线', value: b.offline },
      ] }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: (bs || []).map(x => ({ name: x.status || x.name, value: x.count })) }] });
    }, 0);
  },

  /* ---- 数据总览 · 财务维度 ---- */
  async financeDim(el) {
    const rows = (await api('/api/overview/finance-dimension')) || [];
    el.innerHTML = kpiGrid([
      { label: '近12月收入(元)', value: money(rows.reduce((a, x) => a + (x.income || 0), 0)), cls: 'ok' },
      { label: '近12月利润(元)', value: money(rows.reduce((a, x) => a + (x.profit || 0), 0)), cls: 'blue' },
      { label: '近12月支出(元)', value: money(rows.reduce((a, x) => a + (x.expense || 0), 0)), cls: 'warn' },
      { label: '费用单数', value: rows.reduce((a, x) => a + (x.expense_count || 0), 0).toLocaleString(), cls: 'blue' },
    ]) + chartBox('月度收支与利润', 320)
      + card('月度财务明细', tableHtml(['月份', '收入(元)', '支出(元)', '利润(元)', '费用单数'],
        rows.slice().reverse().map(x => [esc(x.month), money(x.income), money(x.expense), money(x.profit), (x.expense_count || 0).toLocaleString()])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: { trigger: 'axis' }, legend: {}, grid: { left: 70, right: 20, bottom: 30 }, xAxis: { type: 'category', data: rows.map(x => x.month) }, yAxis: { type: 'value' }, series: [
        { name: '收入', type: 'bar', data: rows.map(x => x.income), itemStyle: { color: '#2563eb' } },
        { name: '支出', type: 'bar', data: rows.map(x => x.expense), itemStyle: { color: '#f59e0b' } },
        { name: '利润', type: 'line', data: rows.map(x => x.profit), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 数据总览 · 换电密集分布 ---- */
  async exchangeHeat(el) {
    const [peak, regions] = await Promise.all([api('/api/insights/exchange-peak'), api('/api/overview/regions')]);
    const total = (peak || []).reduce((a, x) => a + (x.count || 0), 0);
    const hot = (peak || []).reduce((m, x) => (x.count || 0) > (m.count || 0) ? x : m, {});
    el.innerHTML = kpiGrid([
      { label: '全天换电总量', value: total.toLocaleString(), cls: 'blue' },
      { label: '高峰时段', value: (hot.hour != null ? hot.hour : '-') + '时', cls: 'ok' },
      { label: '高峰单量', value: (hot.count || 0).toLocaleString(), cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('24小时换电密集分布', 320) + chartBox('区域换电分布 TOP12', 320) + `</div>`
      + card('区域换电明细', tableHtml(['城市', '换电柜', '30天换电'], (regions || []).slice(0, 12).map(x => [esc(bsShort(x.city)), x.exchange_count, (x.exchange_30d || 0).toLocaleString()])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 30 }, xAxis: { type: 'category', data: (peak || []).map(p => p.hour + '时') }, yAxis: { type: 'value' }, series: [{ type: 'line', smooth: true, data: (peak || []).map(p => p.count), itemStyle: { color: '#2563eb' }, areaStyle: { opacity: .15 } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: (regions || []).slice(0, 12).map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: (regions || []).slice(0, 12).map(x => x.exchange_30d), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 数据总览 · 用户车辆密集分布 ---- */
  async userBikeHeat(el) {
    const [cd, tier, s, dev] = await Promise.all([
      api('/api/users/city-detail'), api('/api/users/tier'), api('/api/users/summary'), api('/api/overview/device-dimension'),
    ]);
    const items = (cd.items || []).slice(0, 15);
    const bike = (dev.bike || {});
    el.innerHTML = kpiGrid([
      { label: '用户总数', value: (s.user_total || 0).toLocaleString(), cls: 'blue' },
      { label: '活跃用户(30d)', value: (s.active_30d || 0).toLocaleString(), cls: 'ok' },
      { label: '车辆总数', value: (bike.total || 0).toLocaleString(), cls: 'blue' },
      { label: '车辆在线', value: (bike.online || 0).toLocaleString(), cls: 'ok' },
      { label: '高频用户(30d)', value: (tier.frequency || {}).high || 0, cls: 'blue' },
      { label: '中频用户(30d)', value: (tier.frequency || {}).medium || 0, cls: 'blue' },
    ]) + `<div class="grid-2">` + chartBox('城市用户分布 TOP15', 320) + chartBox('用户频次分层', 320) + `</div>`
      + card('城市用户车辆明细', tableHtml(['城市', '用户数', '活跃用户(30d)', '协议数', '30天换电'],
        items.map(x => [esc(x.city || '-'), (x.users || 0).toLocaleString(), (x.active_users || 0).toLocaleString(), x.agreements || 0, (x.exchange_30d || 0).toLocaleString()])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: items.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: items.map(x => x.users), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: [
        { name: '高频(≥30次)', value: (tier.frequency || {}).high || 0 }, { name: '中频(10~29次)', value: (tier.frequency || {}).medium || 0 }, { name: '低频(1~9次)', value: (tier.frequency || {}).low || 0 },
      ] }] });
    }, 0);
  },

  /* ---- 销售 · 网点销售情况 ---- */
  async salesSite(el) {
    const d = (await api('/api/sales/site-rank?limit=20')) || [];
    el.innerHTML = kpiGrid([
      { label: '上榜网点', value: d.length, cls: 'blue' },
      { label: '合计换电', value: d.reduce((a, x) => a + (x.exchange_count || 0), 0).toLocaleString(), cls: 'blue' },
      { label: '合计利润(元)', value: money(d.reduce((a, x) => a + (x.profit_fee || 0), 0)), cls: 'ok' },
    ]) + chartBox('网点销售 TOP15', 320)
      + card('网点销售排行', tableHtml(['网点', '活跃用户', '换电次数', '收入(元)', '利润(元)'],
        d.map(x => [esc(x.site_name), x.active_users || 0, (x.exchange_count || 0).toLocaleString(), money(x.fee), money(x.profit_fee)])));
    setTimeout(() => {
      const c = d.slice(0, 15);
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 80 }, xAxis: { type: 'category', data: c.map(x => x.site_name), axisLabel: { rotate: 40, interval: 0 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: c.map(x => x.exchange_count), itemStyle: { color: '#2563eb' } }] });
    }, 0);
  },

  /* ---- 销售 · 业务销售业绩 ---- */
  async salesStaff(el) {
    const [rank, st] = await Promise.all([api('/api/sales/staff-rank?limit=20'), api('/api/staff/summary')]);
    el.innerHTML = kpiGrid([
      { label: '业务员(签约)', value: (rank || []).length, cls: 'blue' },
      { label: '合计签约', value: (rank || []).reduce((a, x) => a + (x.agreement_count || 0), 0).toLocaleString(), cls: 'ok' },
      { label: '合计客户', value: (rank || []).reduce((a, x) => a + (x.users || 0), 0).toLocaleString(), cls: 'blue' },
    ]) + chartBox('业务员签约 TOP15', 320)
      + card('业务员业绩排行', tableHtml(['业务员', '签约数', '客户数'],
        (rank || []).map(x => [esc(x.business_name), (x.agreement_count || 0).toLocaleString(), x.users || 0])));
    setTimeout(() => {
      const c = (rank || []).slice(0, 15);
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 80 }, xAxis: { type: 'category', data: c.map(x => x.business_name), axisLabel: { rotate: 40, interval: 0 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: c.map(x => x.agreement_count), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 销售 · 套餐购买明细 ---- */
  async salesPackage(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <select id="so_status"><option value="">全部状态</option><option value="success">成功</option><option value="cancelled">已取消</option></select>
        <button class="btn btn-primary" onclick="loadServiceOrder(1)">查询</button></div>
      <div id="so_box"></div>`;
    window.loadServiceOrder = async (page = 1) => {
      try {
        const st = document.getElementById('so_status').value;
        const d = await api(`/api/sales/service-orders?page=${page}&order_status=${encodeURIComponent(st)}`);
        document.getElementById('so_box').innerHTML =
          tableHtml(['订单号', '用户', '手机号', '商品类型', '数量', '实付(元)', '支付方式', '签约网点', '城市', '状态', '下单时间'],
            (d.items || []).map(x => [x.id, esc(x.buyer_user_name), esc(x.buyer_user_phone || '-'), esc(x.goods_type || '-'), x.goods_quantity,
              money(x.pay_fee), esc(x.pay_way || '-'), esc(x.sign_site_name || '-'), esc(x.sys_city_name || '-'),
              x.order_status === 'success' ? tag('成功', 'tag-ok') : esc(x.order_status), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadServiceOrder');
      } catch (e) { console.error(e); document.getElementById('so_box').innerHTML = dbErrorHtml(e); }
    };
    loadServiceOrder(1);
  },

  /* ---- 销售 · 协议签约明细 ---- */
  async salesAgreement(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="ag_kw" placeholder="用户名/手机号/城市">
        <select id="ag_status"><option value="">全部状态</option><option value="working">使用中</option><option value="owe_rent">欠费</option><option value="paused">已暂停</option><option value="stop">已停用</option><option value="cancelled">已取消</option></select>
        <button class="btn btn-primary" onclick="loadAgreement(1)">查询</button></div>
      <div id="ag_box"></div>`;
    window.loadAgreement = async (page = 1) => {
      try {
        const kw = document.getElementById('ag_kw').value;
        const st = document.getElementById('ag_status').value;
        const d = await api(`/api/users/agreements?page=${page}&keyword=${encodeURIComponent(kw)}&status=${st}`);
        document.getElementById('ag_box').innerHTML =
          tableHtml(['协议号', '用户', '手机号', '类型', '押金状态', '实缴押金(元)', '生效时间', '到期时间', '状态', '城市'],
            (d.items || []).map(x => [x.id, esc(x.user_name), esc(x.user_phone || '-'), esc(x.type || '-'),
              x.deposit_status === 'on' ? tag('在押', 'tag-ok') : tag('未押', 'tag-off'), money(x.deposit_real_fee),
              fmtTs(x.activation_time), fmtTs(x.rent_expire_time), tag(x.status_text || x.status, x.status === 'working' ? 'tag-ok' : x.status === 'owe_rent' ? 'tag-p1' : 'tag-p2'), esc(x.sys_city_name || '-')]))
          + pager(d.total, d.page, d.page_size, 'loadAgreement');
      } catch (e) { console.error(e); document.getElementById('ag_box').innerHTML = dbErrorHtml(e); }
    };
    loadAgreement(1);
  },

  /* ---- 销售 · 名下网点列表 ---- */
  async salesSiteList(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="ssl_kw" placeholder="网点名/地址/联系人">
        <select id="ssl_type"><option value="">全部类型</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select>
        <button class="btn btn-primary" onclick="loadSalesSiteList(1)">查询</button></div>
      <div id="ssl_box"></div>`;
    window.loadSalesSiteList = async (page = 1) => {
      try {
        const kw = document.getElementById('ssl_kw').value;
        const ty = document.getElementById('ssl_type').value;
        const d = await api(`/api/sites/list?page=${page}&keyword=${encodeURIComponent(kw)}&type=${ty}`);
        document.getElementById('ssl_box').innerHTML =
          tableHtml(['网点名称', '城市', '区域', '类型', '状态', '联系人', '电话', '地址', '创建时间'],
            (d.items || []).map(x => [esc(x.name), esc(x.city), esc(x.area || '-'), esc(String(x.type_text ?? x.type)),
              x.site_status === 'on' ? tag('在营', 'tag-ok') : tag('停业', 'tag-off'), esc(x.contact_person_name || '-'),
              esc(x.contact_person_tel || '-'), esc(x.address || '-'), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadSalesSiteList');
      } catch (e) { console.error(e); document.getElementById('ssl_box').innerHTML = dbErrorHtml(e); }
    };
    loadSalesSiteList(1);
  },

  /* ---- 网点 · 收支对账单 ---- */
  async siteStatement(el) {
    const [f, ex] = await Promise.all([api('/api/finance/summary'), api('/api/finance/expense-list?page=1&page_size=50')]);
    el.innerHTML = kpiGrid([
      { label: '近30天支出(元)', value: money(f.expense_fee), cls: 'warn' },
      { label: '费用单数', value: f.expense_count, cls: 'blue' },
      { label: '近30天收入(元)', value: money(f.income_fee), cls: 'ok' },
    ]) + chartBox('支出类型 TOP8', 300)
      + card('费用支出流水', tableHtml(['单号', '费用名称', '类型', '对方单位', '金额(元)', '状态', '时间'],
        (ex.items || []).map(x => [x.id, esc(x.expense_name || x.expense_description || '-'), esc(x.expense_type || '-'),
          esc(x.out_unit_name || '-'), money(x.fee), x.bill_status === 'settle' ? tag('已结算', 'tag-ok') : tag(x.bill_status, 'tag-p2'), fmtTs(x.create_time)])));
    const exTypes = (ex.items || []).reduce((m, x) => { const k = x.expense_type || 'other'; m[k] = (m[k] || 0) + (x.fee || 0); return m; }, {});
    const et = Object.entries(exTypes).sort((a, b) => b[1] - a[1]).slice(0, 8);
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 70, right: 20, bottom: 60 }, xAxis: { type: 'category', data: et.map(x => x[0]), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: et.map(x => x[1]), itemStyle: { color: '#f59e0b' } }] });
    }, 0);
  },

  /* ---- 网点 · 评估与发展 ---- */
  async siteEval(el) {
    const [s, regions, list] = await Promise.all([
      api('/api/sites/summary'), api('/api/overview/regions'), api('/api/sites/list?page=1&page_size=20'),
    ]);
    const r = (regions || []).slice(0, 12);
    el.innerHTML = kpiGrid([
      { label: '网点总数', value: s.site_total, cls: 'blue' },
      { label: '在营率', value: (s.site_total ? (s.site_open / s.site_total * 100).toFixed(1) : 0) + '%', cls: 'ok' },
      { label: '覆盖城市', value: (regions || []).length, cls: 'blue' },
      { label: '处理中工单', value: s.work_order_doing, cls: 'warn' },
    ]) + `<div class="grid-2">` + chartBox('城市网点数 TOP12', 320) + chartBox('城市30天换电 TOP12', 320) + `</div>`
      + card('重点网点样本', tableHtml(['网点名称', '城市', '区域', '类型', '状态', '联系人', '地址'],
        (list.items || []).map(x => [esc(x.name), esc(x.city), esc(x.area || '-'), esc(String(x.type_text ?? x.type)),
          x.site_status === 'on' ? tag('在营', 'tag-ok') : tag('停业', 'tag-off'), esc(x.contact_person_name || '-'), esc(x.address || '-')])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: r.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: r.map(x => x.site_count), itemStyle: { color: '#2563eb' } }] });
      drawChart(firstChartId(el, 1), { tooltip: {}, grid: { left: 60, right: 20, bottom: 60 }, xAxis: { type: 'category', data: r.map(x => bsShort(x.city)), axisLabel: { rotate: 30 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: r.map(x => x.exchange_30d), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 网点 · 基本表 ---- */
  async siteTables(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="st_kw" placeholder="网点名/地址/联系人">
        <select id="st_status"><option value="">全部状态</option><option value="on">在营</option><option value="off">停业</option></select>
        <button class="btn btn-primary" onclick="loadSiteTables(1)">查询</button></div>
      <div id="st_box"></div>`;
    window.loadSiteTables = async (page = 1) => {
      try {
        const kw = document.getElementById('st_kw').value;
        const st = document.getElementById('st_status').value;
        const d = await api(`/api/sites/list?page=${page}&keyword=${encodeURIComponent(kw)}&status=${st}`);
        document.getElementById('st_box').innerHTML =
          tableHtml(['网点名称', '城市', '区域', '类型', '状态', '联系人', '电话', '经理', '客户', '地址', '创建时间'],
            (d.items || []).map(x => [esc(x.name), esc(x.city), esc(x.area || '-'), esc(String(x.type_text ?? x.type)),
              x.site_status === 'on' ? tag('在营', 'tag-ok') : tag('停业', 'tag-off'), esc(x.contact_person_name || '-'),
              esc(x.contact_person_tel || '-'), esc(x.store_manager_name || '-'), esc(x.customer_name || '-'),
              esc(x.address || '-'), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadSiteTables');
      } catch (e) { console.error(e); document.getElementById('st_box').innerHTML = dbErrorHtml(e); }
    };
    loadSiteTables(1);
  },

  /* ---- 网点 · 销售业绩 ---- */
  async siteSales(el) {
    const d = (await api('/api/sales/site-rank?limit=20')) || [];
    el.innerHTML = kpiGrid([
      { label: '上榜网点', value: d.length, cls: 'blue' },
      { label: '合计换电', value: d.reduce((a, x) => a + (x.exchange_count || 0), 0).toLocaleString(), cls: 'blue' },
      { label: '合计利润(元)', value: money(d.reduce((a, x) => a + (x.profit_fee || 0), 0)), cls: 'ok' },
    ]) + chartBox('网点业绩 TOP15', 320)
      + card('网点销售排行', tableHtml(['网点', '活跃用户', '换电次数', '收入(元)', '利润(元)'],
        d.map(x => [esc(x.site_name), x.active_users || 0, (x.exchange_count || 0).toLocaleString(), money(x.fee), money(x.profit_fee)])));
    setTimeout(() => {
      const c = d.slice(0, 15);
      drawChart(firstChartId(el, 0), { tooltip: {}, grid: { left: 60, right: 20, bottom: 80 }, xAxis: { type: 'category', data: c.map(x => x.site_name), axisLabel: { rotate: 40, interval: 0 } }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: c.map(x => x.exchange_count), itemStyle: { color: '#16a34a' } }] });
    }, 0);
  },

  /* ---- 网点 · 单网点视图 ---- */
  async siteDetail(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="sd_site" placeholder="网点名称(精确)">
        <button class="btn btn-primary" onclick="loadSiteOrders(1)">查询该网点订单</button></div>
      <div id="sd_box"></div>`;
    window.loadSiteOrders = async (page = 1) => {
      try {
        const name = document.getElementById('sd_site').value.trim();
        if (!name) { document.getElementById('sd_box').innerHTML = '<div class="empty">请输入网点名称</div>'; return; }
        const hit = await api(`/api/sites/list?keyword=${encodeURIComponent(name)}&page_size=5`);
        const site = (hit.items || []).find(x => x.name === name) || (hit.items || [])[0];
        if (!site) { document.getElementById('sd_box').innerHTML = '<div class="empty">未找到该网点</div>'; return; }
        const d = await api(`/api/sites/orders?page=${page}&site_id=${site.id}`);
        document.getElementById('sd_box').innerHTML =
          `<div class="kpi-sub">网点：${esc(site.name)}（${esc(site.city)}） 共 ${d.total} 单</div>` +
          tableHtml(['订单号', '网点', '用户', '手机号', '柜SN', '电池SN', '车辆SN', '实付(元)', '利润(元)', '首换', '时间'],
            (d.items || []).map(x => [x.id, esc(x.site_name || '-'), esc(x.take_user_name || '-'), esc(x.take_user_phone || '-'),
              esc(x.take_exchange_sn || '-'), esc(x.take_battery_sn || '-'), esc(x.bike_sn || '-'),
              money(x.real_pay_price), money(x.profit_fee), x.is_first_take ? tag('首换', 'tag-ok') : '-', fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadSiteOrders');
      } catch (e) { console.error(e); document.getElementById('sd_box').innerHTML = dbErrorHtml(e); }
    };
    loadSiteOrders(1);
  },

  /* ---- 资产 · 换电柜 ---- */
  async assetExchange(el) {
    el.innerHTML = `<div id="ax_kpi"></div>
      <div class="filters" style="margin-bottom:10px">
        <select id="ax_status"><option value="">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select>
        <input class="input" id="ax_kw" placeholder="柜号/名称/地址">
        <button class="btn btn-primary" onclick="loadAssetExchange(1)">查询</button></div>
      <div id="ax_box"></div>`;
    window.loadAssetExchange = async (page = 1) => {
      try {
        const st = document.getElementById('ax_status').value;
        const kw = document.getElementById('ax_kw').value;
        const d = await api(`/api/devices/exchanges?page=${page}&status=${st}&keyword=${encodeURIComponent(kw)}`);
        const s = d.stats;
        document.getElementById('ax_kpi').innerHTML = kpiGrid([
          { label: '换电柜总数', value: s.total, cls: 'blue' }, { label: '在线', value: s.online, cls: 'ok' }, { label: '离线', value: s.offline, cls: 'warn' },
        ]);
        document.getElementById('ax_box').innerHTML =
          tableHtml(['柜号', '设备名称', '客户', '状态', '总仓', '满仓', '充电中', '空仓', '烟感', '水浸', '火警', '摆放位置', '地址', '最后上报'],
            d.items.map(x => [esc(x.device_sn), esc(x.device_name || '-'), esc(x.customer_name), statusTag(x.online_status),
              x.slot_total, x.slot_full, x.slot_charging, x.slot_empty,
              x.smoke === '1' ? tag('告警', 'tag-p0') : '-', x.flooded === '1' ? tag('告警', 'tag-p0') : '-', x.fire === '1' ? tag('告警', 'tag-p0') : '-',
              esc(x.site_placement || '-'), esc(x.last_location_address || '-'), fmtTs(x.last_upload_time)]))
          + pager(d.total, d.page, d.page_size, 'loadAssetExchange');
      } catch (e) { console.error(e); document.getElementById('ax_box').innerHTML = dbErrorHtml(e); }
    };
    loadAssetExchange(1);
  },

  /* ---- 资产 · 电池 ---- */
  async assetBattery(el) {
    el.innerHTML = `<div id="ab_kpi"></div>
      <div class="filters" style="margin-bottom:10px">
        <select id="ab_status"><option value="">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select>
        <input class="input" id="ab_kw" placeholder="电池SN/柜号/地址">
        <button class="btn btn-primary" onclick="loadAssetBattery(1)">查询</button></div>
      <div id="ab_box"></div>`;
    window.loadAssetBattery = async (page = 1) => {
      try {
        const st = document.getElementById('ab_status').value;
        const kw = document.getElementById('ab_kw').value;
        const d = await api(`/api/devices/batteries?page=${page}&status=${st}&keyword=${encodeURIComponent(kw)}`);
        const s = d.stats;
        document.getElementById('ab_kpi').innerHTML = kpiGrid([
          { label: '电池总数', value: s.total, cls: 'blue' }, { label: '在线', value: s.online, cls: 'ok' }, { label: '离线', value: s.offline, cls: 'warn' },
        ]);
        document.getElementById('ab_box').innerHTML =
          tableHtml(['电池SN', '客户', '电池状态', '在线', '类型', '电量%', '电压V', '充电', '所在柜', '供应商', '地址', '最后上报'],
            d.items.map(x => [esc(x.device_sn), esc(x.customer_name), esc(x.battery_status || '-'), statusTag(x.online_status),
              esc(x.type || '-'), x.power != null ? x.power : '-', x.voltage != null ? x.voltage : '-',
              x.charging === '1' ? tag('充电中', 'tag-ok') : '-', esc(x.last_upload_exchange_sn || '-'),
              esc(x.supplier_name || '-'), esc(x.last_location_address || '-'), fmtTs(x.last_battery_upload_time)]))
          + pager(d.total, d.page, d.page_size, 'loadAssetBattery');
      } catch (e) { console.error(e); document.getElementById('ab_box').innerHTML = dbErrorHtml(e); }
    };
    loadAssetBattery(1);
  },

  /* ---- 资产 · 车辆 ---- */
  async assetBike(el) {
    const [s, dev] = await Promise.all([api('/api/assets/summary'), api('/api/overview/device-dimension')]);
    const bike = s.bike || {}, devb = (dev.bike || {});
    el.innerHTML = kpiGrid([
      { label: '车辆总数', value: (bike.total || 0).toLocaleString(), cls: 'blue' },
      { label: '车辆在线', value: (bike.online || 0).toLocaleString(), cls: 'ok' },
      { label: '车辆离线', value: (devb.offline || 0).toLocaleString(), cls: 'warn' },
    ]) + chartBox('车辆在线构成', 300)
      + card('车辆资产明细', tableHtml(['资产项', '数量'],
        [['车辆总数', (bike.total || 0).toLocaleString()], ['车辆在线', (bike.online || 0).toLocaleString()], ['车辆离线', (devb.offline || 0).toLocaleString()]]));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: [
        { name: '车辆在线', value: bike.online || 0 }, { name: '车辆离线', value: devb.offline || 0 },
      ] }] });
    }, 0);
  },

  /* ---- 资产 · 仓库 ---- */
  async assetWarehouse(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <input class="input" id="aw_kw" placeholder="电池SN">
        <button class="btn btn-primary" onclick="loadAssetTransfer(1, 'aw')">查询</button></div>
      <div id="aw_box"></div>`;
    window.loadAssetTransfer = async (page = 1, box = 'aw') => {
      try {
        const kw = document.getElementById(box + '_kw').value;
        const d = await api(`/api/assets/transfer-logs?page=${page}&keyword=${encodeURIComponent(kw)}`);
        document.getElementById(box + '_box').innerHTML =
          tableHtml(['ID', '电池SN', '流转类型', '流转状态', '流入', '流出', '时间'],
            (d.items || []).map(x => [x.id, esc(x.battery_device_sn), esc(x.transfer_type || '-'), esc(x.transfer_status || '-'),
              esc(x.inflow_name || '-'), esc(x.outflow_name || '-'), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, `loadAssetTransfer(1, '${box}')`);
      } catch (e) { console.error(e); document.getElementById(box + '_box').innerHTML = dbErrorHtml(e); }
    };
    loadAssetTransfer(1, 'aw');
  },

  /* ---- 资产 · 流通 ---- */
  async assetFlow(el) {
    el.innerHTML = `<div id="af_box"></div>`;
    window.loadAssetFlow = async (page = 1) => {
      try {
        const d = await api(`/api/assets/transfer-logs?page=${page}&page_size=30`);
        document.getElementById('af_box').innerHTML =
          tableHtml(['ID', '电池SN', '流转类型', '流转状态', '流入', '流出', '时间'],
            (d.items || []).map(x => [x.id, esc(x.battery_device_sn), esc(x.transfer_type || '-'), esc(x.transfer_status || '-'),
              esc(x.inflow_name || '-'), esc(x.outflow_name || '-'), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadAssetFlow');
      } catch (e) { console.error(e); document.getElementById('af_box').innerHTML = dbErrorHtml(e); }
    };
    loadAssetFlow(1);
  },

  /* ---- 资产 · 调拨 ---- */
  async assetTransfer(el) {
    el.innerHTML = `<div class="filters" style="margin-bottom:10px">
        <select id="at_type"><option value="">全部流转</option><option value="1">换柜流转</option><option value="2">维修流转</option></select>
        <button class="btn btn-primary" onclick="loadAssetTransferList(1)">查询</button></div>
      <div id="at_box"></div>`;
    window.loadAssetTransferList = async (page = 1) => {
      try {
        const ty = document.getElementById('at_type').value;
        const d = await api(`/api/assets/transfer-logs?page=${page}&transfer_type=${ty}`);
        document.getElementById('at_box').innerHTML =
          tableHtml(['ID', '电池SN', '流转类型', '流转状态', '流入', '流出', '时间'],
            (d.items || []).map(x => [x.id, esc(x.battery_device_sn), esc(x.transfer_type || '-'), esc(x.transfer_status || '-'),
              esc(x.inflow_name || '-'), esc(x.outflow_name || '-'), fmtTs(x.create_time)]))
          + pager(d.total, d.page, d.page_size, 'loadAssetTransferList');
      } catch (e) { console.error(e); document.getElementById('at_box').innerHTML = dbErrorHtml(e); }
    };
    loadAssetTransferList(1);
  },

  /* ---- 资产 · 出入库 ---- */
  async assetInout(el) {
    const d = await api('/api/assets/transfer-logs?page=1&page_size=50');
    const flow = (d.items || []).reduce((m, x) => { const k = x.transfer_type || 'other'; m[k] = (m[k] || 0) + 1; return m; }, {});
    const ft = Object.entries(flow);
    el.innerHTML = kpiGrid([
      { label: '流转总数', value: d.total, cls: 'blue' },
      { label: '流转类型数', value: ft.length, cls: 'blue' },
    ]) + chartBox('流转类型构成', 300)
      + card('最近流转记录', tableHtml(['ID', '电池SN', '流转类型', '流转状态', '流入', '流出', '时间'],
        (d.items || []).slice(0, 30).map(x => [x.id, esc(x.battery_device_sn), esc(x.transfer_type || '-'), esc(x.transfer_status || '-'),
          esc(x.inflow_name || '-'), esc(x.outflow_name || '-'), fmtTs(x.create_time)])));
    setTimeout(() => {
      drawChart(firstChartId(el, 0), { tooltip: {}, series: [{ type: 'pie', radius: '60%', data: ft.map(x => ({ name: x[0], value: x[1] })) }] });
    }, 0);
  },

  /* ---- 资产 · 故障 ---- */
  async assetFault(el) {
    const [s, wo] = await Promise.all([api('/api/assets/summary'), api('/api/assets/work-orders?page=1&page_size=30')]);
    el.innerHTML = kpiGrid([
      { label: '电池异常', value: (s.battery || {}).fault, cls: 'danger' },
      { label: '换电柜总数', value: (s.exchange || {}).total, cls: 'blue' },
      { label: '电池总数', value: (s.battery || {}).total, cls: 'blue' },
    ]) + card('维修工单', tableHtml(['工单号', '事件类型', '事件名称', '地址', '状态', '优先级', '创建人', '处理人', '创建时间', '处理结束'],
        (wo.items || []).map(x => [esc(x.event_id || x.id), esc(x.event_type || '-'), esc(x.event_name || '-'), esc(x.address || '-'),
          esc(x.status || '-'), esc(x.priority || '-'), esc(x.creator_name || '-'), esc(x.handler_name || '-'), fmtTs(x.create_time), fmtTs(x.handle_stop_time)])));
  },

  /* ---- 占位 ---- */
  async placeholder(el) {
    el.innerHTML = placeholderHtml();
  },
};

function firstChartId(el, idx) {
  const cards = el.querySelectorAll('.chart');
  return cards[idx] ? cards[idx].id : '';
}

window.exportCsv = function (type) {
  const params = new URLSearchParams();
  if (type === 'exchange') {
    params.set('type', 'exchange');
    params.set('status', document.getElementById('ex_status')?.value || '');
    params.set('keyword', document.getElementById('ex_kw')?.value || '');
  } else if (type === 'battery') {
    params.set('type', 'battery');
    params.set('status', document.getElementById('bt_status')?.value || '');
    params.set('power_min', document.getElementById('bt_pmin')?.value || '');
    params.set('power_max', document.getElementById('bt_pmax')?.value || '');
    params.set('keyword', document.getElementById('bt_kw')?.value || '');
  } else if (type === 'alarm') {
    params.set('type', 'alarm');
    params.set('device_type', document.getElementById('al_dev')?.value || 'all');
    params.set('alarm_type', document.getElementById('al_type')?.value || '');
  }
  window.open('/api/devices/export?' + params.toString(), '_blank');
};

/* ---------- 登录 / 用户 ---------- */
async function init() {
  try {
    currentUser = await api('/api/auth/me');
  } catch (e) {
    window.location.href = '/login.html';
    return;
  }
  document.getElementById('btnUserMenu').textContent = (currentUser.display_name || currentUser.username) + ' ▾';
  document.getElementById('dropRole').textContent = '角色：' + (currentUser.role_name || currentUser.role);
  if (currentUser.permissions.includes('admin:user')) {
    document.getElementById('dropAdmin').style.display = 'block';
    document.getElementById('dropRoleAdmin').style.display = 'block';
  }
  render();
}

document.getElementById('btnUserMenu').addEventListener('click', () => {
  document.getElementById('userDropdown').style.display = document.getElementById('userDropdown').style.display === 'none' ? 'block' : 'none';
});
document.getElementById('dropLogout').addEventListener('click', async () => {
  await api('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login.html';
});
document.getElementById('dropAdmin').addEventListener('click', openAdmin);
document.getElementById('dropRoleAdmin').addEventListener('click', openRoleAdmin);

window.addEventListener('click', (e) => {
  if (!e.target.closest('.user-menu')) document.getElementById('userDropdown').style.display = 'none';
});

/* ---------- 角色管理 ---------- */
let roleList = [];
let roleEditingId = null;

async function openRoleAdmin() {
  document.getElementById('roleModal').style.display = 'flex';
  await loadRoles();
}
function closeRole() { document.getElementById('roleModal').style.display = 'none'; }
window.closeRole = closeRole;

async function loadRoles() {
  roleList = await api('/api/admin/roles');
  renderRoleTable();
}

function renderRoleTable() {
  const wrap = document.getElementById('roleList');
  if (!roleList.length) { wrap.innerHTML = '<div class="td-empty">暂无角色</div>'; return; }
  wrap.innerHTML = roleList.map(r => `
    <div class="role-item">
      <div class="role-item-head">
        <span class="role-name">${esc(r.name)}</span>
        <span class="role-key">${esc(r.key)}</span>
        ${r.is_system ? tag('内置', 'tag-ok') : ''}
        <span class="role-spacer"></span>
        <button class="btn btn-ghost-dark" onclick="toggleRoleEdit(${r.id})">编辑权限</button>
        ${r.is_system ? '' : `<button class="btn btn-danger-dark" onclick="delRole(${r.id})">删除</button>`}
      </div>
      <div class="role-perms">${(r.permissions || []).map(p => {
        const m = PERM_META.find(x => x.key === p);
        return `<span class="tag tag-blue">${esc(m ? m.name : p)}</span>`;
      }).join('') || '<span class="muted">未分配模块权限</span>'}</div>
      <div class="role-edit" id="roleEdit_${r.id}" style="display:none"></div>
    </div>`).join('');
}

function toggleRoleEdit(id) {
  const r = roleList.find(x => x.id === id);
  const box = document.getElementById('roleEdit_' + id);
  if (box.style.display === 'none') {
    box.style.display = 'block';
    box.innerHTML = `<div class="perm-grid">${PERM_META.map(p => `
      <label class="perm-item"><input type="checkbox" value="${p.key}" ${(r.permissions || []).includes(p.key) ? 'checked' : ''}> ${esc(p.name)}</label>`).join('')}</div>
      <button class="btn btn-primary" onclick="saveRolePerms(${r.id})">保存权限</button>
      <button class="btn btn-ghost-dark" onclick="toggleRoleEdit(${r.id})">收起</button>`;
    roleEditingId = id;
  } else {
    box.style.display = 'none';
    box.innerHTML = '';
    roleEditingId = null;
  }
}
window.toggleRoleEdit = toggleRoleEdit;

async function saveRolePerms(id) {
  const box = document.getElementById('roleEdit_' + id);
  const perms = Array.from(box.querySelectorAll('input[type=checkbox]:checked')).map(x => x.value);
  const name = roleList.find(x => x.id === id).name;
  await api(`/api/admin/roles/${id}`, { method: 'PUT', body: JSON.stringify({ name, permissions: perms }) });
  await loadRoles();
}
window.saveRolePerms = saveRolePerms;

async function createRole() {
  const key = document.getElementById('r_key').value.trim();
  const name = document.getElementById('r_name').value.trim();
  if (!key || !name) { alert('请填写角色标识和名称'); return; }
  await api('/api/admin/roles', { method: 'POST', body: JSON.stringify({ key, name, permissions: [] }) });
  document.getElementById('r_key').value = '';
  document.getElementById('r_name').value = '';
  await loadRoles();
}
window.createRole = createRole;

async function delRole(id) {
  const r = roleList.find(x => x.id === id);
  if (!confirm(`确认删除角色「${r.name}」？`)) return;
  await api(`/api/admin/roles/${id}`, { method: 'DELETE' });
  await loadRoles();
}
window.delRole = delRole;

/* 用户管理 */
let adminUsers = [];
let adminRoles = [];
async function openAdmin() {
  document.getElementById('adminModal').style.display = 'flex';
  const [users, roles] = await Promise.all([api('/api/admin/users'), api('/api/admin/roles')]);
  adminUsers = users;
  adminRoles = roles;
  renderAdminRoleOptions();
  renderAdminTable();
}
function closeAdmin() { document.getElementById('adminModal').style.display = 'none'; }
window.closeAdmin = closeAdmin;

function renderAdminRoleOptions() {
  document.getElementById('u_role').innerHTML = adminRoles.map(r =>
    `<option value="${esc(r.key)}">${esc(r.name)}</option>`).join('');
}

function renderAdminTable() {
  const tbody = document.querySelector('#adminUserTable tbody');
  const roleName = (key) => { const r = adminRoles.find(x => x.key === key); return r ? r.name : key; };
  tbody.innerHTML = adminUsers.map(u => `<tr>
    <td>${u.id}</td><td>${esc(u.username)}</td><td>${esc(roleName(u.role))}</td>
    <td>${esc((u.oem_ids || []).join(','))}</td>
    <td><button class="btn btn-ghost-dark" onclick="editAdmin(${u.id})">编辑</button>
        <button class="btn btn-danger-dark" onclick="delAdmin(${u.id})">删除</button></td></tr>`).join('');
}

function editAdmin(id) {
  const u = adminUsers.find(x => x.id === id);
  document.getElementById('u_id').value = u.id;
  document.getElementById('u_username').value = u.username;
  document.getElementById('u_password').value = '';
  document.getElementById('u_role').value = u.role;
  document.getElementById('u_oem_ids').value = (u.oem_ids || []).join(',');
  document.getElementById('u_display_name').value = u.display_name || '';
}
window.editAdmin = editAdmin;

async function delAdmin(id) {
  if (!confirm('确认删除该用户？')) return;
  await api(`/api/admin/users/${id}`, { method: 'DELETE' });
  openAdmin();
}
window.delAdmin = delAdmin;

document.getElementById('userForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = document.getElementById('u_id').value;
  const body = {
    username: document.getElementById('u_username').value.trim(),
    password: document.getElementById('u_password').value,
    role: document.getElementById('u_role').value,
    oem_ids: document.getElementById('u_oem_ids').value.split(',').map(s => s.trim()).filter(Boolean),
    display_name: document.getElementById('u_display_name').value.trim(),
  };
  if (id) {
    await api(`/api/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(body) });
  } else {
    await api('/api/admin/users', { method: 'POST', body: JSON.stringify(body) });
  }
  document.getElementById('userForm').reset();
  openAdmin();
});

init();
