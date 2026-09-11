<script setup>
/* ===== 板块资金雷达（移植自 capital-flow-pro.html，Vue 化）=====
   聚合概念/行业板块主力净流入：累计分时曲线、资金广度、近 5 分钟异动、
   流入流出排行、白名单独立追踪。数据直连东方财富延迟行情（JSONP），
   偏好存 localStorage、快照历史存 sessionStorage。埋点 flow_view。 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { message } from "ant-design-vue";
import FlowChart from "../flow/FlowChart.vue";
import {
  INDUSTRY_ALLOW, fetchAllSectors, isBasket, loadSeries, marketState,
  fmtYi, fmtYiShort, pad2, timeText,
} from "../flow/capital-flow";
import { track } from "../api/client";

const PREFS_KEY = "flow_prefs_v1";
const HISTORY_KEY = "flow_history_v1";

/* ===== 状态 ===== */
const industry = ref(false);        // false=概念板块 true=行业板块
const topN = ref(8);
const intervalSec = ref(300);
const autoRefresh = ref(true);
const whitelist = ref([]);          // 白名单板块名
const blocked = ref([]);            // 手动屏蔽板块名
const allSectors = ref([]);
const snapshot = ref({});           // code -> { name, value } 当前截面
const prevSnap = ref(null);         // 约 5 分钟前的历史快照（用于异动）
const history = ref([]);            // [{ time, snapshot }]
const mainRows = ref([]);
const watchRows = ref([]);
const busy = ref(false);
const nextAt = ref(0);
const statusText = ref("等待首次同步");
const lastUpdate = ref("—");
const snapshotLabel = ref("—");
const now = ref(new Date());
const settingsOpen = ref(false);
const watchInput = ref("");
const blockInput = ref("");
const settingsPanel = ref(null);
const settingsBtn = ref(null);

/* ===== 偏好与历史持久化 ===== */
function loadPrefs() {
  try {
    const s = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
    industry.value = !!s.industry;
    topN.value = [6, 8, 10, 12].includes(Number(s.topN)) ? Number(s.topN) : 8;
    intervalSec.value = [300, 600, 900].includes(Number(s.intervalSec)) ? Number(s.intervalSec) : 300;
    autoRefresh.value = s.autoRefresh !== false;
    whitelist.value = Array.isArray(s.whitelist) ? s.whitelist : [];
    blocked.value = Array.isArray(s.blocked) ? s.blocked : [];
  } catch (e) {}
  try {
    const h = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]");
    history.value = Array.isArray(h)
      ? h.filter((it) => it && Number.isFinite(it.time) && it.snapshot && typeof it.snapshot === "object").slice(-12)
      : [];
  } catch (e) {}
}
function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      industry: industry.value, topN: topN.value, intervalSec: intervalSec.value,
      autoRefresh: autoRefresh.value, whitelist: whitelist.value, blocked: blocked.value,
    }));
  } catch (e) {}
}
function saveHistory() {
  try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history.value.slice(-12))); } catch (e) {}
}

/* ===== 过滤与选择 ===== */
function isAccepted(s) {
  if (blocked.value.includes(s.name)) return false;
  return industry.value
    ? INDUSTRY_ALLOW.has(s.rawName) || INDUSTRY_ALLOW.has(s.name)
    : !isBasket(s.name);
}
const accepted = computed(() => allSectors.value.filter(isAccepted));

/* 图表篮子:净流入端 TopN + 净流出端 TopN,按 code 去重 */
function pickForChart(sectors) {
  const ok = sectors.filter(isAccepted);
  const seen = new Set();
  return ok.slice(0, topN.value).concat(ok.slice(-topN.value)).filter((item) => {
    if (seen.has(item.code)) return false;
    seen.add(item.code);
    return true;
  });
}

/* ===== 概览指标 ===== */
const topIn = computed(() => accepted.value.find((s) => s.value >= 0) || null);
const topOut = computed(() => [...accepted.value].reverse().find((s) => s.value < 0) || null);
const breadth = computed(() => {
  const pos = accepted.value.filter((s) => s.value >= 0).length;
  const neg = accepted.value.length - pos;
  return {
    pos, neg,
    pct: accepted.value.length ? Math.round((pos / accepted.value.length) * 100) : 0,
  };
});

/* ===== 近 5 分钟异动 ===== */
const anomalies = computed(() => {
  const prev = prevSnap.value;
  if (!prev) return { hasPrev: false, inflow: [], outflow: [] };
  const changes = [];
  for (const code of Object.keys(snapshot.value)) {
    const cur = snapshot.value[code], old = prev.snapshot[code];
    if (cur && old) changes.push({ name: cur.name, current: cur.value, delta: cur.value - old.value });
  }
  return {
    hasPrev: true,
    inflow: changes.filter((c) => c.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, 4),
    outflow: changes.filter((c) => c.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, 4),
  };
});

