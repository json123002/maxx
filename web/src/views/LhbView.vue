<script setup>
/* ===== 龙虎榜:每日榜单 + 营业部席位画像 =====
   对标业绩顶级产品(同花顺/东方财富/开盘啦):
   1. 每日榜单:
      - 英雄区:日期步进选择 + 全天席位买入/卖出/游资总览卡片
      - 游资动向看板:网传知名游资(章盟主/作手新一/呼家楼等)当日买卖净额与重仓个股,点名直达席位画像
      - 交互工具条:个股搜索 + 标签筛选(全部/净买入/净卖出/游资出击/机构重仓) + 表头多维排序
      - 个股上榜表:同股多原因智能归并、净买额背景量级底纹条、席位徽标(游资名号/机构数/北向数)
      - 买五卖五深度展开:买卖双栏明细对齐、买五/卖五合计、买卖净三列对照、点席位出席位画像
   2. 席位画像榜:
      - 标签筛选(游资/机构/北向/自营) + 关键词即时搜索
      - 核心指标:上榜频次、历史胜率(次日收涨率)、次日开盘溢价、次日收盘涨幅、次日最高溢价、偏好个股
   3. 席位画像弹窗:
      - 营业部全称 + 游资别名(管理员可实时在线维护/更正)
      - 偏好个股与联动协同席位(支持一键穿透查看协同席位画像)
      - 近 20 次出场战绩明细与次日溢价追踪
*/
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { track } from "../api/client";
import { authState } from "../stores/auth";
import { cls, fmtN } from "../utils/format";
import {
  fetchLhbDates, fetchLhbDaily, fetchLhbStockSeats, fetchLhbSeats, fetchLhbSeat,
  setLhbFamous, delLhbFamous,
} from "../lhb/lhb-data";

const tab = ref("daily");   // daily | seats
const isAdmin = computed(() => authState.user?.role === "admin");

/* ---------- 金额高精度格式化(对标顶级行情软件,规避 0.0 亿) ---------- */
function fmtLhbAmt(v) {
  if (typeof v !== "number" || isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e8) {
    const n = (v / 1e8).toFixed(2);
    return (n.endsWith(".00") ? (v / 1e8).toFixed(0) : n.endsWith("0") ? (v / 1e8).toFixed(1) : n) + " 亿";
  }
  if (abs >= 1e4) {
    const wan = (v / 1e4).toFixed(0);
    return Number(wan).toLocaleString("zh-CN") + " 万";
  }
  return Number(v.toFixed(0)).toLocaleString("zh-CN") + " 元";
}

/* ---------- 席位标签 ---------- */
const TAG_CLS = {
  "游资": "tgHot",
  "机构": "tgInst",
  "北向": "tgNorth",
  "拉萨": "tgLhasa",
  "自营": "tgProp",
};
const tagCls = (t) => TAG_CLS[t?.tag] || "tgProp";
const tagText = (t) => {
  if (!t) return "";
  if (t.tag === "拉萨") return "拉萨天团";
  return t.alias ? `${t.tag}·${t.alias}` : t.tag;
};
const tagTitle = (t) => {
  if (t?.tag === "拉萨") return "东方财富拉萨席位(散户大本营)";
  if (t?.src === "网传") return "网传知名游资席位(仅供参考)";
  return "按席位名称推导";
};

/* 行级席位徽标:游资别名优先,其余按 机构/北向/拉萨/自营 计数 */
function seatBadges(tags, side) {
  if (!tags) return [];
  const out = [];
  const aliases = side === "buy" ? tags.buy_aliases : tags.sell_aliases;
  for (const a of aliases || []) out.push({ text: a, cls: "tgHot" });
  const counts = (side === "buy" ? tags.buy : tags.sell) || {};
  for (const t of ["机构", "北向", "拉萨", "自营"]) {
    if (counts[t]) {
      const text = t === "拉萨"
        ? (counts[t] > 1 ? `拉萨天团×${counts[t]}` : "拉萨天团")
        : `${t}×${counts[t]}`;
      out.push({ text, cls: TAG_CLS[t] });
    }
  }
  return out;
}

/* ---------- 每日榜单 ---------- */
const dates = ref([]);
const date = ref("");
const rows = ref([]);
const summary = ref(null);
const flow = ref([]);          // 当日游资动向
const loading = ref(false);
const expanded = ref("");          // 展开的 code(同股多原因已合并,一股一行)
const seatDetail = ref(null);      // { buy, sell } | null
const seatLoading = ref(false);

const dailyKw = ref("");
const dailyFilter = ref("all");    // all | buy | sell | hot | inst
const dailySortCol = ref("net_amt");
const dailySortDir = ref(-1);      // -1 降序, 1 升序

const DAILY_FILTERS = [
  { k: "all", name: "全部" },
  { k: "buy", name: "净买入" },
  { k: "sell", name: "净卖出" },
  { k: "hot", name: "游资出击" },
  { k: "inst", name: "机构重仓" },
  { k: "lhasa", name: "拉萨天团" },
];

