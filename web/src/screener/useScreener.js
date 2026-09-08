/* ===== useScreener:换手率筛选页全部响应式状态与逻辑(移植自旧 screener-app.js)=====
   前后端分离版:筛选/过滤由后端 SQL 完成(/api/quote/list),
   前端保留排序、渲染数据、CSV 导出;行业统计与情绪统计来自 /api/quote/meta。 */
import { computed, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { apiFetch } from "../api/client";
import { cmpRows, fmtN, rangeVal } from "../utils/format";
import { fetchIndexKline } from "../analysis/data";
import {
  addMetric,
  metricDef,
  metricExtraCols,
  metricsQueryParam,
  metricsSummaryPart,
  normalizeMetricsState,
  removeMetric,
} from "./metrics";

export const LOAD_STEP = 60;   // 手机端每次加载条数
export const RENDER_CAP = 500; // 桌面表格渲染上限
export const IS_MOBILE = () => window.matchMedia("(max-width: 768px)").matches;

// 基础排序项(手机端排序 chips;自定义指标会动态追加)
export const SORT_LABELS = { f8: "换手率", f3: "涨跌幅", f6: "成交额", f20: "总市值", f9: "市盈率" };

// 市场定义(勾选值与旧版一致,直接拼进 markets 参数)
export const MKT_DEFS = [
  { value: "m:1+t:2", label: "沪主板" },
  { value: "m:0+t:6", label: "深主板" },
  { value: "m:0+t:80", label: "创业板" },
  { value: "m:1+t:23", label: "科创板" },
  { value: "m:0+t:81+s:2048", label: "北交所" },
];

export function useScreener() {
  // ===== 筛选条件 =====
  const tMin = ref("8"), tMax = ref(""), cMin = ref("-8"), cMax = ref("-5");
  const kw = ref(""), industry = ref("");
  const mkts = ref([true, true, true, true, false]); // 对应 MKT_DEFS 顺序
  const noST = ref(true), noSuspend = ref(true);
  const metrics = ref([]); // [{k, min, max}] min/max 为输入框原始字符串,空 = 不设界

  // ===== 结果 / 排序 / 分页 / 页签 =====
  const allRows = ref([]), lastTotal = ref(0), lastMeta = ref(null), hasRun = ref(false);
  const sortKey = ref("f8"), sortDir = ref(-1), indSortKey = ref("avgT"), indSortDir = ref(-1);
  const shown = ref(LOAD_STEP);
  const tab = ref("stock"); // stock | ind

  // ===== 查询中状态 =====
  const querying = ref(false);
  const progressVisible = ref(false);
  const statusTxt = ref("");
  let abortFlag = false;

  // ===== 行业下拉 / 数据源徽标 / 情绪徽标 / 折叠面板 =====
  const industries = ref([]);        // [{name, n}]
  const industryReady = ref(false);  // 首次查询后才可按行业筛选
  let presetIndustry = null;         // URL 参数带来的预设行业,首次查询填充下拉后应用
  const srcBadge = reactive({ text: "未查询", rt: false }); // 数据源徽标(实时/延迟 + 快照时间)
  const senti = reactive({ show: false, lv: 3, text: "", title: "" }); // 情绪徽标
  const panelOpen = ref(true);       // 手机端折叠面板

  // ===== 筛选条件摘要(手机折叠面板显示)=====
  const summary = computed(() => {
    const [t1, t2] = rangeVal(tMin.value, tMax.value);
    const [c1, c2] = rangeVal(cMin.value, cMax.value);
    const parts = [];
    if (!isNaN(t1) || !isNaN(t2)) parts.push("换手 " + (isNaN(t1) ? "" : t1) + "~" + (isNaN(t2) ? "∞" : t2) + "%");
    if (!isNaN(c1) || !isNaN(c2)) parts.push("涨跌 " + (isNaN(c1) ? "" : c1) + "~" + (isNaN(c2) ? "∞" : c2) + "%");
    if (industry.value) parts.push(industry.value);
    const mPart = metricsSummaryPart(metrics.value);
    if (mPart) parts.push(mPart);
    parts.push(mkts.value.filter(Boolean).length + " 市场");
    return parts.join(" · ");
  });

  // ===== 本地记忆 =====
  function saveFilters() {
    try {
      localStorage.setItem("tsm-filters", JSON.stringify({
        tMin: tMin.value, tMax: tMax.value,
        cMin: cMin.value, cMax: cMax.value,
        kw: kw.value,
        mkts: mkts.value.slice(),
        noST: noST.value,
        noSuspend: noSuspend.value,
        metrics: metrics.value.map((m) => ({ k: m.k, min: m.min, max: m.max })),
      }));
    } catch (e) {}
  }
  function restoreFilters() {
    let f = null;
    try { f = JSON.parse(localStorage.getItem("tsm-filters") || "null"); } catch (e) {}
    if (!f) return;
    const set = (r, v) => { if (v !== undefined && v !== null && v !== "") r.value = v; };
    set(tMin, f.tMin); set(tMax, f.tMax); set(cMin, f.cMin); set(cMax, f.cMax); set(kw, f.kw);
    if (Array.isArray(f.mkts)) mkts.value = MKT_DEFS.map((_, i) => !!f.mkts[i]);
    if (f.noST !== undefined) noST.value = !!f.noST;
    if (f.noSuspend !== undefined) noSuspend.value = !!f.noSuspend;
    metrics.value = normalizeMetricsState(f.metrics);
  }

  // ===== URL 参数覆盖(对齐旧初始化:?tmin=8&cmin=-8&cmax=-5&industry=半导体&auto=1)=====
  function applyUrlQuery(q) {
    const get = (k) => { const v = q[k]; return Array.isArray(v) ? v[0] : v; };
    const set = (r, v) => { if (v !== null && v !== undefined && v !== "") r.value = String(v); };
    set(tMin, get("tmin")); set(tMax, get("tmax"));
    set(cMin, get("cmin")); set(cMax, get("cmax"));
    const ind = get("industry");
    if (ind) presetIndustry = String(ind);
    return get("auto") === "1";
  }

  // ===== 查询条件 → API 参数 =====
  function buildQuery() {
    const [t1, t2] = rangeVal(tMin.value, tMax.value);
    const [c1, c2] = rangeVal(cMin.value, cMax.value);
    const p = new URLSearchParams();
    p.set("markets", MKT_DEFS.filter((_, i) => mkts.value[i]).map((m) => m.value).join(","));
    if (!isNaN(t1)) p.set("tmin", t1);
    if (!isNaN(t2)) p.set("tmax", t2);
    if (!isNaN(c1)) p.set("cmin", c1);
    if (!isNaN(c2)) p.set("cmax", c2);
    if (industry.value) p.set("industry", industry.value);
    const k = kw.value.trim();
    if (k) p.set("kw", k);
    p.set("no_st", noST.value ? "1" : "0");
    p.set("no_suspend", noSuspend.value ? "1" : "0");
    const ms = metricsQueryParam(metrics.value);
    if (ms.length) p.set("metrics", JSON.stringify(ms));
    return p.toString();
  }

  // ===== 市场情绪徽标(统计量由后端 /api/quote/meta 给出;量能分量仍用指数日K)=====
  function updateSentiBadge(stats, idx) {
    if (!stats || !stats.valid) { senti.show = false; return; }
    const upRatio = stats.up / stats.valid;
    const limitScore = (stats.limit_up + stats.limit_down) > 0
      ? stats.limit_up / (stats.limit_up + stats.limit_down) * 30 : 15;
    // 量能分量:与 analysis computeSentiment 同一口径(5日均额比,盘中线性外推)
    let volScore = 15, volRatio = null, volSrc = "缺失（按中性计）", volNote = "";
    if (idx && idx.length > 5) {
      const amts = idx.map((b) => b.amount).filter(isFinite);
      if (amts.length > 5) {
        const ma = amts.slice(-6, -1).reduce((s, x) => s + x, 0) / 5;
        if (ma > 0) {
          let lastAmt = amts[amts.length - 1];
          const lastBar = idx[idx.length - 1];
          const _now = new Date();
          const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
          const mins = _now.getHours() * 60 + _now.getMinutes();
          const isWeekday = _now.getDay() % 6 !== 0;
          let elapsed = -1;
          if (isWeekday) {
            if (mins >= 570 && mins < 690) elapsed = mins - 570;
            else if (mins >= 690 && mins < 780) elapsed = 120;
            else if (mins >= 780 && mins < 900) elapsed = 120 + (mins - 780);
          }
          volSrc = "完整";
          if (elapsed > 0 && lastBar.date === today) {
            const ratio = Math.min(1, elapsed / 240);
            if (ratio > 0.05 && ratio < 0.99) {
              lastAmt = lastAmt / ratio;
              volSrc = "盘中外推";
              volNote = `按 ${elapsed}/240 分钟外推`;
            }
          }
          volRatio = lastAmt / ma;
          volScore = Math.min(30, Math.max(0, (volRatio - 0.5) * 30));
        }
      }
    }
    const temp = Math.round(upRatio * 40 + limitScore + volScore);
    const level = temp < 20 ? "冰点" : temp < 40 ? "低迷" : temp < 60 ? "中性" : temp < 80 ? "活跃" : "亢奋";
    senti.show = true;
    senti.lv = temp < 20 ? 1 : temp < 40 ? 2 : temp < 60 ? 3 : temp < 80 ? 4 : 5;
    senti.text = "情绪 " + temp + " · " + level;
    const upPct = (upRatio * 100).toFixed(0);
    const mktLabels = MKT_DEFS.filter((_, i) => mkts.value[i]).map((m) => m.label);
    const scope = mktLabels.length ? mktLabels.join("、") : "全市场";
    senti.title = `市场情绪 ${temp}/100 · ${level}\n` +
      `· 范围：${scope}（共 ${stats.valid} 只有效股）\n` +
      `· 上涨 ${stats.up} 家（${upPct}%） · 下跌 ${stats.down ?? stats.valid - stats.up} 家\n` +
      `· 涨停 ${stats.limit_up} / 跌停 ${stats.limit_down}\n` +
      `· 大跌(>5%) ${stats.big_down} 家\n` +
      (volRatio !== null
        ? `· 指数量能 ${volRatio.toFixed(2)}×5日均额 [${volSrc}]${volNote ? " " + volNote : ""}`
        : `· 指数量能：缺失（按中性计）`);
  }

  // ===== 行业下拉填充(门户页跳转带来的预设行业优先)=====
  function fillIndustry(inds) {
    industries.value = inds;
    industryReady.value = true;
    if (presetIndustry) {
      industry.value = presetIndustry;
      presetIndustry = null;
    } else if (industry.value && !inds.some((x) => x.name === industry.value)) {
      industry.value = ""; // 旧 select 赋不存在的值会落空,这里同步清掉
    }
  }

  // ===== 一键查询:后端已定时抓全市场快照入库,前端一次 API 调用出结果 =====
  async function run() {
    const checked = MKT_DEFS.filter((_, i) => mkts.value[i]);
    if (!checked.length) { message.warning("请至少勾选一个市场"); return; }
    querying.value = true;
    abortFlag = false;
    saveFilters();
    const t0 = performance.now();
    progressVisible.value = true;
    statusTxt.value = "查询中…";
    try {
      const mqs = "markets=" + encodeURIComponent(checked.map((c) => c.value).join(","));
      const [lr, mr] = await Promise.all([
        apiFetch("/api/quote/list?" + buildQuery()),
        apiFetch("/api/quote/meta?" + mqs),
      ]);
      if (abortFlag) return;
      if (!lr.ok || !mr.ok) throw new Error("HTTP " + lr.status);
      const list = await lr.json(), meta = await mr.json();
      allRows.value = list.rows || [];
      lastTotal.value = typeof list.total === "number" ? list.total : allRows.value.length;
      lastMeta.value = meta;
      hasRun.value = true;
      shown.value = LOAD_STEP;

      // 数据源徽标:实时/延迟 + 快照时间;抓取失败中的陈旧数据明确标注
      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      const tm = list.fetched_at ? list.fetched_at.replace("T", " ").slice(5, 16) : "--";
      let txt = (list.source || "行情快照") + " " + tm;
      if (list.stale) txt += " · 抓取失败中";
      srcBadge.text = txt;
      srcBadge.rt = list.source === "实时行情" && !list.stale;
      statusTxt.value = list.fetched_at
        ? "完成 · " + lastTotal.value + " 只符合条件 · 耗时 " + secs + "s" + (list.stale ? " · 数据为最近一次成功快照" : "")
        : "后端正在初始化数据，请稍后重试";

      fillIndustry(meta.industries || []);
      updateSentiBadge(meta.stats, null);                                        // 先出价格统计的温度
      fetchIndexKline()
        .then((i) => updateSentiBadge(lastMeta.value && lastMeta.value.stats, i)) // 再补量能分量
        .catch(() => {});
      if (IS_MOBILE()) {
        panelOpen.value = false; // 手机端查询后折叠筛选面板
        setTimeout(() => { if (!querying.value) progressVisible.value = false; }, 2500);
      }
    } catch (e) {
      if (e.message !== "unauthorized") {
        statusTxt.value = "查询失败：" + e.message + "（请稍后重试）";
        message.error("查询失败，请稍后重试");
      }
    } finally {
      querying.value = false;
    }
  }
  function cancel() { abortFlag = true; }

  // ===== 条件变化 → 防抖重查(过滤在服务端,本地不再有过滤逻辑)=====
  let refilterTimer = null;
  function refilter() {
    if (!hasRun.value) return;
    clearTimeout(refilterTimer);
    refilterTimer = setTimeout(run, 400);
  }
  // 搜索框单独 200ms 防抖(旧版行为)
  let kwTimer = null;
  function onKwInput() {
    clearTimeout(kwTimer);
    kwTimer = setTimeout(refilter, 200);
  }
  // 市场勾选变化影响数据范围,立即重查
  function onMktChange() {
    if (hasRun.value) run();
  }

  // ===== 自定义指标增删/编辑(条件变化统一走防抖重查)=====
  function addMetricByKey(k) {
    const next = addMetric(metrics.value, k);
    if (next === metrics.value) return;
    metrics.value = next;
    saveFilters();
    refilter();
  }
  function removeMetricByKey(k) {
    metrics.value = removeMetric(metrics.value, k);
    saveFilters();
    refilter();
  }
  function onMetricInput() {
    saveFilters();
    refilter();
  }

  // ===== 排序(表头/排序 chips 均含动态列)=====
  function setSort(k, defaultDir) {
    if (sortKey.value === k) sortDir.value *= -1;
    else { sortKey.value = k; sortDir.value = defaultDir; }
    shown.value = LOAD_STEP; // 旧版 render() 会重置卡片分页
  }
  function setIndSort(k) {
    if (indSortKey.value === k) indSortDir.value *= -1;
    else { indSortKey.value = k; indSortDir.value = k === "name" ? 1 : -1; }
  }

  // ===== 行业标签/行业卡片点击 → 按行业筛选并切回个股页 =====
  function selectIndustry(name) {
    industry.value = name === "未分类" ? "" : name;
    tab.value = "stock";
    refilter();
    if (IS_MOBILE()) window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ===== 渲染数据(服务端已完成过滤,本地仅排序)=====
  const sortedRows = computed(() => allRows.value.slice().sort(cmpRows(sortKey.value, sortDir.value)));
  const tableRows = computed(() => sortedRows.value.slice(0, RENDER_CAP)); // 桌面表格渲染上限
  const cardRows = computed(() => sortedRows.value.slice(0, shown.value)); // 手机卡片分页
  const hasMore = computed(() => sortedRows.value.length > shown.value);

  function indAgg(rows) {
    const g = {};
    rows.forEach((r) => {
      const k = r.f100 || "未分类";
      (g[k] = g[k] || { name: k, n: 0, t: 0, c: 0, up: 0, amt: 0 });
      g[k].n++; g[k].t += r.f8 || 0; g[k].c += r.f3 || 0; g[k].amt += r.f6 || 0;
      if (r.f3 > 0) g[k].up++;
    });
    return Object.values(g).map((x) => ({ name: x.name, n: x.n, avgT: x.t / x.n, avgC: x.c / x.n, upN: x.up, amount: x.amt }));
  }
  const indRows = computed(() => indAgg(allRows.value).sort(cmpRows(indSortKey.value, indSortDir.value)));

  // 桌面表格需要追加的指标列(跳过基础列)
  const extraCols = computed(() => metricExtraCols(metrics.value));

  // 手机端排序 chips:基础项 + 动态追加的自定义指标
  const sortChips = computed(() => {
    const extra = metrics.value.map((m) => metricDef(m.k)).filter((d) => !SORT_LABELS[d.k]);
    return Object.entries(SORT_LABELS)
      .map(([k, name]) => ({ k, name }))
      .concat(extra.map((d) => ({ k: d.k, name: d.name })));
  });

  // 渲染上限提示文案
  const capNote = computed(() => {
    const rows = allRows.value;
    if (lastTotal.value > rows.length)
      return { show: true, text: "结果超过返回上限，仅显示前 " + rows.length + " 条，请收窄条件" };
    return { show: rows.length > RENDER_CAP, text: "表格仅渲染前 500 行，导出 CSV 含全部结果" };
  });

  function loadMore() { shown.value += LOAD_STEP; }

  // ===== 导出 CSV(含全部筛选结果与自定义指标列,BOM 头保证 Excel 中文不乱码)=====
  function exportCSV() {
    const mCols = metricExtraCols(metrics.value);
    const head = "代码,名称,最新价,涨跌幅%,换手率%,行业,成交额(亿),总市值(亿),市盈率"
      + (mCols.length ? "," + mCols.map((d) => d.name + (d.unit ? "(" + d.unit + ")" : "")).join(",") : "") + "\n";
    const body = sortedRows.value.map((r) => {
      const base = [
        r.f12, r.f14, fmtN(r.f2), fmtN(r.f3), fmtN(r.f8), r.f100 || "",
        typeof r.f6 === "number" ? (r.f6 / 1e8).toFixed(2) : "",
        typeof r.f20 === "number" ? (r.f20 / 1e8).toFixed(2) : "",
        fmtN(r.f9, 1),
      ];
      const extra = mCols.map((d) => { const v = d.disp(r[d.k]); return v === null ? "" : v.toFixed(2); });
      return base.concat(extra).join(",");
    }).join("\n");
    const blob = new Blob(["﻿" + head + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "换手率筛选_" + new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-") + ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return {
    // 常量
    LOAD_STEP, RENDER_CAP, IS_MOBILE, SORT_LABELS, MKT_DEFS,
    // 筛选条件
    tMin, tMax, cMin, cMax, kw, industry, mkts, noST, noSuspend, metrics,
    // 结果/排序/分页/页签
    allRows, lastTotal, lastMeta, hasRun, sortKey, sortDir, indSortKey, indSortDir, shown, tab,
    // 查询中状态
    querying, progressVisible, statusTxt,
    // 行业/徽标/面板
    industries, industryReady, srcBadge, senti, panelOpen, summary,
    // 渲染数据
    sortedRows, tableRows, cardRows, hasMore, indRows, extraCols, sortChips, capNote,
    // 方法
    saveFilters, restoreFilters, applyUrlQuery, buildQuery, updateSentiBadge,
    run, cancel, refilter, onKwInput, onMktChange,
    addMetricByKey, removeMetricByKey, onMetricInput,
    setSort, setIndSort, selectIndustry, loadMore, exportCSV,
  };
}