/* ===== 排行 ===== */
const inflowList = computed(() => accepted.value.filter((s) => s.value >= 0).slice(0, topN.value));
const outflowList = computed(() => accepted.value.filter((s) => s.value < 0).slice(-topN.value).reverse());
const inflowTotal = computed(() => inflowList.value.reduce((sum, s) => sum + s.value, 0));
const outflowTotal = computed(() => outflowList.value.reduce((sum, s) => sum + s.value, 0));
const barWidth = (list, v) => {
  const maxAbs = Math.max(1e-4, ...list.map((s) => Math.abs(s.value)));
  return Math.max(4, (Math.abs(v) / maxAbs) * 100).toFixed(1) + "%";
};

/* ===== 时钟 / 市场状态 / 倒计时 ===== */
const market = computed(() => marketState(now.value));
const lastSeriesTime = computed(() =>
  mainRows.value.length && mainRows.value[0].series.length
    ? mainRows.value[0].series[mainRows.value[0].series.length - 1][0] : "—");
const watchLastTime = computed(() =>
  watchRows.value.length && watchRows.value[0].series.length
    ? watchRows.value[0].series[watchRows.value[0].series.length - 1][0] : "—");
const nextText = computed(() => {
  if (!autoRefresh.value) return "自动刷新已关闭";
  if (!nextAt.value) return "等待首次同步";
  const sec = Math.max(0, Math.round((nextAt.value - now.value.getTime()) / 1000));
  return Math.floor(sec / 60) + "分" + pad2(sec % 60) + "秒";
});

/* ===== 数据同步 ===== */
async function refresh(manual = false) {
  if (busy.value) return;
  busy.value = true;
  statusText.value = "正在连接东方财富行情";
  const started = Date.now();
  try {
    const sectors = await fetchAllSectors(industry.value);
    if (!sectors.length) throw new Error("接口未返回板块数据");
    allSectors.value = sectors;

    const snap = {};
    sectors.filter(isAccepted).forEach((s) => { snap[s.code] = { name: s.name, value: s.value }; });
    const ts = Date.now();
    // 找约 5 分钟前最近的一次快照做异动对比,再把当前截面入历史
    prevSnap.value = findHistorical(ts);
    snapshot.value = snap;
    history.value = history.value
      .concat({ time: ts, snapshot: snap })
      .filter((it) => it.time >= ts - 90 * 60 * 1000)
      .slice(-12);
    saveHistory();

    const watchSel = sectors.filter((s) => whitelist.value.includes(s.name) && !blocked.value.includes(s.name));
    const [main, watch] = await Promise.all([
      loadSeries(pickForChart(sectors)),
      watchSel.length ? loadSeries(watchSel) : Promise.resolve([]),
    ]);
    mainRows.value = main;
    watchRows.value = watch;

    statusText.value = "接口正常 · " + (Date.now() - started) + " ms";
    lastUpdate.value = timeText(new Date());
    snapshotLabel.value = lastSeriesTime.value === "—" ? "当前截面" : "分钟数据截至 " + lastSeriesTime.value;
    nextAt.value = autoRefresh.value ? Date.now() + intervalSec.value * 1000 : 0;
    if (manual) track("flow_view", (industry.value ? "行业" : "概念") + "板块 · " + sectors.length + " 个");
  } catch (err) {
    statusText.value = "同步失败 · " + (err?.message || "未知错误");
    nextAt.value = autoRefresh.value ? Date.now() + intervalSec.value * 1000 : 0;
    message.error("数据同步失败，请检查网络后重试");
  } finally {
    busy.value = false;
  }
}
function findHistorical(nowTs) {
  const target = nowTs - 5 * 60 * 1000;
  let candidate = null;
  for (const item of history.value) {
    if (item.time <= target && (!candidate || item.time > candidate.time)) candidate = item;
  }
  return candidate;
}

/* ===== 交互 ===== */
function changeMode(toIndustry) {
  if (industry.value === toIndustry) return;
  industry.value = toIndustry;
  history.value = [];
  prevSnap.value = null;
  saveHistory();
  savePrefs();
  refresh();
}
function onTopN(e) { topN.value = Number(e.target.value); savePrefs(); refresh(); }
function onInterval(e) {
  intervalSec.value = Number(e.target.value);
  nextAt.value = autoRefresh.value ? Date.now() + intervalSec.value * 1000 : 0;
  savePrefs();
}
function onAuto(e) {
  autoRefresh.value = e.target.checked;
  nextAt.value = autoRefresh.value ? Date.now() + intervalSec.value * 1000 : 0;
  savePrefs();
}