const WD = ["日", "一", "二", "三", "四", "五", "六"];
const weekday = computed(() => (date.value ? "周" + WD[new Date(date.value + "T00:00:00").getDay()] : ""));
const maxAbsNet = computed(() =>
  rows.value.reduce((m, r) => Math.max(m, Math.abs(r.net_amt || 0)), 0) || 1);

/* 游资净买合计(当日榜上网传游资席位的净额总和) */
const flowNet = computed(() => flow.value.reduce((s, f) => s + (f.net || 0), 0));

/* 展开行买五/卖五合计 */
const seatBuySum = computed(() =>
  seatDetail.value?.buy?.reduce((s, x) => s + (x.buy || 0), 0) || 0);
const seatSellSum = computed(() =>
  seatDetail.value?.sell?.reduce((s, x) => s + (x.sell || 0), 0) || 0);

/* 前端实时过滤与多维排序 */
const displayRows = computed(() => {
  let list = rows.value;
  const kw = dailyKw.value.trim().toLowerCase();
  if (kw) {
    list = list.filter((r) =>
      (r.code && r.code.includes(kw)) ||
      (r.name && r.name.toLowerCase().includes(kw))
    );
  }
  if (dailyFilter.value === "buy") {
    list = list.filter((r) => (r.net_amt || 0) > 0);
  } else if (dailyFilter.value === "sell") {
    list = list.filter((r) => (r.net_amt || 0) < 0);
  } else if (dailyFilter.value === "hot") {
    list = list.filter((r) =>
      r.seat_tags?.buy_aliases?.length || r.seat_tags?.sell_aliases?.length
    );
  } else if (dailyFilter.value === "inst") {
    list = list.filter((r) =>
      r.seat_tags?.buy?.["机构"] || r.seat_tags?.sell?.["机构"]
    );
  } else if (dailyFilter.value === "lhasa") {
    list = list.filter((r) =>
      r.seat_tags?.buy?.["拉萨"] || r.seat_tags?.sell?.["拉萨"]
    );
  }

  const col = dailySortCol.value;
  const dir = dailySortDir.value;
  return [...list].sort((a, b) => {
    let va = a[col] ?? 0;
    let vb = b[col] ?? 0;
    if (col === "net_amt" && dir === -1) {
      // 净买额默认按绝对值降序
      return Math.abs(vb) - Math.abs(va);
    }
    return (va - vb) * dir;
  });
});

function toggleDailySort(col) {
  if (dailySortCol.value === col) {
    dailySortDir.value = dailySortDir.value === -1 ? 1 : -1;
  } else {
    dailySortCol.value = col;
    dailySortDir.value = -1;
  }
}

async function loadDates() {
  try {
    const d = await fetchLhbDates();
    dates.value = d.dates;
    if (d.dates.length && !date.value) {
      date.value = d.dates[0];
      loadDaily();
    }
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  }
}

async function loadDaily() {
  if (!date.value) return;
  loading.value = true;
  expanded.value = "";
  seatDetail.value = null;
  try {
    const d = await fetchLhbDaily(date.value);
    rows.value = d.rows;
    summary.value = d.summary;
    flow.value = d.famous_flow || [];
    track("lhb_view", date.value + " → " + d.total + " 条");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function stepDay(dir) {
  const i = dates.value.indexOf(date.value) - dir;   // dates 新→旧,dir=1 为后一日(更新)
  if (i >= 0 && i < dates.value.length) {
    date.value = dates.value[i];
    loadDaily();
  }
}

async function toggleRow(r) {
  if (expanded.value === r.code) { expanded.value = ""; return; }
  expanded.value = r.code;
  seatDetail.value = null;
  seatLoading.value = true;
  try {
    seatDetail.value = await fetchLhbStockSeats(r.code, date.value);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "席位加载失败");
  } finally {
    seatLoading.value = false;
  }
}

/* ---------- 席位榜 ---------- */
const seatKw = ref("");
const seatSort = ref("win_rate");
const seatTagFilter = ref("");     // "" | 游资 | 机构 | 北向 | 自营
const seatRows = ref([]);
const seatsLoading = ref(false);
const SORTS = [
  { k: "win_rate", name: "胜率" },
  { k: "apps", name: "上榜次数" },
  { k: "net", name: "累计净买" },
];
const TAG_FILTERS = [
  { k: "", name: "全部" },
  { k: "游资", name: "游资" },
  { k: "机构", name: "机构" },
  { k: "北向", name: "北向" },
  { k: "拉萨", name: "拉萨天团" },
  { k: "自营", name: "自营" },
];
const seatRowsFiltered = computed(() =>
  !seatTagFilter.value
    ? seatRows.value
    : seatRows.value.filter((s) => s.seat_tag?.tag === seatTagFilter.value));

let kwTimer = null;
function onSeatKw() {
  clearTimeout(kwTimer);
  kwTimer = setTimeout(loadSeats, 300);
}

async function loadSeats() {
  seatsLoading.value = true;
  try {
    const d = await fetchLhbSeats({ kw: seatKw.value.trim(), sort: seatSort.value });
    seatRows.value = d.rows;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    seatsLoading.value = false;
  }
}

/* ---------- 席位画像弹窗 ---------- */
const profile = ref(null);   // { stat, recent }
const profileLoading = ref(false);
const aliasInput = ref("");
const aliasEditing = ref(false);
const aliasSaving = ref(false);

async function openProfile(name) {
  if (!name) return;
  profileLoading.value = true;
  profile.value = null;
  aliasEditing.value = false;
  aliasInput.value = "";
  try {
    profile.value = await fetchLhbSeat(name);
    aliasInput.value = profile.value.stat.seat_tag?.alias || "";
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "画像加载失败");
  } finally {
    profileLoading.value = false;
  }
}
function closeProfile() { profile.value = null; profileLoading.value = false; }

