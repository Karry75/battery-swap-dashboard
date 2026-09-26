/* 公网静态快照模式（GitHub Pages / 任意静态托管）
 *
 * 作用：把前端 app.js 发出的 /api/xxx 请求，重定向到 docs/data/ 下的静态 JSON 快照。
 * 这样即使不连数据库、没有后端进程，页面也能展示"最后一次连接数据库"的完整内容。
 * 快照由 scripts/refresh_public_snapshot.py 生成，已做隐私脱敏。
 */
(function () {
  const DATA_BASE = 'data/';
  const origFetch = window.fetch ? window.fetch.bind(window) : null;

  const DEMO_USER = {
    id: 0,
    username: 'demo',
    role: 'demo',
    role_name: '公开演示版',
    display_name: '公开演示版',
    oem_ids: [],
    // 放开全部"查看"权限，保证静态版菜单与本地版一致；故意不含 admin:user（用户/角色管理为交互式后台功能）
    permissions: [
      'overview:view', 'user:view', 'sales:view', 'site:view', 'asset:view',
      'coupon:view', 'dashboard:view', 'staff:view', 'finance:view',
      'service:view', 'analysis:view',
    ],
  };

  /* 与 scripts/refresh_public_snapshot.py 的 file_key() 保持一致的命名规则 */
  const KEEP_PARAMS = ['city', 'days', 'months', 'limit'];
  /* 参数值归一化：只保留字母/数字/中文/连字符/下划线，避免文件名里出现需要 URL 编码的字符
     （静态服务器与 GitHub Pages 都会对路径做一次百分号解码，若文件名含 %3D 会取不到文件） */
  function keySafe(s) {
    return String(s).replace(/[^0-9A-Za-z\u4e00-\u9fff_-]/g, '');
  }

  /* 把一个 /api 请求映射为若干候选快照名（按优先级），例如
       /api/bigscreen/trend?city=深圳市&months=12
         -> bigscreen_trend__city-深圳市.months-12.json
            bigscreen_trend__city-深圳市.json
            bigscreen_trend__months-12.json
            bigscreen_trend.json
     多参数组合未必都生成了快照，按候选逐个回落，避免整页 404。 */
  function candidates(pathname, search) {
    const base = baseName(pathname);
    const q = new URLSearchParams(search || '');
    const kept = [];
    KEEP_PARAMS.forEach(function (k) {
      const v = q.get(k);
      if (v) kept.push(k + '-' + keySafe(v));
    });
    const mk = function (arr) { return arr.length ? base + '__' + arr.join('.') : ''; };
    const out = [];
    if (kept.length) out.push(mk(kept));
    if (kept.length > 1) {
      const city = kept.filter(function (s) { return s.indexOf('city-') === 0; });
      const other = kept.filter(function (s) { return s.indexOf('city-') !== 0; });
      if (mk(city)) out.push(mk(city));
      if (mk(other)) out.push(mk(other));
    }
    out.push(base);
    return out.filter(function (n, i) { return out.indexOf(n) === i; });
  }

  function jsonResponse(payload, status) {
    return new Response(JSON.stringify(payload), {
      status: status || 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  async function readJSON(url) {
    try {
      const r = await origFetch(url, { cache: 'no-cache' });
      if (!r.ok) return null;
      return await r.json();
    } catch (e) {
      return null;
    }
  }

  /* 快照清单：用于在参数不完全匹配时（如 limit=15 只生成了 limit=20）回落取近似快照 */
  let META = null;
  let META_P = null;
  function loadMeta() {
    if (!META_P) {
      META_P = readJSON(DATA_BASE + 'api_meta.json').then(function (m) { META = m; return m; }).catch(function () { return null; });
    }
    return META_P;
  }
  function baseName(pathname) {
    return pathname.replace(/^\/api\//, '').replace(/\//g, '_');
  }

  /* 快照缺失时的兜底结构（交互式下钻页面在静态版无法实时查询） */
  function fallbackData(pathname) {
    if (pathname === '/api/users/detail') {
      return { user: null, filters: {}, agreements: [], rents: [], orders: [], alarms: [], rents_total: 0 };
    }
    if (pathname === '/api/sites/orders') return { rows: [], total: 0 };
    if (pathname === '/api/admin/roles' || pathname === '/api/admin/users') return [];
    return undefined;
  }

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    if (url.indexOf('/api/') === -1 || !origFetch) {
      return origFetch ? origFetch(input, init) : jsonResponse({ code: 404, msg: '静态模式不支持该请求' }, 404);
    }

    const u = new URL(url, location.href);
    const pathname = u.pathname.replace(/^\/battery-swap-dashboard/, '');

    if (pathname === '/api/auth/me') return jsonResponse({ code: 0, msg: 'ok', data: DEMO_USER });
    if (method !== 'GET') return jsonResponse({ code: 0, msg: 'ok', data: null }); // 登录/登出/写操作在静态版为空操作

    /* 先用 api_meta.json 过滤出确实存在的候选快照，避免产生 404 请求 */
    let names = candidates(pathname, u.search);
    const meta = await loadMeta();
    const files = (meta && Array.isArray(meta.files)) ? meta.files : null;
    if (files) {
      const exist = names.filter(function (n) { return files.indexOf(n + '.json') !== -1; });
      if (exist.length) {
        names = exist;
      } else {
        /* 该参数版本没有快照：借用同接口的其它快照（如 limit=15 借 limit=20） */
        const prefix = baseName(pathname) + '__';
        const hasCity = !!new URLSearchParams(u.search || '').get('city');
        const pool = files.filter(function (f) {
          return f.indexOf(prefix) === 0 && (!hasCity || f.indexOf('city') === -1);
        });
        const pick = pool[0] || files.filter(function (f) { return f.indexOf(prefix) === 0; })[0];
        if (pick) names = [pick.replace(/\.json$/, '')];
      }
    }
    let payload = null;
    for (let i = 0; i < names.length; i++) {
      payload = await readJSON(DATA_BASE + names[i] + '.json');
      if (payload && payload.code === 0) break;
    }
    if (payload && payload.code === 0) return jsonResponse(payload);

    const fb = fallbackData(pathname);
    if (fb !== undefined) return jsonResponse({ code: 0, msg: 'ok', data: fb });
    return jsonResponse({ code: 501, msg: '公开演示版（静态快照）未包含该接口：' + pathname });
  };

  /* 导出 / 服务端下载在静态版不可用 */
  const origOpen = window.open;
  window.open = function (url) {
    if (typeof url === 'string' && url.indexOf('/api/') === 0) {
      window.alert('公开演示版为静态快照，不提供导出下载。完整功能请访问本地服务。');
      return null;
    }
    return origOpen.apply(window, arguments);
  };

  /* 顶部快照说明条 */
  function renderNotice(meta) {
    const el = document.createElement('div');
    el.className = 'public-notice';
    const at = (meta && meta.snapshot_at) || '未知';
    el.innerHTML = '<b>公网静态演示版</b> · 数据为脱敏快照（' + at + '）· 页面不依赖数据库，断网可查看 · 筛选/分页/导出为只读演示';
    document.body.insertBefore(el, document.body.firstChild);
  }

  document.addEventListener('DOMContentLoaded', async function () {
    const meta = await readJSON(DATA_BASE + 'api_meta.json');
    renderNotice(meta);
    document.title = '换电运营平台 · 数据快照 (' + ((meta && meta.snapshot_at) || '') + ')';
  });
})();