const exactName = (input) => {
  const target = String(input || "").trim().toLowerCase();
  if (!target) return "";
  const found = allSectors.value.find((s) => s.name.toLowerCase() === target);
  return found ? found.name : "";
};
function addWatch(input) {
  const name = exactName(input);
  if (!name) { message.warning("未找到匹配板块，请从搜索建议中选择"); return; }
  if (whitelist.value.includes(name)) { message.info("该板块已在白名单中"); return; }
  whitelist.value = [...whitelist.value, name];
  savePrefs();
  message.success("已加入白名单：" + name);
  refresh();
}
function toggleWatch(name) {
  whitelist.value = whitelist.value.includes(name)
    ? whitelist.value.filter((n) => n !== name)
    : [...whitelist.value, name];
  savePrefs();
  message.success((whitelist.value.includes(name) ? "已加入白名单：" : "已移出白名单：") + name);
  refresh();
}
function addBlock(input) {
  const name = exactName(input) || String(input || "").trim();
  if (!name) { message.warning("请输入板块名称"); return; }
  if (!blocked.value.includes(name)) blocked.value = [...blocked.value, name];
  savePrefs();
  message.success("已屏蔽：" + name);
  refresh();
}
function unblock(name) {
  blocked.value = blocked.value.filter((n) => n !== name);
  savePrefs();
  message.success("已取消屏蔽：" + name);
  refresh();
}
function clearBlocked() {
  if (!blocked.value.length) return;
  blocked.value = [];
  savePrefs();
  message.success("已清空手动屏蔽");
  refresh();
}

function toggleSettings(show) {
  settingsOpen.value = typeof show === "boolean" ? show : !settingsOpen.value;
}
function onDocClick(e) {
  if (!settingsOpen.value) return;
  if (settingsPanel.value?.contains(e.target) || settingsBtn.value?.contains(e.target)) return;
  settingsOpen.value = false;
}
function onEsc(e) { if (e.key === "Escape") settingsOpen.value = false; }

/* ===== 生命周期 ===== */
let clockTimer = null;
onMounted(() => {
  loadPrefs();
  clockTimer = setInterval(() => {
    now.value = new Date();
    if (autoRefresh.value && nextAt.value && now.value.getTime() >= nextAt.value && !busy.value) refresh();
  }, 1000);
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onEsc);
  refresh();
});
onUnmounted(() => {
  clearInterval(clockTimer);
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onEsc);
});
</script>