async function saveAlias() {
  const name = profile.value?.stat.dept_name;
  const alias = aliasInput.value.trim();
  if (!name || !alias) return;
  aliasSaving.value = true;
  try {
    await setLhbFamous(name, alias);
    profile.value.stat.seat_tag = { tag: "游资", alias, src: "网传" };
    aliasEditing.value = false;
    message.success(`已标注:${name} → ${alias}(网传)`);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "标注失败");
  } finally {
    aliasSaving.value = false;
  }
}

async function removeAlias() {
  const name = profile.value?.stat.dept_name;
  if (!name) return;
  aliasSaving.value = true;
  try {
    await delLhbFamous(name);
    profile.value.stat.seat_tag = null;
    aliasInput.value = "";
    aliasEditing.value = false;
    message.success("已移除游资标注");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  } finally {
    aliasSaving.value = false;
  }
}

const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const pctCls = (v) => (v == null ? "" : cls(v * 100));
const winCls = (w) => (w == null ? "" : w >= 0.5 ? "up" : "down");

const profileShown = computed(() => profileLoading.value || profile.value);

function switchTab(t) {
  tab.value = t;
  if (t === "seats" && !seatRows.value.length) loadSeats();
}

onMounted(loadDates);
</script>

<template>
  <div class="lhbWrap">
    <!-- ===== 页头:标题 + 口径说明 + 切换 ===== -->
    <div class="secHead">
      <span class="secName">龙虎榜</span>
      <span class="secNote">每日收盘后自动采集 · 胜率按次日收盘口径回填 · 「游资」标签为网传知名席位仅供参考</span>
      <span class="barSpacer"></span>
      <div class="tabBtns">
        <button :class="{ on: tab === 'daily' }" @click="switchTab('daily')">每日榜单</button>
        <button :class="{ on: tab === 'seats' }" @click="switchTab('seats')">席位画像</button>
      </div>
    </div>

    <!-- ===== 每日榜单 ===== -->
    <template v-if="tab === 'daily'">
      <!-- 汇总英雄区:日期步进 + 指标块 -->
      <div class="hero">
        <div class="dayNav">
          <button class="dayBtn" @click="stepDay(-1)" :disabled="!dates.length" title="前一交易日">‹</button>
          <div class="dayCur">
            <b>{{ date || "——" }}</b>
            <span v-if="weekday" class="wd">{{ weekday }}</span>
          </div>
          <button class="dayBtn" @click="stepDay(1)" :disabled="!dates.length" title="后一交易日">›</button>
          <select v-model="date" class="dateSel" @change="loadDaily" :disabled="!dates.length">
            <option v-if="!dates.length" value="">暂无数据(首日 18:05 后自动采集)</option>
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>
        <div v-if="summary" class="statTiles">
          <div class="tile">
            <span class="tLabel">上榜个股</span>
            <b class="tVal">{{ rows.length }}</b>
          </div>
          <div class="tile">
            <span class="tLabel">席位买入合计</span>
            <b class="tVal up">{{ fmtLhbAmt(summary.buy) }}</b>
          </div>
          <div class="tile">
            <span class="tLabel">席位卖出合计</span>
            <b class="tVal down">{{ fmtLhbAmt(summary.sell) }}</b>
          </div>
          <div v-if="flow.length" class="tile">
            <span class="tLabel">游资动向席位</span>
            <b class="tVal tgHotTxt">{{ flow.length }} 家</b>
          </div>
          <div v-if="flow.length" class="tile">
            <span class="tLabel">游资净额</span>
            <b class="tVal" :class="cls(flowNet)">{{ flowNet > 0 ? "+" : "" }}{{ fmtLhbAmt(flowNet) }}</b>
          </div>
        </div>
      </div>



      <!-- 每日榜单工具条:快速搜索 + 分类筛选 + 数量统计 -->
      <div class="toolBar">
        <input v-model="dailyKw" class="kwIn" placeholder="过滤代码 / 名称" />
        <div class="tabBtns sm">
          <button v-for="flt in DAILY_FILTERS" :key="flt.k"
                  :class="{ on: dailyFilter === flt.k }"
                  @click="dailyFilter = flt.k">{{ flt.name }}</button>
        </div>
        <span class="barSpacer"></span>
        <span class="cnt">
          显示 {{ displayRows.length }} / {{ rows.length }} 只个股 · 点击行展开席位明细
        </span>
      </div>

      <!-- 表格区 -->
      <div class="tblWrap" :class="{ loading }">
        <table v-if="displayRows.length">
          <thead>
            <tr>
              <th class="l">#</th>
              <th class="l">股票</th>
              <th class="l">上榜原因</th>
              <th>收盘价</th>
              <th class="sortTh" @click="toggleDailySort('change_rate')">
                涨跌幅 % <span class="sortIco">{{ dailySortCol === 'change_rate' ? (dailySortDir === -1 ? '▼' : '▲') : '' }}</span>
              </th>
              <th class="l sortTh" @click="toggleDailySort('net_amt')">
                净买额 <span class="sortIco">{{ dailySortCol === 'net_amt' ? (dailySortDir === -1 ? '▼' : '▲') : '' }}</span>
              </th>
              <th class="l">买方核心席位</th>
              <th class="sortTh" @click="toggleDailySort('buy_amt')">
                买入额 <span class="sortIco">{{ dailySortCol === 'buy_amt' ? (dailySortDir === -1 ? '▼' : '▲') : '' }}</span>
              </th>
              <th>卖出额</th>
              <th class="sortTh" @click="toggleDailySort('turnover_rate')">
                换手 % <span class="sortIco">{{ dailySortCol === 'turnover_rate' ? (dailySortDir === -1 ? '▼' : '▲') : '' }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(r, i) in displayRows" :key="r.code">
              <tr class="clk" :class="{ hot: r.seat_tags?.buy_aliases?.length, exp: expanded === r.code }"
                  @click="toggleRow(r)">
                <td class="l rank" :class="{ top: i < 3 }">{{ i + 1 }}</td>
                <td class="l name">
                  <router-link class="nameLink" :to="'/stock/' + r.code" @click.stop>{{ r.name }}</router-link>
                  <span class="codeTxt">{{ r.code }}</span>
                </td>
                <td class="l">
                  <div class="reasons">
                    <span v-for="ex in r.explains" :key="ex" class="reason">{{ ex }}</span>
                  </div>
                </td>
                <td>{{ fmtN(r.close_price) }}</td>
                <td :class="cls(r.change_rate)">{{ fmtN(r.change_rate) }}%</td>
                <td class="l netCell">
                  <i class="netBar" :class="r.net_amt >= 0 ? 'upBg' : 'downBg'"
                     :style="{ width: Math.min(100, Math.abs(r.net_amt || 0) / maxAbsNet * 100) + '%' }"></i>
                  <b :class="cls(r.net_amt)">{{ (r.net_amt || 0) > 0 ? "+" : "" }}{{ fmtLhbAmt(r.net_amt) }}</b>
                </td>
                <td class="l seatBadges">
                  <em v-for="bd in seatBadges(r.seat_tags, 'buy')" :key="bd.text"
                      class="tag" :class="bd.cls">{{ bd.text }}</em>
                  <span v-if="!seatBadges(r.seat_tags, 'buy').length" class="dimTxt">—</span>
                </td>
                <td class="dimN">{{ fmtLhbAmt(r.buy_amt) }}</td>
                <td class="dimN">{{ fmtLhbAmt(r.sell_amt) }}</td>
                <td>{{ fmtN(r.turnover_rate) }}%</td>
              </tr>
              <!-- 展开席位明细(买五 / 卖五双栏对比) -->
              <tr v-if="expanded === r.code" class="expRow">
                <td colspan="10">
                  <div v-if="seatLoading" class="expLoading">席位明细加载中…</div>
                  <div v-else-if="seatDetail" class="seatCols">
                    <!-- 买入前五 -->
                    <div class="seatCol">
                      <div class="seatColHead">
                        <span class="seatColT up">买入席位 (买五)</span>
                        <span class="seatTotal">合计: <b class="up">{{ fmtLhbAmt(seatBuySum) }}</b></span>
                      </div>
                      <table class="subTbl">
                        <thead>
                          <tr>
                            <th class="l">席位名称</th>
                            <th>买入</th>
                            <th>卖出</th>
                            <th>净买</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="s in seatDetail.buy" :key="s.id">
                            <td class="l seatCell">
                              <span class="seatName clk" @click="openProfile(s.dept_name)">{{ s.dept_name }}</span>
                              <em v-if="s.seat_tag" class="tag" :class="tagCls(s.seat_tag)" :title="tagTitle(s.seat_tag)">
                                {{ tagText(s.seat_tag) }}
                              </em>
                            </td>
                            <td class="up">{{ fmtLhbAmt(s.buy) }}</td>
                            <td class="dimN">{{ fmtLhbAmt(s.sell) }}</td>
                            <td :class="cls(s.net)">{{ (s.net || 0) > 0 ? "+" : "" }}{{ fmtLhbAmt(s.net) }}</td>
                          </tr>
                          <tr v-if="!seatDetail.buy.length">
                            <td colspan="4" class="dimTxt" style="text-align: center; padding: 12px 0;">无买入席位明细</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    <!-- 卖出前五 -->
                    <div class="seatCol">
                      <div class="seatColHead">
                        <span class="seatColT down">卖出席位 (卖五)</span>
                        <span class="seatTotal">合计: <b class="down">{{ fmtLhbAmt(seatSellSum) }}</b></span>
                      </div>
                      <table class="subTbl">
                        <thead>
                          <tr>
                            <th class="l">席位名称</th>
                            <th>买入</th>
                            <th>卖出</th>
                            <th>净买</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="s in seatDetail.sell" :key="s.id">
                            <td class="l seatCell">
                              <span class="seatName clk" @click="openProfile(s.dept_name)">{{ s.dept_name }}</span>
                              <em v-if="s.seat_tag" class="tag" :class="tagCls(s.seat_tag)" :title="tagTitle(s.seat_tag)">
                                {{ tagText(s.seat_tag) }}
                              </em>
                            </td>
                            <td class="dimN">{{ fmtLhbAmt(s.buy) }}</td>
                            <td class="down">{{ fmtLhbAmt(s.sell) }}</td>
                            <td :class="cls(s.net)">{{ (s.net || 0) > 0 ? "+" : "" }}{{ fmtLhbAmt(s.net) }}</td>
                          </tr>
                          <tr v-if="!seatDetail.sell.length">
                            <td colspan="4" class="dimTxt" style="text-align: center; padding: 12px 0;">无卖出席位明细</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ loading ? "加载中…" : rows.length ? "无符合当前筛选条件的股票" : "该交易日没有龙虎榜数据——每日 18:05 后自动采集，周末及非交易日无数据" }}
        </div>
      </div>
    </template>

    <!-- ===== 席位画像榜 ===== -->
    <template v-else>
      <div class="bar">
        <input v-model="seatKw" class="kwIn" placeholder="营业部名称关键词" @input="onSeatKw" />
        <div class="tabBtns sm">
          <button v-for="s in SORTS" :key="s.k" :class="{ on: seatSort === s.k }"
                  @click="seatSort = s.k; loadSeats()">{{ s.name }}</button>
        </div>
        <div class="tabBtns sm">
          <button v-for="t in TAG_FILTERS" :key="t.k" :class="{ on: seatTagFilter === t.k }"
                  @click="seatTagFilter = t.k">{{ t.name }}</button>
        </div>
        <span class="barSpacer"></span>
        <span class="cnt">{{ seatTagFilter ? seatRowsFiltered.length + " / " : "" }}{{ seatRows.length }} 席位 · 胜率=次日收盘收涨概率</span>
      </div>

      <div class="tblWrap" :class="{ loading: seatsLoading }">
        <table v-if="seatRowsFiltered.length">
          <thead>
            <tr>
              <th class="l">营业部席位</th><th>上榜次数</th><th>胜率</th>
              <th>次日开盘溢价</th><th>次日收盘涨幅</th><th>次日最高溢价</th>
              <th>累计净买</th><th class="l">偏好个股</th><th>最近上榜</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in seatRowsFiltered" :key="s.dept_name" class="clk" @click="openProfile(s.dept_name)">
              <td class="l name">
                {{ s.dept_name }}
                <em v-if="s.seat_tag" class="tag" :class="tagCls(s.seat_tag)" :title="tagTitle(s.seat_tag)">
                  {{ tagText(s.seat_tag) }}
                </em>
              </td>
              <td>{{ s.appearances }}</td>
              <td><b :class="winCls(s.win_rate)">{{ s.win_rate == null ? "—" : (s.win_rate * 100).toFixed(0) + "%" }}</b></td>
              <td :class="pctCls(s.avg_open_premium)">{{ pct(s.avg_open_premium) }}</td>
              <td :class="pctCls(s.avg_close_pct)">{{ pct(s.avg_close_pct) }}</td>
              <td :class="pctCls(s.avg_max_premium)">{{ pct(s.avg_max_premium) }}</td>
              <td :class="cls(s.total_net)">{{ fmtLhbAmt(s.total_net) }}</td>
              <td class="l favCell">
                <router-link v-for="t in (s.top_stocks || []).slice(0, 2)" :key="t.code"
                             class="favLink" :to="'/stock/' + t.code" @click.stop>
                  {{ t.name }}×{{ t.n }}
                </router-link>
                <span v-if="!(s.top_stocks || []).length" class="dimTxt">—</span>
              </td>
              <td class="dimTxt">{{ s.last_date }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ seatsLoading ? "加载中…" : seatTagFilter ? "该标签下暂无席位画像" : "暂无席位画像——需先积累上榜数据,次日收盘后回填胜率" }}
        </div>
      </div>
    </template>

    <!-- ===== 席位画像弹窗 ===== -->
    <div v-if="profileShown" class="pMask" @click.self="closeProfile">
      <div class="pBox">
        <div v-if="profileLoading" class="expLoading">画像加载中…</div>
        <template v-else-if="profile">
          <div class="pHead">
            <div class="pTitle">
              <b>{{ profile.stat.dept_name }}</b>
              <em v-if="profile.stat.seat_tag" class="tag lg" :class="tagCls(profile.stat.seat_tag)"
                  :title="tagTitle(profile.stat.seat_tag)">
                {{ tagText(profile.stat.seat_tag) }}
              </em>
            </div>
            <button class="pClose" @click="closeProfile">×</button>
          </div>

          <!-- 管理员:网传游资标注维护 -->
          <div v-if="isAdmin" class="aliasBar">
            <template v-if="!aliasEditing">
              <button class="ghostBtn" @click="aliasEditing = true">
                {{ profile.stat.seat_tag?.src === "网传" ? "修改游资标注" : "标注游资(网传)" }}
              </button>
              <button v-if="profile.stat.seat_tag?.src === '网传'" class="ghostBtn danger"
                      :disabled="aliasSaving" @click="removeAlias">移除标注</button>
            </template>
            <template v-else>
              <input v-model="aliasInput" class="kwIn sm" placeholder="游资名号,如:炒股养家"
                     maxlength="32" @keyup.enter="saveAlias" />
              <button class="ghostBtn" :disabled="aliasSaving || !aliasInput.trim()" @click="saveAlias">
                {{ aliasSaving ? "保存中…" : "保存" }}
              </button>
              <button class="ghostBtn" @click="aliasEditing = false">取消</button>
            </template>
          </div>

          <div class="pStats">
            <div class="pStat"><span>上榜频次</span><b>{{ profile.stat.appearances }}</b></div>
            <div class="pStat"><span>胜率</span>
              <b :class="winCls(profile.stat.win_rate)">
                {{ profile.stat.win_rate == null ? "—" : (profile.stat.win_rate * 100).toFixed(0) + "%" }}
              </b>
            </div>
            <div class="pStat"><span>次日开盘溢价</span>
              <b :class="pctCls(profile.stat.avg_open_premium)">{{ pct(profile.stat.avg_open_premium) }}</b>
            </div>
            <div class="pStat"><span>次日收盘涨幅</span>
              <b :class="pctCls(profile.stat.avg_close_pct)">{{ pct(profile.stat.avg_close_pct) }}</b>
            </div>
            <div class="pStat"><span>次日最高溢价</span>
              <b :class="pctCls(profile.stat.avg_max_premium)">{{ pct(profile.stat.avg_max_premium) }}</b>
            </div>
            <div class="pStat"><span>累计净买入</span>
              <b :class="cls(profile.stat.total_net)">{{ fmtLhbAmt(profile.stat.total_net) }}</b>
            </div>
          </div>

          <div v-if="profile.stat.top_stocks.length" class="pTags">
            <span>偏好标的:</span>
            <router-link v-for="t in profile.stat.top_stocks" :key="t.code" class="pTag"
                         :to="'/stock/' + t.code">{{ t.name }}×{{ t.n }}</router-link>
          </div>
          <div v-if="profile.stat.co_seats.length" class="pTags">
            <span>协同席位:</span>
            <span v-for="cstat in profile.stat.co_seats" :key="cstat.dept"
                  class="pTag dim clk" :title="'穿透查看 ' + cstat.dept + ' 画像'"
                  @click="openProfile(cstat.dept)">
              {{ cstat.dept }}×{{ cstat.n }}
            </span>
          </div>

          <div class="pSecT">近期上榜明细 (近 20 次)</div>
          <table class="pTbl" v-if="profile.recent.length">
            <thead>
              <tr>
                <th class="l">上榜日期</th>
                <th class="l">股票名称</th>
                <th>方向</th>
                <th>净买额</th>
                <th>次日开盘</th>
                <th>次日收盘</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in profile.recent" :key="i">
                <td class="l dimTxt">{{ r.trade_date }}</td>
                <td class="l">
                  <router-link class="nameLink" :to="'/stock/' + r.code">{{ r.name }}</router-link>
                  <span class="codeTxt">{{ r.code }}</span>
                </td>
                <td :class="r.side === 'B' ? 'up' : 'down'">{{ r.side === 'B' ? "买入" : "卖出" }}</td>
                <td :class="cls(r.net)">{{ (r.net || 0) > 0 ? "+" : "" }}{{ fmtLhbAmt(r.net) }}</td>
                <td :class="r.t1_open == null ? '' : pctCls(r.t1_open / r.t_close - 1)">
                  {{ r.t1_open == null ? "待回填" : pct(r.t1_open / r.t_close - 1) }}</td>
                <td :class="r.t1_close == null ? '' : pctCls(r.t1_close / r.t_close - 1)">
                  {{ r.t1_close == null ? "待回填" : pct(r.t1_close / r.t_close - 1) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lhbWrap { padding: 12px 0 48px; }

.secHead {
  display: flex; align-items: baseline; gap: 12px;
  padding-bottom: 10px; border-bottom: 1px solid var(--line);
}
.secName { font-size: 15px; font-weight: 650; letter-spacing: .04em; }
.secName::before {
  content: ""; display: inline-block; width: 3px; height: 12px; border-radius: 2px;
  background: var(--brand-red); margin-right: 8px; vertical-align: -1px;
}
.secNote { color: var(--dim); font-size: 12px; }
.barSpacer { flex: 1; }

.tabBtns { display: flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 999px; padding: 2px; }
.tabBtns button {
  background: none; border: none; border-radius: 999px; cursor: pointer;
  color: var(--dim); font-size: 12px; font-family: inherit; padding: 4px 14px; transition: all .15s;
}
.tabBtns button.on { color: var(--accent); background: var(--accent-dim); font-weight: 600; }
.tabBtns.sm button { font-size: 11.5px; padding: 2px 10px; }

/* ---- 汇总英雄区 ---- */
.hero { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; margin: 16px 0 12px; }
.dayNav { display: flex; align-items: center; gap: 8px; }
.dayCur { display: flex; align-items: baseline; gap: 8px; min-width: 128px; justify-content: center; }
.dayCur b { font-size: 17px; font-family: var(--mono); letter-spacing: .02em; }
.dayCur .wd { font-size: 12px; color: var(--dim); }
.dayBtn {
  width: 28px; height: 28px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--panel-2); color: var(--dim); font-size: 15px; line-height: 1;
  cursor: pointer; font-family: inherit; transition: color .15s, border-color .15s;
}
.dayBtn:hover:not(:disabled) { color: var(--txt); border-color: var(--line-strong); }
.dayBtn:disabled { opacity: .4; cursor: default; }
.dateSel, .kwIn {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  color: var(--txt); font-size: 12.5px; padding: 5px 10px; font-family: inherit; outline: none;
}
.dateSel:focus, .kwIn:focus { border-color: var(--accent); }
.kwIn.sm { padding: 4px 8px; font-size: 12px; }

.statTiles { display: flex; gap: 28px; flex-wrap: wrap; }
.tile { display: flex; flex-direction: column; gap: 2px; }
.tLabel { font-size: 11.5px; color: var(--dim); letter-spacing: .06em; }
.tVal { font-size: 19px; font-family: var(--mono); font-weight: 650; }
.tgHotTxt { color: #d48806; }


/* ---- 工具条 ---- */
.toolBar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.sortTh { cursor: pointer; }
.sortTh:hover { color: var(--txt); }
.sortIco { font-size: 9px; vertical-align: 1px; color: var(--accent); margin-left: 2px; }

/* ---- 表格 ---- */
.tblWrap { overflow-x: auto; }
.tblWrap.loading { opacity: .55; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: right; color: var(--dim); font-weight: 500; font-size: 11.5px;
  letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line-strong);
  white-space: nowrap; user-select: none;
}
th.l, td.l { text-align: left; }
td { text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--line); font-family: var(--mono); white-space: nowrap; }
td.name { font-family: inherit; }
td.dimN { color: var(--dim); }
tr.clk { cursor: pointer; }
tr:hover td { background: var(--hover); }
tr.exp td { background: var(--hover); }
/* 买方有网传游资参与的个股:左侧金条提示 */
tr.hot td:first-child { box-shadow: inset 3px 0 0 #d48806; }
.rank { color: var(--dim); font-size: 11.5px; }
.rank.top { color: var(--brand-red); font-weight: 700; }
.codeTxt { color: var(--dim); font-size: 11px; margin-left: 6px; font-family: var(--mono); }
.reasons { display: flex; flex-wrap: wrap; gap: 4px; }
.reason {
  font-size: 11.5px; color: var(--dim); background: var(--panel-2);
  border-radius: 4px; padding: 2px 8px; white-space: nowrap;
}
.nameLink { color: var(--txt); text-decoration: none; font-weight: 600; }
.nameLink:hover { color: var(--accent); }
.dimTxt { color: var(--dim); font-family: inherit; }
.up { color: var(--up); }
.down { color: var(--down); }
.empty { padding: 48px 0; text-align: center; color: var(--dim); font-size: 13px; line-height: 1.9; }

/* 净买额量级条:数值背后一条淡淡的分红/绿底色条,一眼看出相对量级 */
.netCell { position: relative; min-width: 120px; }
.netCell b { position: relative; z-index: 1; }
.netBar {
  position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  height: 18px; border-radius: 4px; opacity: .14; pointer-events: none;
}
.netBar.upBg { background: var(--up); }
.netBar.downBg { background: var(--down); }

/* ---- 席位标签 ---- */
.tag {
  font-style: normal; font-size: 10.5px; border-radius: 4px; padding: 1px 6px;
  margin-left: 6px; vertical-align: 1px; white-space: nowrap; cursor: default;
}
.tag.lg { font-size: 11.5px; padding: 2px 8px; }
.tgHot { color: #d48806; background: rgba(212, 136, 6, .12); }
.tgInst { color: #2f6feb; background: rgba(47, 111, 235, .12); }
.tgNorth { color: #0e9594; background: rgba(14, 149, 148, .12); }
.tgLhasa { color: #722ed1; background: rgba(114, 46, 209, .12); }
.tgProp { color: var(--dim); background: var(--panel-2); }
/* 行级席位徽标:第一个不带左间距 */
.seatBadges .tag:first-child { margin-left: 0; }
.favCell { font-family: inherit; }
.favLink { color: var(--dim); font-size: 11.5px; text-decoration: none; margin-right: 8px; }
.favLink:hover { color: var(--accent); }

/* ---- 展开买五卖五明细 ---- */
.expRow td { background: var(--panel-2) !important; white-space: normal; padding: 12px 14px; }
.expLoading { padding: 12px; color: var(--dim); font-size: 12px; text-align: center; }
.seatCols { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 860px) {
  .seatCols { grid-template-columns: 1fr; }
}
.seatCol {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 14px;
}
.seatColHead { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.seatColT { font-size: 12.5px; font-weight: 650; }
.seatTotal { font-size: 11.5px; color: var(--dim); }
.seatTotal b { font-family: var(--mono); }
.subTbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.subTbl th { padding: 5px 8px; font-size: 11px; border-bottom: 1px solid var(--line); }
.subTbl td { padding: 5px 8px; border-bottom: 1px solid var(--line-dim, rgba(255, 255, 255, .04)); }
.subTbl tr:last-child td { border-bottom: none; }
.seatCell { display: flex; align-items: center; gap: 4px; }
.seatName { font-family: inherit; color: var(--txt); }
.seatName.clk:hover { color: var(--accent); text-decoration: underline; }

/* ---- 席位榜工具条 ---- */
.bar { display: flex; align-items: center; gap: 10px; margin: 14px 0 10px; flex-wrap: wrap; }
.kwIn { width: 180px; }
.cnt { font-size: 12px; color: var(--dim); }

/* ---- 画像弹窗 ---- */
.pMask {
  position: fixed; inset: 0; z-index: 60; background: rgba(0, 0, 0, .45);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.pBox {
  background: var(--panel); border: 1px solid var(--line-strong); border-radius: 12px;
  width: 100%; max-width: 760px; max-height: calc(100vh - 80px); overflow-y: auto; padding: 20px 22px;
}
.pHead { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.pTitle { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pTitle b { font-size: 15px; }
.pClose { background: none; border: none; color: var(--dim); font-size: 20px; cursor: pointer; }
.pClose:hover { color: var(--txt); }

.aliasBar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.ghostBtn {
  background: none; border: 1px solid var(--line); border-radius: 8px;
  color: var(--dim); font-size: 12px; padding: 4px 12px; cursor: pointer; font-family: inherit;
}
.ghostBtn:hover { color: var(--txt); }
.ghostBtn:disabled { opacity: .4; cursor: default; }
.ghostBtn.danger:hover { color: var(--down); border-color: var(--down); }

.pStats { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 14px; background: var(--panel-2); padding: 12px 16px; border-radius: 8px; }
.pStat { display: flex; flex-direction: column; gap: 2px; }
.pStat span { font-size: 11px; color: var(--dim); letter-spacing: .05em; }
.pStat b { font-size: 16px; font-family: var(--mono); font-weight: 650; }
.pTags { font-size: 12px; color: var(--dim); margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.pTag {
  background: var(--accent-dim); color: var(--accent); border-radius: 4px;
  padding: 1px 8px; font-size: 11.5px; text-decoration: none;
}
.pTag.dim { background: var(--panel-2); color: var(--dim); }
.pTag.clk:hover { color: var(--accent); text-decoration: underline; cursor: pointer; }
.pSecT { font-size: 12.5px; font-weight: 600; margin-top: 14px; margin-bottom: 6px; }
.pTbl { margin-top: 4px; }
.pTbl td, .pTbl th { padding: 6px 8px; font-size: 12px; }
</style>
