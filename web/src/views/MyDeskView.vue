<script setup>
/* ===== 我的工作台 =====
   左栏 = 工作台股票列表(独立于自选):顶部搜索添加 + 从自选导入,
   重点关注 + 自定义分组 + 按加入日期分组,右键菜单,组内拖拽排序。
   右栏 = 固定高度工作区,顶部页签:实时监控 / 盘口资金 / 基本分析,
   选中的股票驱动个股视图内容(参考 TradingView watchlist 交互)。
   数据:股票池/星标/分组/F10 走后端;实时行情/盘口异动/资金流走东财 JSONP 直连。 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { track } from "../api/client";
import { cls, fmtN, fmtYiT } from "../utils/format";
import { marketState } from "../flow/capital-flow";
import AnalysisModal from "../analysis/AnalysisModal.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import {
  fetchLiveQuotes, fetchChanges, fetchMoneyFlow20,
  fetchStars, addStar, removeStar, fetchF10, buildAlerts,
  fetchGroups, addGroup, renameGroup, removeGroup,
  addGroupItem, removeGroupItem, saveGroupOrder,
  fetchStocks, searchStocks, addStock, removeStock,
  saveStockOrder, importWatchlist,
} from "../desk/desk-data";

/* ---------- 格式化 ---------- */
const fmtMoney = (v) =>
  typeof v !== "number" ? "—"
  : Math.abs(v) >= 1e8 ? (v / 1e8).toFixed(2) + "亿"
  : (v / 1e4).toFixed(0) + "万";
const fmtMoneySign = (v) =>
  typeof v !== "number" ? "—" : (v > 0 ? "+" : "") + fmtMoney(v);
const fmtPct = (v) =>
  typeof v === "number" ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "—";
const moneyCls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");

/* ---------- 工作台股票池 + 实时行情 ---------- */
const rows = ref([]);
const live = ref({});
const stars = ref(new Set());
const groups = ref([]); // 自定义分组 [{id, name, codes:[...]}]
const loading = ref(false);
const liveAt = ref("");

function merged(r) {
  const l = live.value[r.f12] || {};
  return { ...r, ...l, limit_up: r.limit_up, limit_down: r.limit_down };
}

const rowsByCode = computed(() => new Map(rows.value.map((r) => [r.f12, r])));

async function loadStocks() {
  loading.value = true;
  try {
    // 分组接口失败(如后端未升级)不拖垮主列表,降级为空分组
    const [wl, st, gs] = await Promise.all([
      fetchStocks(), fetchStars(),
      fetchGroups().catch(() => ({ groups: [] })),
    ]);
    rows.value = wl.rows || [];
    stars.value = new Set(st.codes || []);
    groups.value = gs.groups || [];
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

/* ---------- 从自选导入 ---------- */
const importing = ref(false);

async function doImport() {
  if (importing.value) return;
  importing.value = true;
  try {
    const d = await importWatchlist();
    if (d.added > 0) {
      message.success(`已从自选导入 ${d.added} 只股票`);
      await loadStocks();
      refreshLive();
    } else {
      message.info("自选里没有新股票可导入");
    }
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "导入失败");
  } finally {
    importing.value = false;
  }
}

async function refreshLive() {
  const codes = rows.value.map((r) => r.f12);
  if (!codes.length) return;
  try {
    live.value = await fetchLiveQuotes(codes);
    const d = new Date();
    liveAt.value = [d.getHours(), d.getMinutes(), d.getSeconds()]
      .map((n) => String(n).padStart(2, "0")).join(":");
  } catch { /* JSONP 失败保留旧值,快照数据兜底展示 */ }
}

/* ---------- 分组展开/收起 ---------- */
const collapsed = reactive(new Set());
const toggleGroup = (k) => collapsed.has(k) ? collapsed.delete(k) : collapsed.add(k);

const starRows = computed(() => rows.value.filter((r) => stars.value.has(r.f12)));

// 已归入自定义分组的股票:「我的自选」只展示未分组的,同一只股票不与分组重复出现
const groupedCodes = computed(() => {
  const s = new Set();
  for (const g of groups.value) for (const c of g.codes) s.add(c);
  return s;
});
const poolRows = computed(() =>
  rows.value.filter((r) => !groupedCodes.value.has(r.f12)));

/* ---------- 视图状态:顶部页签 + 选中股票 ---------- */
// monitor=实时监控(不依赖个股) fund=盘口资金 basic=基本分析
const tab = ref("monitor");
const selected = ref("");

const sel = computed(() => {
  const r = rows.value.find((x) => x.f12 === selected.value);
  return r ? merged(r) : null;
});
const stockTab = computed(() => tab.value !== "monitor");

// 点股票:切到个股页签(已在个股视图则保持当前页签)
function pick(code, t) {
  selected.value = code;
  if (t) tab.value = t;
  else if (!stockTab.value) tab.value = "fund";
}
// 点个股页签:无选中股票时先落到第一只(重点关注优先)
function pickTab(t) {
  if (t !== "monitor" && !selected.value) {
    const first = starRows.value[0] || rows.value[0];
    if (first) selected.value = first.f12;
  }
  tab.value = t;
}

/* ---------- 重点关注 ---------- */
async function toggleStar(r, e) {
  e?.stopPropagation();
  const code = r.f12, on = stars.value.has(code);
  try {
    on ? await removeStar(code) : await addStar(code);
    const next = new Set(stars.value);
    on ? next.delete(code) : next.add(code);
    stars.value = next;
    message.success(on ? `已取消重点关注 ${r.f14}` : `已重点关注 ${r.f14}`);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

/* ---------- 搜索添加(防抖 + 键盘导航,与自选页同交互) ---------- */
const kw = ref("");
const results = ref([]);
const searching = ref(false);
const dropOpen = ref(false);
const searchBox = ref(null);
const active = ref(0); // 键盘高亮项(↑↓ 移动,Enter 选中,Esc 关闭)
let searchTimer = null;

function onInput() {
  clearTimeout(searchTimer);
  const q = kw.value.trim();
  if (!q) {
    results.value = [];
    dropOpen.value = false;
    return;
  }
  searchTimer = setTimeout(async () => {
    searching.value = true;
    try {
      const d = await searchStocks(q);
      results.value = d.rows;
      active.value = 0;
      dropOpen.value = true;
    } catch (err) {
      if (err.message !== "unauthorized") message.error(err.message || "搜索失败");
    } finally {
      searching.value = false;
    }
  }, 250);
}

function onKey(e) {
  if (e.key === "Escape") {
    addMenu.value = null;
    dropOpen.value = false;
    return;
  }
  if (!dropOpen.value || !results.value.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    active.value = (active.value + 1) % results.value.length;
    scrollActive();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    active.value = (active.value - 1 + results.value.length) % results.value.length;
    scrollActive();
  } else if (e.key === "Enter") {
    const r = results.value[active.value];
    if (r && !r.added) add(r, null);
  }
}

function scrollActive() {
  const el = searchBox.value && searchBox.value.querySelector(".rsItem.act");
  if (el) el.scrollIntoView({ block: "nearest" });
}

// 命中片段拆分(代码/名称里高亮关键字)
function hl(text) {
  const q = kw.value.trim().toLowerCase();
  if (!text || !q) return [{ t: text || "", hit: false }];
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return [{ t: text, hit: false }];
  return [
    { t: text.slice(0, i), hit: false },
    { t: text.slice(i, i + q.length), hit: true },
    { t: text.slice(i + q.length), hit: false },
  ].filter((s) => s.t);
}

async function add(r, gid) {
  try {
    await addStock(r.f12);
    // 指定分组时同一步归入该组;不指定则只进「我的自选」(未分组池)
    const g = gid ? groups.value.find((x) => x.id === gid) : null;
    if (g) await addGroupItem(g.id, r.f12);
    message.success(g ? `已添加 ${r.f14} 到「${g.name}」` : "已添加 " + r.f14 + " " + r.f12);
    addMenu.value = null;
    kw.value = "";
    results.value = [];
    dropOpen.value = false;
    await loadStocks();
    refreshLive();
    pick(r.f12);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  }
}

const showDrop = computed(() => dropOpen.value && (results.value.length || searching.value));

/* ---------- 单条结果的添加位置(点右侧 caret 选:我的自选 / 某分组) ---------- */
const addMenu = ref(null); // { r, x, y } 固定定位小菜单,避免被下拉裁剪

function toggleAddMenu(r, e) {
  if (addMenu.value?.r.f12 === r.f12) { addMenu.value = null; return; }
  const rect = e.currentTarget.getBoundingClientRect();
  addMenu.value = {
    r,
    x: Math.max(8, Math.min(rect.right - 132, window.innerWidth - 140)),
    y: rect.bottom + 4,
  };
}
// 已在池中的股票,只要还有没加入的分组,仍可通过 caret 直接入组
const canPickTarget = (r) =>
  groups.value.length > 0 &&
  (!r.added || groups.value.some((g) => !g.codes.includes(r.f12)));

/* ---------- 右键菜单(股票叶 / 自定义分组头) ---------- */
const ctxMenu = ref(null); // { x, y, type:'stock'|'group', r, gid? }

function openCtx(r, e, gid) {
  e.preventDefault();
  e.stopPropagation();
  const W = 160, H = 260; // 菜单约略尺寸,防贴边溢出
  ctxMenu.value = {
    x: Math.min(e.clientX, window.innerWidth - W - 8),
    y: Math.min(e.clientY, window.innerHeight - H - 8),
    type: "stock", r, gid,
  };
}

function openGroupCtx(g, e) {
  e.preventDefault();
  e.stopPropagation();
  const W = 160, H = 110;
  ctxMenu.value = {
    x: Math.min(e.clientX, window.innerWidth - W - 8),
    y: Math.min(e.clientY, window.innerHeight - H - 8),
    type: "group", r: g,
  };
}

const closeCtx = () => { ctxMenu.value = null; };
// 先关菜单再执行动作(避免模板读到空 ctxMenu)
function ctxAct(fn) {
  const m = ctxMenu.value;
  closeCtx();
  if (m) fn(m.r, m);
}

/* ---------- 自定义分组:新建 / 重命名 / 删除 / 成员管理 ---------- */
const grpNew = reactive({ open: false, name: "", saving: false });

function openNewGroup() {
  grpNew.name = "";
  grpNew.open = true;
}

async function doNewGroup() {
  const name = grpNew.name.trim();
  if (!name || grpNew.saving) return;
  grpNew.saving = true;
  try {
    const d = await addGroup(name);
    groups.value.push({ id: d.id, name: d.name, codes: [] });
    grpNew.open = false;
    message.success("已创建分组 " + d.name);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "创建失败");
  } finally {
    grpNew.saving = false;
  }
}

const renaming = ref(null); // { id, name }

function startRename(g) {
  renaming.value = { id: g.id, name: g.name };
}

async function doRename() {
  const rn = renaming.value;
  if (!rn) return;
  renaming.value = null;
  const g = groups.value.find((x) => x.id === rn.id);
  const name = rn.name.trim();
  if (!g || !name || name === g.name) return;
  try {
    await renameGroup(g.id, name);
    g.name = name;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "重命名失败");
  }
}

const grpDel = reactive({ open: false, row: null, loading: false });

function askRemoveGroup(g) {
  grpDel.row = g;
  grpDel.open = true;
}

async function doRemoveGroup() {
  const g = grpDel.row;
  if (!g) return;
  grpDel.loading = true;
  try {
    await removeGroup(g.id);
    groups.value = groups.value.filter((x) => x.id !== g.id);
    grpDel.open = false;
    message.success("已删除分组 " + g.name);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "删除失败");
  } finally {
    grpDel.loading = false;
  }
}