<template>
  <div class="flowRoot">
    <!-- ===== 控制条 ===== -->
    <div class="panel ctlBar">
      <div class="ctlGroup">
        <div class="seg">
          <button type="button" :aria-pressed="!industry" @click="changeMode(false)">概念板块</button>
          <button type="button" :aria-pressed="industry" @click="changeMode(true)">行业板块</button>
        </div>
        <label class="inlineField">展示
          <select :value="topN" @change="onTopN">
            <option :value="6">Top 6</option><option :value="8">Top 8</option>
            <option :value="10">Top 10</option><option :value="12">Top 12</option>
          </select>
        </label>
        <label class="inlineField">刷新
          <select :value="intervalSec" @change="onInterval">
            <option :value="300">5 分钟</option><option :value="600">10 分钟</option><option :value="900">15 分钟</option>
          </select>
        </label>
      </div>
      <div class="ctlGroup">
        <span class="marketPill"><i class="dot" :class="market.cls"></i>{{ market.text }}</span>
        <label class="switch">
          <input type="checkbox" :checked="autoRefresh" @change="onAuto">
          <span class="track"></span>自动刷新
        </label>
        <button ref="settingsBtn" type="button" class="ghostBtn" @click="toggleSettings()">过滤设置</button>
        <button type="button" class="pillBtn" :disabled="busy" @click="refresh(true)">
          {{ busy ? "同步中…" : "立即刷新" }}
        </button>
      </div>
    </div>

    <!-- ===== 数据状态条 ===== -->
    <div class="healthStrip">
      <div class="healthItem"><span>DATA STATUS</span><b>{{ statusText }}</b></div>
      <div class="healthItem"><span>LAST UPDATE</span><b>{{ lastUpdate }}</b></div>
      <div class="healthItem"><span>MARKET SNAPSHOT</span><b>{{ snapshotLabel }}</b></div>
      <div class="healthItem"><span>NEXT REFRESH</span><b>{{ nextText }}</b></div>
    </div>

    <!-- ===== 市场概览 KPI ===== -->
    <section class="flowSec">
      <div class="secHead">
        <div>
          <h2 class="secTitle">市场概览</h2>
          <div class="secNote">当前截面的核心资金信号 · 已纳入 {{ accepted.length }} 个板块 · 屏蔽 {{ blocked.length }} 个</div>
        </div>
      </div>
      <div class="kpiGrid">
        <div class="kpiCard kIn">
          <div class="kpiTop"><span>最强主力流入</span><i class="kpiIco">↗</i></div>
          <div class="kpiVal up">{{ topIn ? topIn.name : "—" }}</div>
          <div class="kpiMeta">{{ topIn ? fmtYi(topIn.value, 2) + " · 流入端最强" : "暂无净流入" }}</div>
        </div>
        <div class="kpiCard kOut">
          <div class="kpiTop"><span>最强主力流出</span><i class="kpiIco">↘</i></div>
          <div class="kpiVal down">{{ topOut ? topOut.name : "—" }}</div>
          <div class="kpiMeta">{{ topOut ? fmtYi(topOut.value, 2) + " · 流出端最强" : "暂无净流出" }}</div>
        </div>
        <div class="kpiCard kBreadth">
          <div class="kpiTop"><span>板块资金广度</span><i class="kpiIco">▥</i></div>
          <div class="kpiVal">{{ accepted.length ? breadth.pos + " / " + breadth.neg : "—" }}</div>
          <div class="kpiMeta">净流入占比 {{ breadth.pct }}%</div>
        </div>
        <div class="kpiCard kAnom">
          <div class="kpiTop"><span>近 5 分钟异动</span><i class="kpiIco">⚡</i></div>
          <div class="kpiVal warn">{{ anomalies.hasPrev ? anomalies.inflow.length + anomalies.outflow.length + " 个" : "待积累" }}</div>
          <div class="kpiMeta">{{ anomalies.hasPrev
            ? "流入 " + anomalies.inflow.length + " · 流出 " + anomalies.outflow.length
            : "需积累约 5 分钟快照" }}</div>
        </div>
      </div>
    </section>

    <!-- ===== 资金曲线 + 异动雷达 ===== -->
    <section class="flowSec">
      <div class="secHead">
        <div>
          <h2 class="secTitle">累计分时资金曲线</h2>
          <div class="secNote">暖色代表净流入端，冷色代表净流出端 · 单位：亿元 · 悬停查看时点明细</div>
        </div>
      </div>
      <div class="mainGrid">
        <div class="panel chartPanel">
          <div class="panelHead">
            <div>
              <div class="panelTitle">{{ industry ? "行业" : "概念" }}板块 · 主力净流入</div>
              <div class="panelSub">截至 {{ lastSeriesTime }} · {{ mainRows.length }} 条曲线</div>
            </div>
            <div class="legend">
              <span class="legendItem up"><i></i>流入</span>
              <span class="legendItem down"><i></i>流出</span>
            </div>
          </div>
          <FlowChart :rows="mainRows"
                     empty-text="正在连接行情接口…" />
        </div>
        <div class="panel radarPanel">
          <div class="panelHead">
            <div>
              <div class="panelTitle">资金异动雷达</div>
              <div class="panelSub">当前值相对约 5 分钟前的变化</div>
            </div>
            <span class="marketPill"><i class="dot" :class="{ live: anomalies.hasPrev }"></i>{{ anomalies.hasPrev ? "已更新" : "待积累" }}</span>
          </div>
          <div class="radarBody">
            <div class="radarSummary">
              <div><span>急速流入</span><b class="up">{{ anomalies.inflow.length }}</b></div>
              <div><span>急速流出</span><b class="down">{{ anomalies.outflow.length }}</b></div>
            </div>
            <template v-if="anomalies.hasPrev">
              <div class="anomGroup">
                <div class="anomLabel"><span>加速流入</span><span>Δ净流入</span></div>
                <div v-for="a in anomalies.inflow" :key="a.name" class="anomItem">
                  <div class="anomMain">
                    <div class="anomName">{{ a.name }}</div>
                    <div class="anomSub">当前 {{ fmtYi(a.current, 1) }}</div>
                  </div>
                  <b class="anomDelta up">{{ fmtYi(a.delta, 1) }}</b>
                </div>
                <div v-if="!anomalies.inflow.length" class="emptySmall">暂无变化</div>
              </div>
              <div class="anomGroup">
                <div class="anomLabel"><span>加速流出</span><span>Δ净流入</span></div>
                <div v-for="a in anomalies.outflow" :key="a.name" class="anomItem">
                  <div class="anomMain">
                    <div class="anomName">{{ a.name }}</div>
                    <div class="anomSub">当前 {{ fmtYi(a.current, 1) }}</div>
                  </div>
                  <b class="anomDelta down">{{ fmtYi(a.delta, 1) }}</b>
                </div>
                <div v-if="!anomalies.outflow.length" class="emptySmall">暂无变化</div>
              </div>
            </template>
            <div v-else class="emptySmall">完成两次间隔约 5 分钟的数据同步后，将显示板块资金变化排行。</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 板块资金排行 ===== -->
    <section class="flowSec">
      <div class="secHead">
        <div>
          <h2 class="secTitle">板块资金排行</h2>
          <div class="secNote">{{ industry ? "行业" : "概念" }}板块 · 按当前主力净额排序 · 点击星标加入白名单，点击隐藏剔除干扰板块</div>
        </div>
      </div>
      <div class="rankGrid">
        <div class="panel">
          <div class="panelHead">
            <div><div class="panelTitle">主力净流入</div><div class="panelSub">资金主动承接方向</div></div>
            <b class="up total">{{ inflowList.length ? fmtYi(inflowTotal, 1) : "—" }}</b>
          </div>
          <div class="rankList">
            <div v-for="(s, i) in inflowList" :key="s.code" class="rankRow">
              <span class="rankNo">{{ pad2(i + 1) }}</span>
              <div class="rankName"><b>{{ s.name }}</b><span>{{ s.code }}</span></div>
              <div class="flowBar"><i class="barIn" :style="{ width: barWidth(inflowList, s.value) }"></i></div>
              <b class="rankAmt up">{{ fmtYiShort(s.value) }}</b>
              <div class="rankActs">
                <button type="button" class="miniBtn" :class="{ on: whitelist.includes(s.name) }"
                        :title="whitelist.includes(s.name) ? '移出白名单' : '加入白名单'"
                        @click="toggleWatch(s.name)">★</button>
                <button type="button" class="miniBtn" title="隐藏该板块" @click="addBlock(s.name)">⊘</button>
              </div>
            </div>
            <div v-if="!inflowList.length" class="emptySmall">暂无净流入板块</div>
          </div>
        </div>
        <div class="panel">
          <div class="panelHead">
            <div><div class="panelTitle">主力净流出</div><div class="panelSub">资金主动撤离方向</div></div>
            <b class="down total">{{ outflowList.length ? fmtYi(outflowTotal, 1) : "—" }}</b>
          </div>
          <div class="rankList">
            <div v-for="(s, i) in outflowList" :key="s.code" class="rankRow">
              <span class="rankNo">{{ pad2(i + 1) }}</span>
              <div class="rankName"><b>{{ s.name }}</b><span>{{ s.code }}</span></div>
              <div class="flowBar"><i class="barOut" :style="{ width: barWidth(outflowList, s.value) }"></i></div>
              <b class="rankAmt down">{{ fmtYiShort(s.value) }}</b>
              <div class="rankActs">
                <button type="button" class="miniBtn" :class="{ on: whitelist.includes(s.name) }"
                        :title="whitelist.includes(s.name) ? '移出白名单' : '加入白名单'"
                        @click="toggleWatch(s.name)">★</button>
                <button type="button" class="miniBtn" title="隐藏该板块" @click="addBlock(s.name)">⊘</button>
              </div>
            </div>
            <div v-if="!outflowList.length" class="emptySmall">暂无净流出板块</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 白名单资金追踪 ===== -->
    <section class="flowSec">
      <div class="secHead">
        <div>
          <h2 class="secTitle">白名单资金追踪</h2>
          <div class="secNote">独立跟踪你关心的板块，不受默认篮子过滤影响 · {{ whitelist.length }} 个板块</div>
        </div>
      </div>
      <div class="watchGrid">
        <div class="panel chartPanel">
          <div class="panelHead">
            <div>
              <div class="panelTitle">白名单累计分时</div>
              <div class="panelSub">{{ whitelist.length ? "截至 " + watchLastTime + " · " + watchRows.length + " 条曲线" : "添加板块后自动绘制" }}</div>
            </div>
          </div>
          <FlowChart v-if="whitelist.length" :rows="watchRows" compact
                     empty-text="白名单板块暂无分钟级资金数据" />
          <div v-else class="emptyChart">尚未添加白名单板块&#10;可在右侧搜索，或在排行榜中点击星标</div>
        </div>
        <div class="panel watchSide">
          <div class="panelTitle">管理白名单</div>
          <div class="panelSub">输入东方财富板块名称</div>
          <div class="addRow">
            <input v-model="watchInput" list="flowSectorOptions" placeholder="搜索板块名称"
                   autocomplete="off" @keydown.enter="addWatch(watchInput); watchInput = ''">
            <datalist id="flowSectorOptions">
              <option v-for="s in allSectors" :key="s.code" :value="s.name"></option>
            </datalist>
            <button type="button" class="ghostBtn" @click="addWatch(watchInput); watchInput = ''">添加</button>
          </div>
          <div class="chips">
            <span v-for="name in [...whitelist].sort((a, b) => a.localeCompare(b, 'zh-CN'))" :key="name" class="chip">
              {{ name }}<button type="button" aria-label="移出白名单" @click="toggleWatch(name)">×</button>
            </span>
            <div v-if="!whitelist.length" class="emptySmall emptyLeft">白名单为空</div>
          </div>
          <div class="sideHelp">白名单与过滤设置保存在当前浏览器，不会上传。切换概念/行业后，系统会按当前接口返回的同名板块匹配。</div>
        </div>
      </div>
    </section>

    <!-- ===== 口径说明 ===== -->
    <section class="flowSec">
      <div class="secHead">
        <div>
          <h2 class="secTitle">口径与使用边界</h2>
          <div class="secNote">理解数据，避免把资金估算当成确定结论</div>
        </div>
      </div>
      <div class="methodGrid">
        <div class="panel methodCard">
          <i class="mIdx">01</i><h3>数据来源</h3>
          <p>页面复用东方财富延迟行情接口，获取板块当前主力净额与分钟级累计资金序列。接口属于网页行情能力，不提供稳定性承诺。</p>
        </div>
        <div class="panel methodCard">
          <i class="mIdx">02</i><h3>主力口径</h3>
          <p>“主力净流入”为超大单与大单净额合计，是基于成交拆单规则的估算指标，不等同于真实机构账户的完整买卖台账。</p>
        </div>
        <div class="panel methodCard">
          <i class="mIdx">03</i><h3>决策边界</h3>
          <p>资金流需结合价格趋势、成交量、板块持续性与个股结构交叉确认。本页面仅供研究与盘中观察，不构成投资建议。</p>
        </div>
      </div>
    </section>

    <!-- ===== 过滤设置弹层 ===== -->
    <aside v-if="settingsOpen" ref="settingsPanel" class="settingsPop" aria-label="过滤设置">
      <div class="setHead">
        <div>
          <div class="panelTitle">过滤与显示设置</div>
          <div class="panelSub">剔除不需要关注的统计类板块</div>
        </div>
        <button type="button" class="miniBtn" aria-label="关闭设置" @click="toggleSettings(false)">✕</button>
      </div>
      <div class="setSec">
        <h3>手动屏蔽板块</h3>
        <div class="addRow">
          <input v-model="blockInput" list="flowSectorOptions" placeholder="输入板块名称"
                 autocomplete="off" @keydown.enter="addBlock(blockInput); blockInput = ''">
          <button type="button" class="ghostBtn" @click="addBlock(blockInput); blockInput = ''">屏蔽</button>
        </div>
        <div class="chips">
          <span v-for="name in [...blocked].sort((a, b) => a.localeCompare(b, 'zh-CN'))" :key="name" class="chip">
            {{ name }}<button type="button" aria-label="取消屏蔽" @click="unblock(name)">×</button>
          </span>
          <div v-if="!blocked.length" class="emptySmall emptyLeft">暂无手动屏蔽板块</div>
        </div>
      </div>
      <div class="setSec">
        <h3>默认过滤规则</h3>
        <p class="sideHelp">概念板块默认剔除指数成分、风格、涨跌停、业绩预告、股价区间等统计篮子；行业板块保留接口返回的行业分类。手动屏蔽优先级最高。</p>
      </div>
      <div class="setSec">
        <button type="button" class="ghostBtn" @click="clearBlocked">清空手动屏蔽</button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.flowRoot { position: relative; max-width: 1560px; margin: 0 auto; width: 100%; }
