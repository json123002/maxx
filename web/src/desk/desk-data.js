/* ===== 我的工作台 数据层 =====
   实时行情/盘口异动走东财 JSONP 直连(与板块资金雷达同模式);
   自选/星标/F10 资料走后端 API;资金流日K复用 analysis 取数链。 */
import { jsonp } from "../utils/jsonp";
import { api } from "../api/client";
import { fetchHis, secidOf } from "../analysis/data";

const DELAY_HOST = "https://push2delay.eastmoney.com";
const CHANGES_HOST = "https://push2ex.eastmoney.com";

/* ---------- 实时行情(含主力净流入 f62 / 主力净占比 f184) ---------- */
const QUOTE_FIELDS = "f12,f14,f2,f3,f6,f8,f10,f17,f62,f184";

export async function fetchLiveQuotes(codes) {
  if (!codes.length) return {};
  const out = {};
  // secids 过长会被截断,按 60 只一批分片
  for (let i = 0; i < codes.length; i += 60) {
    const secids = codes.slice(i, i + 60).map(secidOf).join(",");
    const d = await jsonp(`${DELAY_HOST}/api/qt/ulist.np/get?fltt=2` +
      `&secids=${encodeURIComponent(secids)}&fields=${QUOTE_FIELDS}`);
    for (const r of d?.data?.diff || []) {
      if (r?.f12) out[String(r.f12)] = r;
    }
  }
  return out;
}

/* ---------- 盘口异动(大资金动向) ---------- */
// 类型码 ↔ 名称(东财 push2ex 口径);dir 用于着色:bull 偏多 / bear 偏空
export const CHANGE_TYPES = {
  8193: { name: "大笔买入", dir: "bull" },
  8194: { name: "大笔卖出", dir: "bear" },
  8201: { name: "火箭发射", dir: "bull" },
  8202: { name: "快速反弹", dir: "bull" },
  8203: { name: "高台跳水", dir: "bear" },
  8204: { name: "加速下跌", dir: "bear" },
  4:    { name: "封涨停板", dir: "bull" },
  8:    { name: "封跌停板", dir: "bear" },
  16:   { name: "打开涨停", dir: "bear" },
  32:   { name: "打开跌停", dir: "bull" },
  64:   { name: "有大买盘", dir: "bull" },
  128:  { name: "有大卖盘", dir: "bear" },
  8213: { name: "60日新高", dir: "bull" },
  8214: { name: "60日新低", dir: "bear" },
};
const CHANGE_TYPE_PARAM = Object.keys(CHANGE_TYPES).join(",");

// 单笔拉全市场今日异动,调用方按自选过滤;i 字段结构随类型而异(已实测):
// 8193/8194/64/128 大笔/买卖盘: "量,价,涨跌幅,金额"   4/8 封板: "价,量,价,涨跌幅"
// 16/32 开板: "价,涨跌幅"   8201-8204 火箭/跳水类: "涨跌幅,价,涨跌幅"   8213/8214 新高新低: "价,价,涨跌幅"
// 涨跌幅均为小数比率(0.0954 = 9.54%),统一 ×100 输出
const MONEY_T = new Set([8193, 8194, 64, 128]);
const SEAL_T = new Set([4, 8]);
const OPEN_T = new Set([16, 32]);
const HILO_T = new Set([8213, 8214]);

export async function fetchChanges() {
  const d = await jsonp(`${CHANGES_HOST}/getAllStockChanges` +
    `?type=${CHANGE_TYPE_PARAM}&pageindex=0&pagesize=200` +
    `&ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wzchanges`);
  const rows = [];
  for (const r of d?.data?.allstock || []) {
    const meta = CHANGE_TYPES[r.t];
    if (!meta || !r.c) continue;
    const a = String(r.i || "").split(",").map(Number);
    let price = null, pct = null, amount = null;
    if (MONEY_T.has(r.t)) { price = a[1]; pct = a[2]; amount = a[3]; }
    else if (SEAL_T.has(r.t)) { price = a[0]; pct = a[3]; }
    else if (OPEN_T.has(r.t)) { price = a[0]; pct = a[1]; }
    else if (HILO_T.has(r.t)) { price = a[0]; pct = a[2]; }
    else { pct = a[0]; price = a[1]; }
    rows.push({
      time: String(r.tm || "").padStart(6, "0")
        .replace(/(\d{2})(\d{2})(\d{2})/, "$1:$2:$3"),
      code: String(r.c),
      name: r.n || "",
      type: meta.name,
      dir: meta.dir,
      price,
      pct: Number.isFinite(pct) ? pct * 100 : null,
      amount: Number.isFinite(amount) ? amount : null,
    });
  }
  return rows.sort((x, y) => (x.time < y.time ? 1 : -1));
}

/* ---------- 近 20 日资金流(主力/超大/大/中/小单) ---------- */
export async function fetchMoneyFlow20(code) {
  const d = await fetchHis(
    "/api/qt/stock/fflow/daykline/get?secid=" + secidOf(code) +
    "&klt=101&lmt=20&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56", "");
  return (d.klines || []).map((s) => {
    const a = s.split(",");
    return { date: a[0], main: +a[1], small: +a[2], mid: +a[3], big: +a[4], super: +a[5] };
  }).filter((b) => isFinite(b.main));
}