// 成员管理弹窗:勾选即进组/出组(即时生效)
const grpDlg = reactive({ open: false, row: null });

function openGrpDlg(r) {
  grpDlg.row = r;
  grpDlg.open = true;
}

async function toggleMembership(g) {
  const code = grpDlg.row?.f12;
  if (!code) return;
  const member = g.codes.includes(code);
  try {
    member ? await removeGroupItem(g.id, code) : await addGroupItem(g.id, code);
    if (member) g.codes = g.codes.filter((c) => c !== code);
    else g.codes.unshift(code);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

async function removeFromGroup(gid, r) {
  const g = groups.value.find((x) => x.id === gid);
  if (!g) return;
  try {
    await removeGroupItem(gid, r.f12);
    g.codes = g.codes.filter((c) => c !== r.f12);
    message.success(`已从「${g.name}」移除 ${r.f14}`);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  }
}

/* ---------- 从工作台移除(二次确认) ---------- */
const rmState = reactive({ open: false, row: null, loading: false });

function askRemove(r) {
  rmState.row = r;
  rmState.open = true;
}

async function removeWatch() {
  const r = rmState.row;
  if (!r) return;
  rmState.loading = true;
  try {
    await removeStock(r.f12);
    rows.value = rows.value.filter((x) => x.f12 !== r.f12);
    for (const g of groups.value) {
      if (g.codes.includes(r.f12)) g.codes = g.codes.filter((c) => c !== r.f12);
    }
    if (stars.value.has(r.f12)) {
      const next = new Set(stars.value);
      next.delete(r.f12);
      stars.value = next;
    }
    if (selected.value === r.f12) {
      const first = starRows.value[0] || rows.value[0];
      selected.value = first ? first.f12 : "";
    }
    rmState.open = false;
    message.success("已移除 " + r.f14);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  } finally {
    rmState.loading = false;
  }
}

/* ---------- 组内拖拽排序 + 拖入自定义分组 ---------- */
// 组键:'star'=重点关注  'all'=我的自选  'g<id>'=自定义分组
const drag = reactive({ code: "", group: "" });
const dropOn = ref(""); // 悬停目标 code,渲染插入指示线
const dropGroup = ref(null); // 悬停的自定义分组 id(拖入高亮)

function onDragStart(r, g, e) {
  drag.code = r.f12;
  drag.group = g;
  e.dataTransfer.effectAllowed = "move";
}

function onDragOver(r, g, e) {
  // 只允许同组内排序(跨组排序会改变分组语义;跨组请拖到分组头上)
  if (drag.code && drag.group === g && drag.code !== r.f12) {
    e.preventDefault();
    dropOn.value = r.f12;
  }
}

function onDrop(r, g) {
  if (!drag.code || drag.group !== g || drag.code === r.f12) return;
  if (g.startsWith("g")) {
    // 自定义分组:重排 codes 数组(渲染顺序以 codes 为准)
    const grp = groups.value.find((x) => "g" + x.id === g);
    if (!grp) return;
    const from = grp.codes.indexOf(drag.code);
    if (from < 0) return;
    const [m] = grp.codes.splice(from, 1);
    const to = grp.codes.indexOf(r.f12);
    if (to < 0) { grp.codes.splice(from, 0, m); return; }
    grp.codes.splice(to, 0, m);
    saveGroupOrder(grp.id, grp.codes).catch((err) => {
      if (err.message !== "unauthorized") message.error("排序保存失败");
    });
    return;
  }
  // 重点关注/日期组:重排 rows(分组顺序由 rows 派生)
  const arr = rows.value;
  const from = arr.findIndex((x) => x.f12 === drag.code);
  if (from < 0) return;
  const [moved] = arr.splice(from, 1);
  const to = arr.findIndex((x) => x.f12 === r.f12); // 移除后重定位,插到目标之前
  if (to < 0) { arr.splice(from, 0, moved); return; }
  arr.splice(to, 0, moved);
  persistGroupOrder(g);
}

function onDragEnd() {
  drag.code = "";
  drag.group = "";
  dropOn.value = null;
  dropGroup.value = null;
}

// 拖到自定义分组头上 = 加入该分组
function onGroupHeadDragOver(g, e) {
  if (drag.code && drag.group !== "g" + g.id && !g.codes.includes(drag.code)) {
    e.preventDefault();
    dropGroup.value = g.id;
  }
}

async function onGroupHeadDrop(g) {
  if (dropGroup.value !== g.id) return;
  const code = drag.code;
  onDragEnd();
  const r = rowsByCode.value.get(code);
  try {
    await addGroupItem(g.id, code);
    g.codes.unshift(code);
    message.success(`已把 ${r?.f14 || code} 加入「${g.name}」`);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加入分组失败");
  }
}

async function persistGroupOrder(g) {
  // star=重点关注组  all=我的自选(全量);自定义分组走 saveGroupOrder(见 onDrop)
  const list = g === "star" ? starRows.value : rows.value;
  try {
    await saveStockOrder(list.map((x) => x.f12));
  } catch (err) {
    if (err.message !== "unauthorized") message.error("排序保存失败");
  }
}

/* ---------- 实时监控:主力流向 + 大资金动向 ---------- */
const changes = ref([]);
const changesAt = ref("");

const flowBoard = computed(() =>
  rows.value.map(merged)
    .filter((r) => typeof r.f62 === "number")
    .sort((a, b) => b.f62 - a.f62));

const flowMax = computed(() =>
  flowBoard.value.reduce((m, r) => Math.max(m, Math.abs(r.f62)), 1));

const changeDir = ref("all");
const watchChanges = computed(() => {
  const set = new Set(rows.value.map((r) => r.f12));
  return changes.value
    .filter((c) => set.has(c.code))
    .filter((c) => changeDir.value === "all" || c.dir === changeDir.value)
    .slice(0, 60);
});

const flowSummary = computed(() => {
  const list = flowBoard.value;
  return {
    inN: list.filter((r) => r.f62 > 0).length,
    outN: list.filter((r) => r.f62 < 0).length,
    sum: list.reduce((s, r) => s + r.f62, 0),
  };
});

async function refreshChanges() {
  try {
    changes.value = await fetchChanges();
    const d = new Date();
    changesAt.value = [d.getHours(), d.getMinutes()]
      .map((n) => String(n).padStart(2, "0")).join(":");
  } catch { /* 保留旧数据 */ }
}

/* ---------- 盘口资金(20 日资金流) ---------- */
const flowCache = reactive({});
const flow20 = computed(() => flowCache[selected.value]?.rows || null);

async function loadFlow(code) {
  if (flowCache[code]?.rows || flowCache[code]?.loading) return;
  flowCache[code] = { loading: true, rows: null, error: false };
  try {
    flowCache[code] = { loading: false, rows: await fetchMoneyFlow20(code), error: false };
  } catch {
    // 失败不缓存(东财偶有风控限流),点重试或切换股票再切回即可
    flowCache[code] = { loading: false, rows: null, error: true };
  }
}

const flowStat = computed(() => {
  const fs = flow20.value;
  if (!fs || !fs.length) return null;
  const sum = (arr) => arr.reduce((s, r) => s + r.main, 0);
  let streak = 0;
  for (let i = fs.length - 1; i >= 0; i--) {
    if (fs[i].main > 0) streak += 1; else break;
  }
  let outStreak = 0;
  for (let i = fs.length - 1; i >= 0; i--) {
    if (fs[i].main < 0) outStreak += 1; else break;
  }
  return { d5: sum(fs.slice(-5)), d20: sum(fs), streak, outStreak };
});

const flowDetail = computed(() => (flow20.value || []).slice(-10).reverse());

// 资金流 SVG 图:主力 = 超大单(深色) + 大单(浅色) 堆叠,零轴上下发散
const flowChart = computed(() => {
  const fs = flow20.value;
  if (!fs || !fs.length) return null;
  const W = 660, H = 190, padT = 10, padB = 22, mid = padT + (H - padT - padB) / 2;
  const max = fs.reduce((m, r) => Math.max(m, Math.abs(r.super + r.big)), 1);
  const sy = (H - padT - padB) / 2 / max;
  const step = (W - 24) / fs.length;
  const bw = Math.min(20, step * 0.58);
  const bars = fs.map((r, i) => {
    const x = 12 + i * step + (step - bw) / 2;
    const rects = [];
    let accPos = 0, accNeg = 0;
    for (const [v, op] of [[r.super, 1], [r.big, 0.45]]) {
      if (!v) continue;
      const h = Math.abs(v) * sy;
      if (v > 0) { rects.push({ x, y: mid - accPos - h, w: bw, h, cls: "in", op }); accPos += h; }
      else { rects.push({ x, y: mid + accNeg, w: bw, h, cls: "out", op }); accNeg += h; }
    }
    return { date: r.date.slice(5), rects, main: r.main };
  });
  return { W, H, mid, bars, max };
});

/* ---------- 基本分析(F10) ---------- */
const f10Cache = reactive({});
const f10 = computed(() => f10Cache[selected.value]?.data || null);

async function loadF10(code) {
  if (f10Cache[code]?.data || f10Cache[code]?.loading) return;
  f10Cache[code] = { loading: true, data: null, error: false };
  try {
    f10Cache[code] = { loading: false, data: await fetchF10(code), error: false };
    // 埋点:查看 F10 资料(缓存命中不重复上报)
    const r = rows.value.find((x) => x.f12 === code);
    track("f10_view", code + (r && r.f14 ? " " + r.f14 : ""));
  } catch {
    f10Cache[code] = { loading: false, data: null, error: true };
  }
}

const holderChart = computed(() => {
  const hs = (f10.value?.holders || []).filter((h) => h.num).slice(0, 6).reverse();
  if (!hs.length) return null;
  const W = 660, H = 130, padT = 16, padB = 34;
  const max = Math.max(...hs.map((h) => h.num));
  const min = Math.min(...hs.map((h) => h.num));
  const span = Math.max(max - min, 1);
  const step = (W - 40) / hs.length;
  const bw = Math.min(46, step * 0.5);
  return {
    W, H,
    bars: hs.map((h, i) => ({
      x: 20 + i * step + (step - bw) / 2,
      y: padT + (1 - (h.num - min) / span) * (H - padT - padB) * 0.72,
      h: Math.max(6, ((h.num - min) / span) * (H - padT - padB) * 0.72 + 6),
      w: bw,
      label: (h.num / 1e4).toFixed(1) + "万",
      date: (h.date || "").slice(2, 7).replace("-", "/"),
      last: i === hs.length - 1,
    })),
  };
});

const latestHolder = computed(() => (f10.value?.holders || [])[0] || null);

/* ---------- 公司架构(管理层构成) ---------- */
const execStats = computed(() => {
  const es = f10.value?.execs || [];
  if (!es.length) return null;
  const male = es.filter((e) => e.sex === "男").length;
  const female = es.filter((e) => e.sex === "女").length;
  const ages = es.map((e) => e.age).filter((a) => typeof a === "number");
  return {
    total: es.length, male, female,
    malePct: Math.round((male / es.length) * 100),
    femalePct: Math.round((female / es.length) * 100),
    avgAge: ages.length
      ? Math.round(ages.reduce((s, a) => s + a, 0) / ages.length) : null,
  };
});

// 点高管行展开/收起履历
const expandedExec = ref("");
const execKey = (e) => e.name + "|" + e.position;
const toggleExec = (e) => {
  const k = execKey(e);
  expandedExec.value = expandedExec.value === k ? "" : k;
};

/* ---------- 大事件提醒 ---------- */
const selChanges = computed(() =>
  changes.value.filter((c) => c.code === selected.value));
const alerts = computed(() =>
  buildAlerts(sel.value, selChanges.value, flow20.value));

/* ---------- 战法弹窗 ---------- */
const anaRef = ref(null);
function openAnalysis(code) {
  const c = code || selected.value;
  if (c) anaRef.value?.open(c);
}

watch(selected, (code) => {
  if (!code) return;
  loadFlow(code);
  loadF10(code);
});

/* ---------- 生命周期 ---------- */
let timer = null;

// 点击组件外:关闭搜索下拉 + 添加位置菜单 + 右键菜单
function onDocClick(e) {
  if (searchBox.value && !searchBox.value.contains(e.target)) {
    dropOpen.value = false;
  }
  addMenu.value = null;
  closeCtx();
}
// 在树节点以外的地方右键:关掉已开的菜单(节点上由 openCtx/openGroupCtx 重新定位)
function onDocCtx(e) {
  if (!e.target.closest || !e.target.closest(".tNode")) closeCtx();
}

onMounted(async () => {
  await loadStocks();
  refreshLive();
  refreshChanges();
  // 埋点:打开工作台页面(带当前股票池规模)
  track("desk_view", rows.value.length + " 只");
  // 预选第一只(重点关注优先),供个股页签直接使用
  const first = starRows.value[0] || rows.value[0];
  if (first) selected.value = first.f12;
  timer = setInterval(() => {
    if (marketState().cls === "live") { refreshLive(); refreshChanges(); }
  }, 30_000);
  document.addEventListener("click", onDocClick);
  document.addEventListener("contextmenu", onDocCtx);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  clearTimeout(searchTimer);
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("contextmenu", onDocCtx);
});
</script>

<template>
  <div class="desk">
    <!-- ===== 左栏:工作台股票列表(通高,搜索 + 分组树) ===== -->
    <aside class="rail">
      <div class="railHead">
        <span class="railTitle">我的工作台<span class="railCnt">{{ rows.length }}</span></span>
        <span class="railOps">
          <button class="railOpBtn" title="从自选导入" :disabled="importing" @click="doImport">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
          </button>
          <button class="railOpBtn" title="新建分组" @click="openNewGroup">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round">
              <path d="M12 5v14M5 12h14"/></svg>
          </button>
        </span>
      </div>

      <!-- 搜索添加 -->
      <div class="railSearch" ref="searchBox">
        <div class="rsInner" :class="{ open: showDrop }">
          <svg class="rsIcon" width="14" height="14" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
          </svg>
          <input v-model="kw" class="rsInput" placeholder="代码 / 名称 / 拼音,加入工作台"
                 @input="onInput" @keydown="onKey"
                 @focus="results.length && (dropOpen = true)" />
          <span v-if="searching" class="rsSpin"></span>
        </div>
        <div v-show="showDrop" class="rsDrop">
          <div v-if="!results.length && searching" class="rsEmpty">搜索中…</div>
          <div v-else-if="!results.length" class="rsEmpty">没有找到相关股票</div>
          <button v-for="(r, i) in results" :key="r.f12" class="rsItem"
                  :class="{ act: i === active, added: r.added }"
                  @mouseenter="active = i" @click="!r.added && add(r, null)">
            <span class="rsName"><template v-for="(s, j) in hl(r.f14)" :key="j"><mark v-if="s.hit">{{ s.t }}</mark><template v-else>{{ s.t }}</template></template></span>
            <span class="rsCode"><template v-for="(s, j) in hl(r.f12)" :key="j"><mark v-if="s.hit">{{ s.t }}</mark><template v-else>{{ s.t }}</template></template></span>
            <span class="rsActs">
              <span class="rsAct" :class="{ on: r.added }">{{ r.added ? "已加" : "+ 加入" }}</span>
              <span v-if="canPickTarget(r)" class="rsAddCaret" title="选择添加位置"
                    @click.stop="toggleAddMenu(r, $event)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2.4" stroke-linecap="round">
                  <path d="M6 9l6 6 6-6"/></svg>
              </span>
            </span>
          </button>
        </div>
        <!-- 添加位置小菜单(固定定位,不被下拉裁剪):默认进我的自选,或直接入某分组 -->
        <div v-if="addMenu" class="rsAddMenu"
             :style="{ left: addMenu.x + 'px', top: addMenu.y + 'px' }" @click.stop>
          <button v-if="!addMenu.r.added" @click="add(addMenu.r, null)">我的自选</button>
          <button v-for="g in groups" :key="'am' + g.id"
                  :disabled="g.codes.includes(addMenu.r.f12)"
                  @click="add(addMenu.r, g.id)">
            {{ g.name }}
            <i v-if="g.codes.includes(addMenu.r.f12)">已在组内</i>
          </button>
        </div>
      </div>

      <div class="tree" v-if="rows.length">
        <!-- 重点关注 -->
        <div class="tGroup" v-if="starRows.length">
          <button class="tNode g" @click="toggleGroup('g-star')">
            <svg class="tArrow" :class="{ shut: collapsed.has('g-star') }" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <path d="M6 9l6 6 6-6"/></svg>
            <svg class="tStarIco" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z"/></svg>
            重点关注
            <span class="tCount">{{ starRows.length }}</span>
          </button>
          <div v-show="!collapsed.has('g-star')" class="tKids">
            <button v-for="r in starRows" :key="'s' + r.f12" class="tNode leaf"
                    :class="{ on: selected === r.f12 && stockTab, dropHere: dropOn === r.f12 }"
                    draggable="true"
                    @click="pick(r.f12)" @contextmenu="openCtx(r, $event)"
                    @dragstart="onDragStart(r, 'star', $event)"
                    @dragover="onDragOver(r, 'star', $event)"
                    @drop="onDrop(r, 'star')" @dragend="onDragEnd">
              <span class="dStar on" title="取消重点关注" @click="toggleStar(r, $event)">★</span>
              <span class="dName">{{ r.f14 }}<i>{{ r.f12 }}</i></span>
              <span class="dPct" :class="cls(merged(r).f3)">{{ fmtPct(merged(r).f3) }}</span>
            </button>
          </div>
        </div>

        <!-- 自定义分组 -->
        <div class="tGroup" v-for="g in groups" :key="'g' + g.id">
          <button class="tNode g" :class="{ dropGrp: dropGroup === g.id }"
                  @click="toggleGroup('g' + g.id)" @contextmenu="openGroupCtx(g, $event)"
                  @dragover="onGroupHeadDragOver(g, $event)" @drop="onGroupHeadDrop(g)">
            <svg class="tArrow" :class="{ shut: collapsed.has('g' + g.id) }" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <path d="M6 9l6 6 6-6"/></svg>
            <svg class="tFolderIco" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linejoin="round">
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
            <input v-if="renaming?.id === g.id" class="tRename" v-model="renaming.name"
                   maxlength="20" @click.stop @keydown.enter.stop="doRename"
                   @keydown.esc.stop="renaming = null" @blur="doRename"
                   :ref="(el) => el && el.focus()" />
            <template v-else>{{ g.name }}</template>
            <span class="tCount">{{ g.codes.length }}</span>
          </button>
          <div v-show="!collapsed.has('g' + g.id)" class="tKids">
            <template v-for="code in g.codes" :key="'g' + g.id + code">
              <button v-if="rowsByCode.get(code)" class="tNode leaf"
                      :class="{ on: selected === code && stockTab, dropHere: dropOn === code }"
                      draggable="true"
                      @click="pick(code)" @contextmenu="openCtx(rowsByCode.get(code), $event, g.id)"
                      @dragstart="onDragStart(rowsByCode.get(code), 'g' + g.id, $event)"
                      @dragover="onDragOver(rowsByCode.get(code), 'g' + g.id, $event)"
                      @drop="onDrop(rowsByCode.get(code), 'g' + g.id)" @dragend="onDragEnd">
                <span class="dStar" :class="{ on: stars.has(code) }"
                      :title="stars.has(code) ? '取消重点关注' : '标记重点关注'"
                      @click="toggleStar(rowsByCode.get(code), $event)">★</span>
                <span class="dName">{{ rowsByCode.get(code).f14 }}<i>{{ code }}</i>
                  <em v-if="rowsByCode.get(code).limit_up === 1" class="lmBadge up">涨停</em>
                  <em v-else-if="rowsByCode.get(code).limit_down === 1" class="lmBadge down">跌停</em>
                </span>
                <span class="dPct" :class="cls(merged(rowsByCode.get(code)).f3)">{{ fmtPct(merged(rowsByCode.get(code)).f3) }}</span>
              </button>
            </template>
            <div v-if="!g.codes.length" class="tGrpHint">把股票拖到组名上加入,<br/>或右键股票「设置分组」</div>
          </div>
        </div>

        <!-- 我的自选(未分组股票;已入组的不再重复显示) -->
        <div class="tGroup">
          <button class="tNode g" @click="toggleGroup('g-all')">
            <svg class="tArrow" :class="{ shut: collapsed.has('g-all') }" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <path d="M6 9l6 6 6-6"/></svg>
            <svg class="tListIco" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round">
              <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>
            我的自选
            <span class="tCount">{{ poolRows.length }}</span>
          </button>
          <div v-show="!collapsed.has('g-all')" class="tKids">
            <button v-for="r in poolRows" :key="r.f12" class="tNode leaf"
                    :class="{ on: selected === r.f12 && stockTab, dropHere: dropOn === r.f12 }"
                    draggable="true"
                    @click="pick(r.f12)" @contextmenu="openCtx(r, $event)"
                    @dragstart="onDragStart(r, 'all', $event)"
                    @dragover="onDragOver(r, 'all', $event)"
                    @drop="onDrop(r, 'all')" @dragend="onDragEnd"
                    :title="(r.created_at || '').slice(0, 10) + ' 加入'">
              <span class="dStar" :class="{ on: stars.has(r.f12) }"
                    :title="stars.has(r.f12) ? '取消重点关注' : '标记重点关注'"
                    @click="toggleStar(r, $event)">★</span>
              <span class="dName">{{ r.f14 }}<i>{{ r.f12 }}</i>
                <em v-if="r.limit_up === 1" class="lmBadge up">涨停</em>
                <em v-else-if="r.limit_down === 1" class="lmBadge down">跌停</em>
              </span>
              <span class="dPct" :class="cls(merged(r).f3)">{{ fmtPct(merged(r).f3) }}</span>
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="railEmpty">
        还没有股票<br/>用上方搜索框添加,或点右上角从自选导入
      </div>
    </aside>

    <!-- ===== 右侧:固定高度工作区(页签 + 内部滚动) ===== -->
    <div class="main">
      <nav class="topTabs" v-if="rows.length">
        <button :class="{ on: tab === 'monitor' }" @click="pickTab('monitor')">实时监控</button>
        <button :class="{ on: tab === 'fund' }" @click="pickTab('fund')">盘口资金</button>
        <button :class="{ on: tab === 'basic' }" @click="pickTab('basic')">基本分析</button>
        <button :class="{ on: tab === 'exec' }" @click="pickTab('exec')">公司架构</button>
        <span class="topMeta">
          <template v-if="stockTab && sel">{{ sel.f14 }} {{ sel.f12 }} · </template>
          <i class="liveDot" :class="{ idle: !liveAt }"></i>{{ liveAt || "待刷新" }}
        </span>
      </nav>

      <div class="stage" v-if="rows.length">
        <!-- ===== 实时监控(双卡总览) ===== -->
        <div v-if="tab === 'monitor'" class="monGrid">
          <div class="dPanel">
            <div class="dHead">
              <span class="dTitle">主力流向</span>
              <span class="dEn">Main Capital</span>
              <span class="dMeta">
                <i class="liveDot" :class="{ idle: !liveAt }"></i>{{ liveAt || "待刷新" }}
              </span>
            </div>
            <div v-if="flowBoard.length" class="flowSum">
              <span>合计 <b :class="moneyCls(flowSummary.sum)">{{ fmtMoneySign(flowSummary.sum) }}</b></span>
              <span class="up">{{ flowSummary.inN }} 只净流入</span>
              <span class="down">{{ flowSummary.outN }} 只净流出</span>
            </div>
            <div v-if="flowBoard.length" class="flowList">
              <button v-for="r in flowBoard" :key="'f' + r.f12" class="fRow"
                      :class="{ on: selected === r.f12 && stockTab }" @click="pick(r.f12)">
                <span class="fName">{{ r.f14 }}</span>
                <span class="fBar">
                  <i class="fZero"></i>
                  <i class="fFill" :class="r.f62 >= 0 ? 'in' : 'out'"
                     :style="r.f62 >= 0
                       ? { left: '50%', width: (Math.abs(r.f62) / flowMax * 50) + '%' }
                       : { right: '50%', width: (Math.abs(r.f62) / flowMax * 50) + '%' }"></i>
                </span>
                <span class="fVal" :class="moneyCls(r.f62)">{{ fmtMoneySign(r.f62) }}</span>
              </button>
            </div>
            <div v-else class="dEmpty">暂无主力资金数据</div>
          </div>

          <div class="dPanel">
            <div class="dHead">
              <span class="dTitle">大资金动向</span>
              <span class="dEn">Big Money</span>
              <span class="dirFilter">
                <button v-for="o in [['all', '全部'], ['bull', '偏多'], ['bear', '偏空']]" :key="o[0]"
                        :class="{ on: changeDir === o[0] }" @click="changeDir = o[0]">{{ o[1] }}</button>
              </span>
              <span class="dMeta">
                <i class="liveDot" :class="{ idle: !changesAt }"></i>{{ changesAt || "待刷新" }}
              </span>
            </div>
            <div v-if="watchChanges.length" class="feedList">
              <button v-for="(c, i) in watchChanges" :key="c.code + c.time + i" class="cRow"
                      @click="pick(c.code)">
                <span class="cTime">{{ c.time }}</span>
                <span class="cName">{{ c.name }}</span>
                <span class="cType" :class="c.dir">{{ c.type }}</span>
                <span class="cVal">
                  {{ typeof c.price === "number" ? c.price.toFixed(2) : "" }}
                  <b v-if="c.amount"> · {{ (c.amount / 1e4).toFixed(0) }}万</b>
                </span>
              </button>
            </div>
            <div v-else class="dEmpty">今日暂无盘口异动</div>
          </div>
        </div>

        <!-- ===== 个股视图:盘口资金 / 基本分析 ===== -->
        <template v-else-if="sel">
          <header class="hero">
            <div class="heroL">
              <div class="heroName">
                {{ sel.f14 }}
                <span class="heroCode">{{ sel.f12 }}</span>
                <em v-if="sel.limit_up === 1" class="lmBadge up">涨停</em>
                <em v-else-if="sel.limit_down === 1" class="lmBadge down">跌停</em>
              </div>
              <div class="heroInd">{{ sel.f100 || "—" }} · {{ (sel.created_at || "").slice(0, 10) }} 加入工作台</div>
            </div>
            <div class="heroPrice">
              <b :class="cls(sel.f3)">{{ fmtN(sel.f2) }}</b>
              <span :class="cls(sel.f3)">{{ fmtPct(sel.f3) }}</span>
            </div>
            <div class="heroKv">
              <div class="kv"><span>换手率</span><b>{{ fmtN(sel.f8, 1) }}%</b></div>
              <div class="kv"><span>成交额</span><b>{{ fmtYiT(sel.f6) }}</b></div>
              <div class="kv"><span>量比</span><b>{{ fmtN(sel.f10) }}</b></div>
              <div class="kv">
                <span>主力净流入</span>
                <b :class="moneyCls(sel.f62)">{{ fmtMoneySign(sel.f62) }}</b>
              </div>
              <div class="kv">
                <span>主力净占比</span>
                <b :class="moneyCls(sel.f184)">{{ typeof sel.f184 === "number" ? sel.f184.toFixed(1) + "%" : "—" }}</b>
              </div>
            </div>
          </header>

          <section class="dPanel detail">
            <!-- ===== 盘口资金 ===== -->
            <div v-if="tab === 'fund'" class="pane">
              <div class="dSub">主力流向<span class="dSubNote">今日实时 + 阶段累计</span></div>
              <div class="statStrip">
                <div class="stat">
                  <span class="sCap">今日主力净额</span>
                  <b :class="moneyCls(sel.f62)">{{ fmtMoneySign(sel.f62) }}</b>
                </div>
                <div class="stat" v-if="flowStat">
                  <span class="sCap">近 5 日主力</span>
                  <b :class="moneyCls(flowStat.d5)">{{ fmtMoneySign(flowStat.d5) }}</b>
                </div>
                <div class="stat" v-if="flowStat">
                  <span class="sCap">近 20 日主力</span>
                  <b :class="moneyCls(flowStat.d20)">{{ fmtMoneySign(flowStat.d20) }}</b>
                </div>
                <div class="stat" v-if="flowStat">
                  <span class="sCap">连续性</span>
                  <b v-if="flowStat.streak >= 2" class="up">连续 {{ flowStat.streak }} 日流入</b>
                  <b v-else-if="flowStat.outStreak >= 2" class="down">连续 {{ flowStat.outStreak }} 日流出</b>
                  <b v-else class="dimB">无连续趋势</b>
                </div>
              </div>

              <div class="dSub">近 20 日大单流向<span class="dSubNote">主力 = 超大单 + 大单,单位:金额</span></div>
              <div v-if="flowCache[selected]?.loading" class="dLoading"><i class="dSpin"></i>资金流加载中…</div>
              <template v-else-if="flowChart">
                <svg class="mfChart" :viewBox="`0 0 ${flowChart.W} ${flowChart.H}`" preserveAspectRatio="none">
                  <line :x1="8" :x2="flowChart.W - 8" :y1="flowChart.mid" :y2="flowChart.mid" class="mfZero"/>
                  <g v-for="(b, i) in flowChart.bars" :key="i">
                    <rect v-for="(rc, j) in b.rects" :key="j"
                          :x="rc.x" :y="rc.y" :width="rc.w" :height="rc.h"
                          :class="rc.cls" :fill-opacity="rc.op" rx="1">
                      <title>{{ b.date }} 主力净额 {{ fmtMoneySign(b.main) }}</title>
                    </rect>
                  </g>
                  <text v-for="i in [0, Math.floor(flowChart.bars.length / 2), flowChart.bars.length - 1]"
                        :key="'t' + i" class="mfTick" text-anchor="middle"
                        :x="12 + (flowChart.W - 24) / flowChart.bars.length * (i + 0.5)"
                        :y="flowChart.H - 6">{{ flowChart.bars[i].date }}</text>
                </svg>
                <div class="mfLegend">
                  <span><i class="lg in"></i>净流入</span>
                  <span><i class="lg out"></i>净流出</span>
                  <span class="dimB">深色为超大单,浅色为大单;悬停查看单日净额</span>
                </div>
              </template>
              <div v-else-if="flowCache[selected]?.error" class="dEmpty">
                资金流加载失败(可能触发接口限流)
                <button class="retryLink" @click="loadFlow(selected)">重试</button>
              </div>
              <div v-else class="dEmpty">暂无资金流数据</div>

              <div class="dSub">大资金动向<span class="dSubNote">该股今日盘口异动</span></div>
              <div v-if="selChanges.length" class="feedList static">
                <div v-for="(c, i) in selChanges" :key="'sc' + i" class="cRow asRow">
                  <span class="cTime">{{ c.time }}</span>
                  <span class="cType" :class="c.dir">{{ c.type }}</span>
                  <span class="cVal">
                    {{ typeof c.price === "number" ? c.price.toFixed(2) : "" }}
                    <b v-if="c.amount"> · {{ (c.amount / 1e4).toFixed(0) }}万</b>
                  </span>
                </div>
              </div>
              <div v-else class="dEmpty">今日暂无该股盘口异动</div>

              <template v-if="flowDetail.length">
                <div class="dSub">分级明细<span class="dSubNote">近 10 日,单位:金额</span></div>
                <div class="mfTblWrap">
                  <table class="mfTbl">
                    <thead>
                      <tr><th class="l">日期</th><th>主力</th><th>超大单</th><th>大单</th><th>中单</th><th>小单</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in flowDetail" :key="r.date">
                        <td class="l">{{ r.date.slice(5) }}</td>
                        <td :class="moneyCls(r.main)">{{ fmtMoneySign(r.main) }}</td>
                        <td :class="moneyCls(r.super)">{{ fmtMoneySign(r.super) }}</td>
                        <td :class="moneyCls(r.big)">{{ fmtMoneySign(r.big) }}</td>
                        <td :class="moneyCls(r.mid)">{{ fmtMoneySign(r.mid) }}</td>
                        <td :class="moneyCls(r.small)">{{ fmtMoneySign(r.small) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </div>

            <!-- ===== 基本分析 ===== -->
            <div v-else-if="tab === 'basic'" class="pane">
              <div v-if="f10Cache[selected]?.loading" class="dLoading"><i class="dSpin"></i>资料加载中…</div>
              <template v-else-if="f10">
                <div class="dSub">题材概念</div>
                <div v-if="f10.boards?.length" class="chipWrap">
                  <span v-for="(b, i) in f10.boards" :key="b" class="chip" :class="{ hot: i === 0 }">{{ b }}</span>
                </div>
                <div v-if="f10.points?.length" class="ptList">
                  <div v-for="p in f10.points" :key="p.title" class="ptItem">
                    <b>{{ p.title }}</b>
                    <p v-for="(c, i) in p.contents" :key="i">{{ c }}</p>
                  </div>
                </div>
                <div v-if="!f10.boards?.length && !f10.points?.length" class="dEmpty">暂无题材数据</div>

                <div class="dSub">股东分析</div>
                <template v-if="latestHolder">
                  <div class="statStrip">
                    <div class="stat">
                      <span class="sCap">股东户数 · {{ (latestHolder.date || "").slice(0, 7) }}</span>
                      <b>{{ (latestHolder.num / 1e4).toFixed(2) }} 万户</b>
                    </div>
                    <div class="stat" v-if="typeof latestHolder.ratio === 'number'">
                      <span class="sCap">较上期</span>
                      <b :class="latestHolder.ratio < 0 ? 'up' : latestHolder.ratio > 0 ? 'down' : ''">
                        {{ (latestHolder.ratio > 0 ? "+" : "") + latestHolder.ratio.toFixed(2) }}%
                      </b>
                    </div>
                    <div class="stat" v-if="latestHolder.focus">
                      <span class="sCap">筹码集中度</span><b>{{ latestHolder.focus }}</b>
                    </div>
                    <div class="stat" v-if="latestHolder.avg_amt">
                      <span class="sCap">户均持股市值</span>
                      <b>{{ (latestHolder.avg_amt / 1e4).toFixed(1) }} 万</b>
                    </div>
                  </div>
                  <svg v-if="holderChart" class="hdChart" :viewBox="`0 0 ${holderChart.W} ${holderChart.H}`"
                       preserveAspectRatio="none">
                    <g v-for="(b, i) in holderChart.bars" :key="i">
                      <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="2"
                            :class="b.last ? 'hdBar last' : 'hdBar'"/>
                      <text class="hdVal" text-anchor="middle" :x="b.x + b.w / 2" :y="b.y - 4">{{ b.label }}</text>
                      <text class="hdDate" text-anchor="middle" :x="b.x + b.w / 2"
                            :y="holderChart.H - 18">{{ b.date }}</text>
                    </g>
                  </svg>
                  <div class="dNote">股东户数持续下降通常意味着筹码集中,反之趋于分散。</div>
                </template>
                <div v-else class="dEmpty">暂无股东数据</div>

                <div class="dSub">地域与公司</div>
                <div class="kvGrid">
                  <div class="kv2"><span>所在地区</span><b>{{ f10.survey?.region || "—" }}</b></div>
                  <div class="kv2"><span>所属行业</span><b>{{ f10.survey?.industry || "—" }}</b></div>
                  <div class="kv2"><span>证监会行业</span><b>{{ f10.survey?.csrc_industry || "—" }}</b></div>
                  <div class="kv2"><span>董事长</span><b>{{ f10.survey?.chairman || "—" }}</b></div>
                  <div class="kv2"><span>注册资本</span><b>{{ f10.survey?.reg_capital || "—" }}</b></div>
                  <div class="kv2"><span>员工人数</span><b>{{ f10.survey?.employees || "—" }}</b></div>
                  <div class="kv2 wide"><span>注册地址</span><b>{{ f10.survey?.address || "—" }}</b></div>
                  <div class="kv2 wide"><span>公司全称</span><b>{{ f10.survey?.full_name || "—" }}</b></div>
                </div>
                <p v-if="f10.survey?.intro" class="intro">{{ f10.survey.intro }}</p>

                <div class="dSub">战法分析</div>
                <div class="zfaRow">
                  <span class="dNote">综合 / 趋势波段 / 趋势启动 / 超跌反弹 / 3030 战法 / 资金流向 / 基本面,七维联判。</span>
                  <button class="anaLink" @click="openAnalysis()">打开战法分析</button>
                </div>

                <div class="dSub">大事件提醒<span class="dSubNote">基于今日行情与盘口异动的规则提醒</span></div>
                <div v-if="alerts.length" class="alList">
                  <div v-for="(a, i) in alerts" :key="i" class="alItem" :class="a.level">
                    <i class="alDot"></i>{{ a.text }}
                  </div>
                </div>
                <div v-else class="dEmpty">今日暂无显著事件</div>
              </template>
              <div v-else class="dEmpty">
                资料加载失败
                <button class="retryLink" @click="loadF10(selected)">重试</button>
              </div>
            </div>

            <!-- ===== 公司架构 ===== -->
            <div v-else class="pane">
              <div v-if="f10Cache[selected]?.loading" class="dLoading"><i class="dSpin"></i>资料加载中…</div>
              <template v-else-if="f10">
                <div class="dSub">管理层构成<span class="dSubNote">董监高 · 点姓名行展开履历</span></div>
                <template v-if="execStats">
                  <div class="statStrip">
                    <div class="stat">
                      <span class="sCap">高管人数</span><b>{{ execStats.total }}</b>
                    </div>
                    <div class="stat">
                      <span class="sCap">男性</span><b>{{ execStats.male }} 人</b>
                    </div>
                    <div class="stat">
                      <span class="sCap">女性</span><b>{{ execStats.female }} 人</b>
                    </div>
                    <div class="stat" v-if="execStats.avgAge">
                      <span class="sCap">平均年龄</span><b>{{ execStats.avgAge }} 岁</b>
                    </div>
                  </div>
                  <div class="sxBar" title="男女比例">
                    <i class="m" :style="{ width: execStats.malePct + '%' }"></i>
                    <i class="f" :style="{ width: execStats.femalePct + '%' }"></i>
                  </div>
                  <div class="sxLegend">
                    <span><i class="lg m"></i>男 {{ execStats.malePct }}%</span>
                    <span><i class="lg f"></i>女 {{ execStats.femalePct }}%</span>
                  </div>
                  <div class="mfTblWrap execTbl">
                    <table class="mfTbl">
                      <thead>
                        <tr><th class="l">姓名</th><th class="l">职务</th><th>性别</th><th>年龄</th><th>学历</th><th>年薪</th><th>持股</th></tr>
                      </thead>
                      <tbody>
                        <template v-for="e in f10.execs" :key="e.name + e.position">
                          <tr class="execRow" :class="{ open: expandedExec === execKey(e) }"
                              :title="e.resume ? '点击查看履历' : ''" @click="toggleExec(e)">
                            <td class="l">{{ e.name }}</td>
                            <td class="l">{{ e.position }}</td>
                            <td>{{ e.sex || "—" }}</td>
                            <td>{{ e.age || "—" }}</td>
                            <td>{{ e.degree || "—" }}</td>
                            <td>{{ e.salary ? (e.salary / 1e4).toFixed(1) + "万" : "—" }}</td>
                            <td>{{ e.hold_num ? (e.hold_num / 1e4).toFixed(1) + "万股" : "—" }}</td>
                          </tr>
                          <tr v-if="expandedExec === execKey(e) && e.resume" class="execResume">
                            <td colspan="7">{{ e.resume }}</td>
                          </tr>
                        </template>
                      </tbody>
                    </table>
                  </div>
                </template>
                <div v-else class="dEmpty">暂无管理层数据</div>
              </template>
              <div v-else class="dEmpty">
                资料加载失败
                <button class="retryLink" @click="loadF10(selected)">重试</button>
              </div>
            </div>
          </section>
        </template>

        <div v-else class="dPanel dEmptyBig">
          从左侧列表选择一只股票,查看{{ { fund: "盘口资金", basic: "基本分析", exec: "公司架构" }[tab] }}。
        </div>
      </div>

      <div v-if="!rows.length && !loading" class="stage">
        <div class="dPanel dEmptyBig">
          工作台为空,先用左侧搜索框添加几只股票,<br/>或点左上角图标从自选一键导入。
        </div>
      </div>
    </div>

    <!-- ===== 左树右键菜单 ===== -->
    <Teleport to="body">
      <div v-if="ctxMenu" class="ctxMenu"
           :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }">
        <template v-if="ctxMenu.type === 'group'">
          <button class="ctxItem" @click="ctxAct((g) => startRename(g))">重命名分组</button>
          <button class="ctxItem danger" @click="ctxAct((g) => askRemoveGroup(g))">删除分组</button>
        </template>
        <template v-else>
          <button class="ctxItem" @click="ctxAct((r) => pick(r.f12, 'fund'))">盘口资金</button>
          <button class="ctxItem" @click="ctxAct((r) => pick(r.f12, 'basic'))">基本分析</button>
          <button class="ctxItem" @click="ctxAct((r) => openAnalysis(r.f12))">战法分析</button>
          <div class="ctxSep"></div>
          <button class="ctxItem" @click="ctxAct((r) => toggleStar(r))">
            {{ stars.has(ctxMenu.r.f12) ? "取消重点关注" : "标记重点关注" }}
          </button>
          <button class="ctxItem" @click="ctxAct(openGrpDlg)">设置分组…</button>
          <button v-if="ctxMenu.gid" class="ctxItem"
                  @click="ctxAct((r, m) => removeFromGroup(m.gid, r))">从本组移除</button>
          <button class="ctxItem danger" @click="ctxAct(askRemove)">从工作台移除</button>
        </template>
      </div>
    </Teleport>

    <!-- ===== 新建分组弹窗 ===== -->
    <Teleport to="body">
      <div v-if="grpNew.open" class="gMask" @click.self="grpNew.open = false">
        <div class="gCard" role="dialog" aria-label="新建分组">
          <div class="gTitle">新建分组</div>
          <input v-model="grpNew.name" class="gInput" maxlength="20"
                 placeholder="分组名称,如:短线池、中线观察"
                 @keydown.enter="doNewGroup" @keydown.esc="grpNew.open = false"
                 :ref="(el) => el && el.focus()" />
          <div class="gOps">
            <button class="gCancel" @click="grpNew.open = false">取消</button>
            <button class="gDone" :disabled="grpNew.saving || !grpNew.name.trim()"
                    @click="doNewGroup">{{ grpNew.saving ? "创建中…" : "创建" }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ===== 设置分组弹窗(勾选即进组/出组) ===== -->
    <Teleport to="body">
      <div v-if="grpDlg.open" class="gMask" @click.self="grpDlg.open = false">
        <div class="gCard" role="dialog" aria-label="设置分组">
          <div class="gTitle">设置分组 · {{ grpDlg.row?.f14 }} {{ grpDlg.row?.f12 }}</div>
          <div v-if="groups.length" class="gList">
            <button v-for="g in groups" :key="'gm' + g.id" class="gItem"
                    :class="{ on: g.codes.includes(grpDlg.row?.f12) }"
                    @click="toggleMembership(g)">
              <span class="gCheck"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 12.5l5 5L20 6.5"/></svg></span>
              {{ g.name }}
              <span class="gCnt">{{ g.codes.length }}</span>
            </button>
          </div>
          <div v-else class="gEmpty">还没有分组,点左上角 + 新建一个。</div>
          <div class="gOps">
            <button class="gDone" @click="grpDlg.open = false">完成</button>
          </div>
        </div>
      </div>
    </Teleport>

    <AnalysisModal ref="anaRef" :rows="rows" />

    <ConfirmModal
      :open="rmState.open"
      :title="'从工作台移除 ' + (rmState.row ? rmState.row.f14 : '')"
      :desc="rmState.row ? rmState.row.f12 + ' 将从工作台移除（含星标与分组成员关系），不影响自选。' : ''"
      ok-text="移除"
      :loading="rmState.loading"
      @confirm="removeWatch"
      @close="rmState.open = false"
    />

    <ConfirmModal
      :open="grpDel.open"
      :title="'删除分组 ' + (grpDel.row ? grpDel.row.name : '')"
      desc="仅删除分组及其成员关系,组内股票仍留在工作台。"
      ok-text="删除"
      :loading="grpDel.loading"
      @confirm="doRemoveGroup"
      @close="grpDel.open = false"
    />
  </div>
</template>

<style scoped>
/* ===== 终端式布局:整页固定视口内,左列表通高,右侧页签工作区 ===== */
.desk {
  display: grid; grid-template-columns: 296px minmax(0, 1fr);
  /* appContent 高 100vh-60,负 margin 吃掉其 padding 后,高度与其一致才能贴满底部 */
  height: calc(100vh - 60px);
  margin: -16px -24px -20px;
  overflow: hidden;
}
.up { color: var(--up); } .down { color: var(--down); }
.dimB { color: var(--dim); font-weight: 400 !important; }

/* ===== 左栏:工作台股票列表 ===== */
.rail {
  border-right: 1px solid var(--line);
  background: var(--panel);
  display: flex; flex-direction: column;
  min-height: 0;
}
.railHead {
  flex: none; display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px 10px;
}
.railTitle { font-size: 13.5px; font-weight: 650; letter-spacing: .03em; }
.railCnt {
  margin-left: 8px; font-family: var(--mono); font-size: 10.5px; color: var(--dim);
  border: 1px solid var(--line); border-radius: 999px; padding: 0 7px;
  font-weight: 400; vertical-align: 1px;
}
.railOps { display: inline-flex; gap: 4px; }
.railOpBtn {
  width: 26px; height: 26px; border: none; border-radius: 7px;
  background: none; color: var(--dim); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: color .15s, background .15s;
}
.railOpBtn svg { width: 15px; height: 15px; }
.railOpBtn:hover:not(:disabled) { color: var(--accent); background: var(--accent-dim); }
.railOpBtn:disabled { opacity: .5; cursor: default; }
.railEmpty { padding: 36px 16px; text-align: center; color: var(--dim); font-size: 12.5px; line-height: 2; }
.railEmpty a { color: var(--accent); text-decoration: none; }

/* ===== 左栏搜索添加(紧凑版,交互同自选页) ===== */
.railSearch {
  flex: none; position: relative; z-index: 30;
  padding: 0 12px 12px; border-bottom: 1px solid var(--line);
}
.rsInner {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg, transparent); border: 1px solid var(--line-strong);
  border-radius: 9px; padding: 0 10px; height: 34px;
  transition: border-color .15s, box-shadow .15s, border-radius .15s;
}
.rsInner:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.rsInner.open { border-radius: 9px 9px 0 0; }
.rsIcon { color: var(--dim); flex-shrink: 0; }
.rsInput {
  flex: 1; min-width: 0; border: none; outline: none; background: transparent;
  color: var(--txt); font-size: 12.5px; font-family: inherit;
}
.rsInput::placeholder { color: var(--dim); }
.rsSpin {
  width: 13px; height: 13px; flex-shrink: 0; border-radius: 50%;
  border: 2px solid var(--line-strong); border-top-color: var(--accent);
  animation: dSpin .7s linear infinite;
}
.rsDrop {
  position: absolute; top: 34px; left: 12px; right: 12px;
  background: var(--panel); border: 1px solid var(--line-strong); border-top: none;
  border-radius: 0 0 9px 9px; overflow: hidden;
  box-shadow: 0 12px 32px rgba(0, 0, 0, .14);
  max-height: 320px; overflow-y: auto;
}
.rsEmpty { padding: 16px; text-align: center; color: var(--dim); font-size: 12px; }

/* 单条结果的添加位置选择(caret + 固定定位小菜单) */
.rsAddMenu {
  position: fixed; z-index: 60; min-width: 124px;
  background: var(--panel); border: 1px solid var(--line-strong); border-radius: 9px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, .16); padding: 4px;
}
.rsAddMenu button {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  width: 100%; background: none; border: none; border-radius: 6px;
  font-family: inherit; font-size: 12px; color: var(--txt); text-align: left;
  padding: 6px 10px; cursor: pointer; transition: background .12s;
}
.rsAddMenu button:hover:not(:disabled) { background: var(--hover); }
.rsAddMenu button:disabled { color: var(--dim); cursor: default; }
.rsAddMenu button i { font-style: normal; font-size: 10px; color: var(--dim); }
.rsItem {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: none; border: none; border-top: 1px solid var(--line);
  padding: 8px 12px; cursor: pointer; font-family: inherit; font-size: 12.5px;
  color: var(--txt); text-align: left; transition: background .12s;
}
.rsItem:first-child { border-top: none; }
.rsItem:hover, .rsItem.act { background: var(--hover); }
.rsItem.added { cursor: default; }
.rsItem mark { background: none; color: var(--accent); font-weight: 700; }
.rsName { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rsCode { color: var(--dim); font-family: var(--mono); font-size: 11px; }
.rsActs { margin-left: auto; flex-shrink: 0; display: flex; align-items: center; gap: 4px; }
.rsAct {
  font-size: 11px; font-weight: 600; color: var(--accent);
  border: 1px solid var(--accent); border-radius: 999px; padding: 1px 8px;
}
.rsAct.on { color: var(--dim); border-color: var(--line); font-weight: 400; }
.rsAddCaret {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 5px; color: var(--dim);
  transition: all .12s;
}
.rsAddCaret:hover { background: var(--accent-dim); color: var(--accent); }
.rsAddCaret svg { width: 11px; height: 11px; }

/* ===== 树(分组 + 股票叶) ===== */
.tree { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 8px 16px; }
.tGroup { margin-top: 2px; }

.tNode {
  display: flex; align-items: center; gap: 7px; width: 100%;
  background: none; border: none; border-radius: 8px; cursor: pointer;
  font-family: inherit; color: var(--txt); text-align: left;
  padding: 7px 9px; font-size: 13px; transition: background .12s;
}
.tNode:hover { background: var(--hover); }
.tNode.on { background: var(--accent-dim); color: var(--accent); font-weight: 600; }

/* 分组节点 */
.tNode.g { color: var(--dim); font-size: 12px; letter-spacing: .03em; }
.tNode.g:hover { color: var(--txt); }
.tArrow {
  width: 11px; height: 11px; flex: none; color: var(--dim);
  transition: transform .18s;
}
.tArrow.shut { transform: rotate(-90deg); }
.tCount {
  margin-left: auto; font-family: var(--mono); font-size: 10.5px; color: var(--dim);
  border: 1px solid var(--line); border-radius: 999px; padding: 0 7px;
}
.tStarIco { width: 12px; height: 12px; color: #f5a623; flex: none; }
.tFolderIco { width: 13px; height: 13px; color: var(--accent); flex: none; }
.tListIco { width: 13px; height: 13px; color: var(--dim); flex: none; }
.tNode.g.dropGrp {
  background: var(--accent-dim); color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}

/* 分组内联输入(新建 / 重命名) */
.tRename {
  flex: 1; min-width: 0; border: 1px solid var(--accent); border-radius: 6px;
  background: var(--panel); color: var(--txt); outline: none;
  font-family: inherit; font-size: 12px; padding: 2px 8px;
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.tGrpHint { padding: 10px 12px 12px 26px; color: var(--dim); font-size: 11px; line-height: 1.8; }

/* 子级缩进 + 引导线 */
.tKids {
  margin-left: 15px; padding-left: 9px;
  border-left: 1px solid var(--line);
}
.tNode.leaf { padding: 6.5px 9px; }
.tNode.leaf.dropHere { box-shadow: inset 0 2px 0 var(--accent); }

/* 股票叶节点内部 */
.dStar {
  flex: none; color: var(--line-strong); font-size: 13px; line-height: 1;
  transition: color .15s, transform .1s; cursor: pointer;
}
.dStar:hover { color: var(--dim); transform: scale(1.18); }
.dStar.on { color: #f5a623; }
.dName {
  flex: 1; min-width: 0; font-size: 12.5px; font-weight: 550;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dName i { font-style: normal; font-family: var(--mono); font-size: 10.5px; color: var(--dim); margin-left: 6px; }
.dPct { flex: none; font-family: var(--mono); font-size: 11.5px; width: 58px; text-align: right; }

/* ===== 右键菜单 ===== */
.ctxMenu {
  position: fixed; z-index: 1000; min-width: 140px;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 10px; box-shadow: 0 10px 28px rgba(0, 0, 0, .18);
  padding: 5px;
}
.ctxItem {
  display: block; width: 100%; background: none; border: none; border-radius: 6px;
  padding: 7px 12px; font-family: inherit; font-size: 12.5px; color: var(--txt);
  text-align: left; cursor: pointer; transition: background .12s;
}
.ctxItem:hover { background: var(--hover); }
.ctxItem.danger { color: var(--up); }
.ctxSep { height: 1px; background: var(--line); margin: 4px 6px; }

/* ===== 设置分组弹窗 ===== */
.gMask {
  position: fixed; inset: 0; z-index: 999;
  background: rgba(15, 20, 30, .38); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center;
}
.gCard {
  width: 320px; max-width: calc(100vw - 48px); max-height: 70vh;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 14px; box-shadow: 0 18px 48px rgba(0, 0, 0, .22);
  padding: 16px 16px 12px; display: flex; flex-direction: column;
}
.gTitle { font-size: 13.5px; font-weight: 650; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
.gList { overflow-y: auto; margin: 4px -6px 0; padding: 0 6px; }
.gItem {
  display: flex; align-items: center; gap: 9px; width: 100%;
  background: none; border: none; border-radius: 8px; cursor: pointer;
  font-family: inherit; font-size: 13px; color: var(--txt); text-align: left;
  padding: 8px 10px; transition: background .12s;
}
.gItem:hover { background: var(--hover); }
.gCheck {
  flex: none; width: 16px; height: 16px; border-radius: 5px;
  border: 1.5px solid var(--line-strong); display: inline-flex;
  align-items: center; justify-content: center; transition: all .15s;
}
.gCheck svg { width: 10px; height: 10px; opacity: 0; }
.gItem.on .gCheck { border-color: var(--accent); background: var(--accent); color: #fff; }
.gItem.on .gCheck svg { opacity: 1; }
.gCnt {
  margin-left: auto; font-family: var(--mono); font-size: 10.5px; color: var(--dim);
  border: 1px solid var(--line); border-radius: 999px; padding: 0 7px;
}
.gEmpty { padding: 26px 8px; text-align: center; color: var(--dim); font-size: 12.5px; line-height: 1.9; }
.gInput {
  width: 100%; margin-top: 12px; box-sizing: border-box;
  border: 1px solid var(--line-strong); border-radius: 9px; outline: none;
  background: var(--bg, transparent); color: var(--txt);
  font-family: inherit; font-size: 13px; padding: 8px 12px;
  transition: border-color .15s, box-shadow .15s;
}
.gInput:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.gOps { display: flex; justify-content: flex-end; gap: 8px; padding-top: 12px; border-top: 1px solid var(--line); margin-top: 12px; }
.gCancel {
  background: none; border: 1px solid var(--line); border-radius: 999px;
  color: var(--dim); font-family: inherit; font-size: 12.5px; padding: 5px 16px;
  cursor: pointer; transition: all .15s;
}
.gCancel:hover { color: var(--txt); border-color: var(--line-strong); }
.gDone {
  background: var(--accent); color: #fff; border: none; border-radius: 999px;
  font-family: inherit; font-size: 12.5px; padding: 5px 20px; cursor: pointer;
  transition: opacity .15s;
}
.gDone:hover:not(:disabled) { opacity: .88; }
.gDone:disabled { opacity: .5; cursor: default; }

/* ===== 右侧工作区:页签 + 固定高度舞台 ===== */
.main {
  min-width: 0; min-height: 0;
  display: flex; flex-direction: column;
}
.topTabs {
  flex: none; display: flex; align-items: center; gap: 4px;
  padding: 8px 24px 0; border-bottom: 1px solid var(--line);
}
.topTabs button {
  background: none; border: none; color: var(--dim); font-family: inherit;
  font-size: 13.5px; padding: 10px 14px; cursor: pointer;
  border-bottom: 2px solid transparent; transition: color .15s;
}
.topTabs button:hover { color: var(--txt); }
.topTabs button.on { color: var(--accent); border-bottom-color: var(--accent); font-weight: 650; }
.topMeta {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--mono); font-size: 11px; color: var(--dim);
  padding-bottom: 8px;
}
.stage {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 18px 24px 32px;
  display: flex; flex-direction: column; gap: 18px;
}
.dPanel {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; padding: 16px 20px 18px; flex: none;
}
.dHead { display: flex; align-items: baseline; gap: 10px; padding-bottom: 12px; }
.dTitle { font-size: 14px; font-weight: 650; letter-spacing: .04em; }
.dTitle::before {
  content: ""; display: inline-block; width: 3px; height: 11px; border-radius: 2px;
  background: var(--brand-red); margin-right: 7px; vertical-align: -1px;
}
.dEn { font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: var(--dim); font-family: var(--mono); }
.dMeta {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--mono); font-size: 11px; color: var(--dim);
}
.liveDot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.liveDot.idle { background: var(--dim); box-shadow: none; }
.dEmpty { color: var(--dim); font-size: 12.5px; padding: 26px 4px; text-align: center; }
.dEmptyBig { text-align: center; color: var(--dim); font-size: 13px; line-height: 2; padding: 60px 20px; }
.dLoading { display: flex; align-items: center; gap: 10px; color: var(--dim); font-size: 12.5px; padding: 30px 4px; justify-content: center; }
.dSpin {
  width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid var(--line-strong); border-top-color: var(--accent);
  animation: dSpin .8s linear infinite;
}
@keyframes dSpin { to { transform: rotate(360deg); } }
.dSub { font-size: 13px; font-weight: 650; margin: 20px 0 10px; display: flex; align-items: baseline; gap: 10px; }
.dSub:first-child { margin-top: 4px; }
.dSubNote { font-size: 11px; color: var(--dim); font-weight: 400; }
.dNote { font-size: 11.5px; color: var(--dim); line-height: 1.7; }
.retryLink {
  background: none; border: none; color: var(--accent); font-size: 12px;
  font-family: inherit; cursor: pointer; padding: 0; margin-left: 8px;
  text-decoration: underline; text-underline-offset: 3px;
}

/* ===== 选中股票头部 ===== */
.hero {
  flex: none;
  display: flex; align-items: center; gap: 28px; flex-wrap: wrap;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; padding: 16px 22px;
}
.heroName { font-size: 19px; font-weight: 650; display: flex; align-items: center; }
.heroCode { font-family: var(--mono); font-size: 12px; color: var(--dim); margin-left: 10px; font-weight: 400; }
.heroInd { font-size: 12px; color: var(--dim); margin-top: 3px; }
.heroPrice { display: flex; align-items: baseline; gap: 10px; }
.heroPrice b { font-family: var(--mono); font-size: 30px; font-weight: 650; line-height: 1; }
.heroPrice span { font-family: var(--mono); font-size: 14px; font-weight: 600; }
.heroKv { margin-left: auto; display: flex; gap: 26px; flex-wrap: wrap; }
.kv { display: flex; flex-direction: column; gap: 2px; }
.kv span { font-size: 11px; color: var(--dim); }
.kv b { font-family: var(--mono); font-size: 14.5px; font-weight: 600; }

/* ===== 实时监控:双卡填满舞台 ===== */
.monGrid { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.monGrid .dPanel { min-height: 0; display: flex; flex-direction: column; }
.flowSum {
  display: flex; gap: 16px; font-size: 12px; color: var(--dim);
  padding-bottom: 10px; border-bottom: 1px dashed var(--line); margin-bottom: 4px;
}
.flowSum b { font-family: var(--mono); }
.flowList, .feedList { overflow-y: auto; margin: 0 -8px; padding: 0 8px; }
.monGrid .flowList, .monGrid .feedList { flex: 1; min-height: 0; }
.feedList.static { overflow: visible; margin-top: 2px; }
.dirFilter { display: inline-flex; gap: 2px; margin-left: 10px; }
.dirFilter button {
  background: none; border: 1px solid var(--line); border-radius: 999px;
  color: var(--dim); font-size: 11px; font-family: inherit; cursor: pointer;
  padding: 1px 10px; transition: all .15s;
}
.dirFilter button:hover { color: var(--txt); border-color: var(--line-strong); }
.dirFilter button.on { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }

.fRow {
  display: flex; align-items: center; gap: 10px; width: 100%;
  background: none; border: none; border-radius: 8px; cursor: pointer;
  padding: 6.5px 8px; font-family: inherit; color: var(--txt); transition: background .12s;
}
.fRow:hover { background: var(--hover); }
.fRow.on { background: var(--accent-dim); }
.fName { flex: none; width: 72px; font-size: 12.5px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fBar { flex: 1; position: relative; height: 14px; }
.fZero { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--line-strong); }
.fFill { position: absolute; top: 2px; bottom: 2px; border-radius: 3px; transition: width .4s cubic-bezier(.2,.8,.2,1); }
.fFill.in { background: var(--up); }
.fFill.out { background: var(--down); }
.fVal { flex: none; width: 76px; text-align: right; font-family: var(--mono); font-size: 12px; }

.cRow {
  display: flex; align-items: center; gap: 10px; width: 100%;
  background: none; border: none; border-radius: 8px; cursor: pointer;
  padding: 7px 8px; font-family: inherit; color: var(--txt); transition: background .12s;
}
.cRow:hover { background: var(--hover); }
.cRow.asRow { cursor: default; }
.cRow.asRow:hover { background: none; }
.cTime { flex: none; font-family: var(--mono); font-size: 11px; color: var(--dim); width: 48px; }
.cName { flex: none; width: 68px; font-size: 12.5px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cType { flex: none; font-size: 10.5px; border-radius: 4px; padding: 1px 7px; white-space: nowrap; }
.cType.bull { color: var(--up); background: color-mix(in srgb, var(--up) 12%, transparent); }
.cType.bear { color: var(--down); background: color-mix(in srgb, var(--down) 12%, transparent); }
.cVal { margin-left: auto; font-family: var(--mono); font-size: 11.5px; color: var(--dim); }
.cVal b { color: var(--txt); font-weight: 600; }

/* ===== 个股视图 ===== */
.detail { flex: none; }
.pane { animation: dFade .18s ease; }
@keyframes dFade { from { opacity: .35; } to { opacity: 1; } }

/* ===== 盘口资金 ===== */
.statStrip { display: flex; gap: 34px; flex-wrap: wrap; margin-bottom: 4px; }
.stat { display: flex; flex-direction: column; gap: 3px; }
.sCap { font-size: 11px; color: var(--dim); }
.stat b { font-family: var(--mono); font-size: 17px; font-weight: 650; }

.mfChart { width: 100%; height: 190px; display: block; }
.mfZero { stroke: var(--line-strong); stroke-width: 1; }
.mfChart rect.in { fill: var(--up); }
.mfChart rect.out { fill: var(--down); }
.mfTick { fill: var(--dim); font-size: 10px; font-family: var(--mono); }
.mfLegend { display: flex; gap: 18px; align-items: center; font-size: 11px; color: var(--dim); margin-top: 6px; }
.mfLegend .lg { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.lg.in { background: var(--up); } .lg.out { background: var(--down); }

.mfTblWrap { overflow-x: auto; }
.mfTbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.mfTbl th, .mfTbl td { padding: 6px 10px; text-align: right; border-bottom: 1px solid var(--line); white-space: nowrap; }
.mfTbl th { color: var(--dim); font-weight: 500; font-size: 11px; letter-spacing: .04em; }
.mfTbl td { font-family: var(--mono); font-size: 12px; }
.mfTbl .l { text-align: left; }
.mfTbl tbody tr:last-child td { border-bottom: none; }

/* ===== 基本分析 ===== */
.chipWrap { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { font-size: 12px; color: var(--dim); border: 1px solid var(--line); border-radius: 999px; padding: 3px 12px; }
.chip.hot { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.ptList { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.ptItem b { font-size: 12.5px; }
.ptItem p { font-size: 12px; color: var(--dim); line-height: 1.7; margin-top: 2px; }
.ptItem p + p { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--line); }

.hdChart { width: 100%; height: 130px; display: block; margin-top: 10px; }
.hdBar { fill: var(--accent); fill-opacity: .35; }
.hdBar.last { fill-opacity: .9; }
.hdVal { fill: var(--dim); font-size: 10px; font-family: var(--mono); }
.hdDate { fill: var(--dim); font-size: 10px; font-family: var(--mono); }

.kvGrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 24px; }
.kv2 { display: flex; flex-direction: column; gap: 2px; border-bottom: 1px dashed var(--line); padding-bottom: 7px; }
.kv2.wide { grid-column: span 3; }
.kv2 span { font-size: 11px; color: var(--dim); }
.kv2 b { font-size: 13px; font-weight: 550; }
.intro { font-size: 12.5px; color: var(--dim); line-height: 1.8; margin-top: 12px; }

/* 公司架构:男女比例条 */
.sxBar {
  display: flex; height: 8px; border-radius: 999px; overflow: hidden;
  background: var(--line); margin-top: 12px;
}
.sxBar .m { background: var(--accent); }
.sxBar .f { background: #ec6a8a; }
.sxLegend { display: flex; gap: 16px; font-size: 11px; color: var(--dim); margin: 6px 0 4px; }
.sxLegend .lg { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.sxLegend .lg.m { background: var(--accent); }
.sxLegend .lg.f { background: #ec6a8a; }
.execTbl { margin-top: 6px; }
.execRow { cursor: pointer; transition: background .12s; }
.execRow:hover { background: var(--hover); }
.execRow.open td { border-bottom: none; }
.execRow.open td.l:first-child { color: var(--accent); font-weight: 600; }
.execResume td {
  text-align: left !important; font-family: inherit !important;
  font-size: 12px; color: var(--dim); line-height: 1.8;
  padding: 4px 10px 12px !important; white-space: normal !important;
}

.zfaRow { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.anaLink {
  flex: none; background: none; border: 1px solid var(--line-strong); border-radius: 999px;
  color: var(--accent); padding: 4px 16px; font-size: 12.5px; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.anaLink:hover { border-color: var(--accent); background: var(--accent-dim); }

.alList { display: flex; flex-direction: column; }
.alItem {
  display: flex; align-items: baseline; gap: 10px;
  font-size: 12.5px; padding: 7px 2px; border-bottom: 1px solid var(--line);
}
.alItem:last-child { border-bottom: none; }
.alDot { flex: none; width: 7px; height: 7px; border-radius: 50%; transform: translateY(-1px); }
.alItem.high .alDot { background: var(--up); box-shadow: 0 0 0 3px color-mix(in srgb, var(--up) 15%, transparent); }
.alItem.mid .alDot { background: var(--hot); }
.alItem.low .alDot { background: var(--dim); }

/* ===== 响应式 ===== */
@media (max-width: 1080px) {
  .monGrid { grid-template-columns: 1fr; overflow-y: auto; }
  .monGrid .dPanel { min-height: 420px; }
}
@media (max-width: 860px) {
  .desk { grid-template-columns: 1fr; height: auto; overflow: visible; margin: 0; }
  .rail { border-right: none; border-bottom: 1px solid var(--line); max-height: 45vh; }
  .main { overflow: visible; }
  .stage { overflow: visible; padding: 16px 0 24px; }
  .heroKv { margin-left: 0; gap: 18px; }
  .kvGrid { grid-template-columns: 1fr 1fr; }
  .kv2.wide { grid-column: span 2; }
  .heroPrice b { font-size: 24px; }
}
</style>