.up { color: var(--up); } .down { color: var(--down); }
.warn { color: var(--hot); }

/* ===== 面板与分区 ===== */
.panel {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 16px 20px;
}
.flowSec { margin-top: 20px; }
.secHead { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 10px; padding: 0 3px; }
.secTitle { margin: 0; font-size: 16px; letter-spacing: -.01em; }
.secNote { margin-top: 4px; color: var(--dim); font-size: 12px; }
.panelHead {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  padding-bottom: 12px; margin-bottom: 4px; border-bottom: 1px solid var(--line);
}
.panelTitle { font-size: 13px; font-weight: 700; }
.panelSub { margin-top: 4px; color: var(--dim); font-size: 11px; }

/* ===== 控制条 ===== */
.ctlBar { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; padding: 12px 16px; }
.ctlGroup { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.seg { display: inline-flex; padding: 3px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel-2); }
.seg button {
  min-height: 30px; padding: 0 14px; border: 0; border-radius: 8px; background: transparent;
  color: var(--dim); font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: color .15s, background .15s;
}
.seg button[aria-pressed="true"] { color: var(--txt); background: var(--panel); box-shadow: 0 2px 8px rgba(0, 0, 0, .18); }
.inlineField { display: flex; align-items: center; gap: 7px; color: var(--dim); font-size: 12px; }
.inlineField select, .addRow input {
  min-height: 32px; border: 1px solid var(--line); border-radius: 8px;
  background: var(--panel-2); color: var(--txt); padding: 0 10px;
  font-size: 13px; font-family: inherit; outline: none;
}
.inlineField select:focus, .addRow input:focus { border-color: var(--accent); }
.marketPill {
  display: inline-flex; align-items: center; gap: 7px;
  min-height: 30px; padding: 0 11px;
  border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel-2); color: var(--dim); font-size: 12px; white-space: nowrap;
}
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--dim); }
.dot.live { background: var(--down); box-shadow: 0 0 0 4px rgba(74, 222, 128, .12); }
.dot.pause { background: var(--hot); }
.switch { display: inline-flex; align-items: center; gap: 8px; color: var(--dim); font-size: 12px; cursor: pointer; }
.switch input { position: absolute; opacity: 0; pointer-events: none; }
.switch .track {
  width: 34px; height: 20px; position: relative; flex: none;
  border: 1px solid var(--line-strong); border-radius: 999px; background: var(--panel-2);
  transition: background .18s;
}
.switch .track::after {
  content: ""; position: absolute; top: 3px; left: 3px; width: 12px; height: 12px;
  border-radius: 50%; background: var(--dim); transition: transform .18s, background .18s;
}
.switch input:checked + .track { background: var(--accent-dim); border-color: var(--accent); }
.switch input:checked + .track::after { transform: translateX(14px); background: var(--accent); }
.ghostBtn {
  min-height: 32px; padding: 0 14px; border: 1px solid var(--line); border-radius: 8px;
  background: var(--panel-2); color: var(--dim); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: all .15s;
}
.ghostBtn:hover { color: var(--txt); border-color: var(--line-strong); }
.pillBtn {
  min-height: 34px; padding: 0 18px; border: none; border-radius: 999px;
  background: var(--btn-bg); color: var(--btn-txt); font-size: 13px; font-weight: 600;
  font-family: inherit; cursor: pointer; transition: opacity .15s;
}
.pillBtn:hover { opacity: .88; }
.pillBtn:disabled { background: var(--btn-disabled); color: var(--dim); cursor: not-allowed; }