/* ---------- 星标 / F10(后端) ---------- */
export const fetchStars = () => api("/api/desk/star");
export const addStar = (code) =>
  api("/api/desk/star", { method: "POST", body: { code } });
export const removeStar = (code) =>
  api("/api/desk/star/" + code, { method: "DELETE" });
export const fetchF10 = (code) => api("/api/desk/f10/" + code);

/* ---------- 同花顺挂单异动(后端采集):L2 特大挂买/撤单/压托单 ---------- */
export const fetchThsEvents = (code) => api("/api/desk/ths/events/" + code);

/* ---------- 工作台股票池(独立于自选) ---------- */
export const fetchStocks = () => api("/api/desk/stocks");
export const searchStocks = (kw) =>
  api("/api/desk/stocks/search?kw=" + encodeURIComponent(kw));
export const addStock = (code) =>
  api("/api/desk/stocks", { method: "POST", body: { code } });
export const removeStock = (code) =>
  api("/api/desk/stocks/" + code, { method: "DELETE" });
export const saveStockOrder = (codes) =>
  api("/api/desk/stocks/order", { method: "PUT", body: { codes } });
export const importWatchlist = () =>
  api("/api/desk/stocks/import", { method: "POST" });

/* ---------- 自定义分组(后端) ---------- */
export const fetchGroups = () => api("/api/desk/groups");
export const addGroup = (name) =>
  api("/api/desk/groups", { method: "POST", body: { name } });
export const renameGroup = (id, name) =>
  api("/api/desk/groups/" + id, { method: "PUT", body: { name } });
export const removeGroup = (id) =>
  api("/api/desk/groups/" + id, { method: "DELETE" });
export const addGroupItem = (id, code) =>
  api("/api/desk/groups/" + id + "/items", { method: "POST", body: { code } });
export const removeGroupItem = (id, code) =>
  api("/api/desk/groups/" + id + "/items/" + code, { method: "DELETE" });
export const saveGroupOrder = (id, codes) =>
  api("/api/desk/groups/" + id + "/order", { method: "PUT", body: { codes } });

/* ---------- 大事件提醒(规则引擎,基于已有数据本地计算) ----------
   输入:实时行情行 + 该股今日异动 + 资金流;输出按严重度排序的提醒列表。 */
export function buildAlerts(row, changes, flow) {
  const alerts = [];
  if (!row) return alerts;
  const push = (level, text) => alerts.push({ level, text });

  if (row.limit_up === 1) push("high", "今日封涨停板");
  if (row.limit_down === 1) push("high", "今日封跌停板");
  if (typeof row.f3 === "number") {
    if (row.f3 >= 7) push("high", `大涨 ${row.f3.toFixed(2)}%,注意追高风险`);
    else if (row.f3 >= 5) push("mid", `涨幅 ${row.f3.toFixed(2)}%,超过 5%`);
    else if (row.f3 <= -7) push("high", `大跌 ${row.f3.toFixed(2)}%,注意风险释放`);
    else if (row.f3 <= -5) push("mid", `跌幅 ${row.f3.toFixed(2)}%,超过 5%`);
  }
  if (typeof row.f62 === "number") {
    const yi = row.f62 / 1e8;
    if (yi >= 1) push("mid", `主力净流入 ${yi.toFixed(2)} 亿,资金大幅进场`);
    else if (yi <= -1) push("mid", `主力净流出 ${Math.abs(yi).toFixed(2)} 亿,资金大幅离场`);
  }
  if (typeof row.f8 === "number" && row.f8 >= 15)
    push("mid", `换手率 ${row.f8.toFixed(1)}%,筹码剧烈交换`);
  if (typeof row.f10 === "number" && row.f10 >= 3)
    push("low", `量比 ${row.f10.toFixed(1)},成交明显放量`);

  for (const c of changes || []) {
    if (["封涨停板", "打开涨停", "封跌停板", "打开跌停", "大笔买入", "大笔卖出",
         "60日新高", "60日新低"].includes(c.type)) {
      push(c.dir === "bear" ? "mid" : "low",
        `${c.time} ${c.type}` + (c.amount ? ` ${(c.amount / 1e4).toFixed(0)} 万` : ""));
    }
  }

  if (flow && flow.length >= 3) {
    let streak = 0;
    for (let i = flow.length - 1; i >= 0; i--) {
      if (flow[i].main > 0) streak += 1; else break;
    }
    if (streak >= 3) push("low", `主力连续 ${streak} 日净流入`);
  }
  const rank = { high: 0, mid: 1, low: 2 };
  return alerts.sort((a, b) => rank[a.level] - rank[b.level]);
}

/* ---------- 操盘笔记 / 个股备忘 ---------- */
export async function fetchNote(code) {
  return api(`/api/desk/note/${code}`);
}

export async function saveNote(code, content) {
  return api(`/api/desk/note/${code}`, {
    method: "PUT",
    body: { content },
  });
}