/* ===== 数据状态条 ===== */
.healthStrip {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px;
  margin-top: 12px; overflow: hidden;
  border: 1px solid var(--line); border-radius: 12px; background: var(--line);
}
.healthItem { min-width: 0; padding: 10px 14px; background: var(--panel); }
.healthItem span { color: var(--dim); font-size: 10px; letter-spacing: .05em; }
.healthItem b {
  display: block; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--txt); font-size: 12px; font-weight: 500; font-family: var(--mono);
}

/* ===== KPI ===== */
.kpiGrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.kpiCard {
  position: relative; overflow: hidden; min-height: 128px;
  padding: 16px 18px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel);
}
.kpiTop { display: flex; align-items: center; justify-content: space-between; color: var(--dim); font-size: 11px; }
.kpiIco {
  font-style: normal; width: 28px; height: 28px; display: grid; place-items: center;
  border-radius: 9px; font-size: 14px;
}
.kIn .kpiIco { color: var(--up); background: color-mix(in srgb, var(--up) 12%, transparent); }
.kOut .kpiIco { color: var(--down); background: color-mix(in srgb, var(--down) 12%, transparent); }
.kBreadth .kpiIco { color: var(--accent); background: var(--accent-dim); }
.kAnom .kpiIco { color: var(--hot); background: color-mix(in srgb, var(--hot) 12%, transparent); }
.kpiVal {
  margin-top: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: clamp(18px, 1.8vw, 24px); font-weight: 700; letter-spacing: -.02em;
}
.kpiMeta { margin-top: 6px; color: var(--dim); font-size: 11px; }

/* ===== 主图区 ===== */
.mainGrid { display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(290px, .75fr); gap: 12px; }
.chartPanel { min-width: 0; }
.legend { display: flex; gap: 12px; color: var(--dim); font-size: 10px; }
.legendItem { display: inline-flex; align-items: center; gap: 6px; }
.legendItem i { width: 16px; height: 2px; border-radius: 2px; background: currentColor; }
.radarBody { padding: 4px 2px 0; }
.radarSummary { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 10px 0; }
.radarSummary > div { padding: 10px; border-radius: 10px; background: var(--panel-2); }
.radarSummary span { display: block; color: var(--dim); font-size: 10px; }
.radarSummary b { display: block; margin-top: 4px; font-size: 16px; }
.anomGroup { margin-top: 8px; }
.anomLabel { display: flex; justify-content: space-between; padding: 0 2px 6px; color: var(--dim); font-size: 10px; }
.anomItem { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 2px; border-top: 1px solid var(--line); }
.anomMain { min-width: 0; }
.anomName { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.anomSub { margin-top: 2px; color: var(--dim); font-size: 10px; font-family: var(--mono); }
.anomDelta { font-size: 12px; font-weight: 700; font-family: var(--mono); white-space: nowrap; }
.emptySmall { padding: 24px 8px; color: var(--dim); font-size: 11px; text-align: center; line-height: 1.7; }
.emptyLeft { text-align: left; padding: 10px 0; }
.emptyChart {
  min-height: 320px; display: grid; place-items: center;
  color: var(--dim); text-align: center; line-height: 1.7; font-size: 12px; white-space: pre-line;
}

/* ===== 排行 ===== */
.rankGrid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.total { font-size: 14px; font-family: var(--mono); }
.rankList { padding-top: 2px; }
.rankRow {
  display: grid; grid-template-columns: 26px minmax(100px, 1.1fr) minmax(80px, .8fr) 76px 56px;
  gap: 10px; align-items: center; min-height: 46px; border-top: 1px solid var(--line);
}
.rankRow:first-child { border-top: 0; }
.rankNo { color: var(--dim); font-size: 10px; font-family: var(--mono); }
.rankName { min-width: 0; }
.rankName b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
.rankName span { display: block; margin-top: 2px; color: var(--dim); font-size: 10px; font-family: var(--mono); }
.flowBar { height: 5px; overflow: hidden; border-radius: 999px; background: var(--panel-2); }
.flowBar i { display: block; height: 100%; border-radius: inherit; }
.barIn { background: var(--up); }
.barOut { background: var(--down); }
.rankAmt { text-align: right; font-size: 11px; font-weight: 700; font-family: var(--mono); }
.rankActs { display: flex; justify-content: flex-end; gap: 4px; }
.miniBtn {
  width: 25px; height: 25px; display: grid; place-items: center;
  border: 1px solid var(--line); border-radius: 7px; background: var(--panel-2);
  color: var(--dim); font-size: 12px; line-height: 1; cursor: pointer; transition: all .15s;
}
.miniBtn:hover { color: var(--txt); border-color: var(--line-strong); }
.miniBtn.on { color: #f5a623; border-color: rgba(245, 166, 35, .4); background: rgba(245, 166, 35, .1); }

/* ===== 白名单 ===== */
.watchGrid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, .7fr); gap: 12px; }
.watchSide .panelSub { margin-bottom: 12px; }
.addRow { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.addRow input { width: 100%; }
.chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  min-height: 28px; padding: 0 8px 0 10px;
  border: 1px solid var(--line); border-radius: 999px;
  background: var(--panel-2); color: var(--dim); font-size: 11px;
}
.chip button { border: 0; background: none; color: var(--dim); cursor: pointer; padding: 2px; font-size: 13px; line-height: 1; }
.chip button:hover { color: var(--up); }
.sideHelp { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); color: var(--dim); font-size: 10px; line-height: 1.7; }

/* ===== 口径说明 ===== */
.methodGrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.methodCard .mIdx {
  font-style: normal; width: 27px; height: 27px; display: grid; place-items: center;
  border-radius: 8px; color: var(--accent); background: var(--accent-dim);
  font-size: 10px; font-weight: 800; font-family: var(--mono);
}
.methodCard h3 { margin: 12px 0 6px; font-size: 12px; }
.methodCard p { margin: 0; color: var(--dim); font-size: 11px; line-height: 1.75; }

/* ===== 设置弹层 ===== */
.settingsPop {
  position: fixed; z-index: 80; top: 76px; right: 20px;
  width: min(390px, calc(100vw - 28px)); max-height: calc(100vh - 100px); overflow: auto;
  padding: 16px; border: 1px solid var(--line-strong); border-radius: 12px;
  background: var(--panel); box-shadow: 0 24px 60px rgba(0, 0, 0, .3);
}
.setHead { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.setSec { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); }
.setSec h3 { margin: 0 0 9px; font-size: 12px; }
.setSec .sideHelp { margin-top: 0; padding-top: 0; border-top: 0; }

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .mainGrid, .watchGrid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .kpiGrid { grid-template-columns: 1fr 1fr; }
  .rankGrid, .methodGrid { grid-template-columns: 1fr; }
  .healthStrip { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 640px) {
  .ctlBar { align-items: stretch; }
  .ctlGroup { width: 100%; }
  .ctlGroup:last-child { justify-content: space-between; }
  .seg { flex: 1; } .seg button { flex: 1; }
  .kpiGrid { grid-template-columns: 1fr; }
  .healthStrip { grid-template-columns: 1fr; }
  .rankRow { grid-template-columns: 24px minmax(90px, 1fr) 64px 52px; }
  .rankRow .flowBar { display: none; }
  .settingsPop { top: 68px; right: 10px; }
}
</style>
