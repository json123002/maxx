<script setup>
/* ===== 历史榜单回看：每交易日收盘落库的全市场快照 =====
   支持按板块（主板/创业板/科创板等）、股价范围、涨跌幅、换手率全维筛选与全量服务端动态排序。
   点名称进个股详情页。埋点 history_view 记录回看行为。 */
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { api, track } from "../api/client";
import { cls, cmpRows, fmtN, fmtYiT } from "../utils/format";

const dates = ref([]);
const date = ref("");
const market = ref("");
const pmin = ref("");
const pmax = ref("");
const cmin = ref("");
const cmax = ref("");
const tmin = ref("");
const tmax = ref("");
const noST = ref(false);
const kw = ref("");

const rows = ref([]);
const total = ref(0);
const stats = ref(null);
const loading = ref(false);
const sortKey = ref("f8"), sortDir = ref(-1);
const renderCap = ref(200);

const HEAD = [
  { k: "f12", name: "代码", l: true },
  { k: "f14", name: "名称", l: true },
  { k: "market", name: "板块", l: true },
  { k: "f2", name: "收盘价" },
  { k: "f3", name: "涨跌幅 %" },
  { k: "f8", name: "换手率 %" },
  { k: "f100", name: "行业", l: true },
  { k: "f6", name: "成交额" },
  { k: "f20", name: "总市值" },
];

const hasFilters = computed(() =>
  !!(market.value || pmin.value || pmax.value || cmin.value || cmax.value || tmin.value || tmax.value || kw.value.trim() || noST.value)
);

const sorted = computed(() =>
  rows.value.slice().sort(cmpRows(sortKey.value, sortDir.value))
);

const visibleRows = computed(() =>
  sorted.value.slice(0, renderCap.value)
);

function thCls(k) {
  return {
    sorted: k === sortKey.value,
    asc: k === sortKey.value && sortDir.value === 1,
    desc: k === sortKey.value && sortDir.value === -1,
  };
}

function onTh(k) {
  if (sortKey.value === k) {
    sortDir.value *= -1;
  } else {
    sortKey.value = k;
    sortDir.value = (k === "f12" || k === "f14" || k === "f100" || k === "market") ? 1 : -1;
  }
  renderCap.value = 200;
  load();
}

async function loadDates() {
  try {
    const d = await api("/api/quote/history/dates");
    dates.value = d.dates;
    if (d.dates.length && !date.value) {
      date.value = d.dates[0];
      load();
    }
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  }
}

let timer = null;
function onInputDebounce() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    renderCap.value = 200;
    load();
  }, 300);
}

function onSelectChange() {
  renderCap.value = 200;
  load();
}

function resetFilters() {
  market.value = "";
  pmin.value = "";
  pmax.value = "";
  cmin.value = "";
  cmax.value = "";
  tmin.value = "";
  tmax.value = "";
  noST.value = false;
  kw.value = "";
  sortKey.value = "f8";
  sortDir.value = -1;
  renderCap.value = 200;
  load();
}

async function load() {
  if (!date.value) return;
  loading.value = true;
  try {
    const p = new URLSearchParams({
      date: date.value,
      sort_by: sortKey.value,
      order: sortDir.value === 1 ? "asc" : "desc",
      limit: "6000",
    });
    if (kw.value.trim()) p.set("kw", kw.value.trim());
    if (market.value) p.set("market", market.value);
    if (pmin.value !== "" && !isNaN(pmin.value)) p.set("pmin", pmin.value);
    if (pmax.value !== "" && !isNaN(pmax.value)) p.set("pmax", pmax.value);
    if (cmin.value !== "" && !isNaN(cmin.value)) p.set("cmin", cmin.value);
    if (cmax.value !== "" && !isNaN(cmax.value)) p.set("cmax", cmax.value);
    if (tmin.value !== "" && !isNaN(tmin.value)) p.set("tmin", tmin.value);
    if (tmax.value !== "" && !isNaN(tmax.value)) p.set("tmax", tmax.value);
    if (noST.value) p.set("no_st", "1");

    const d = await api("/api/quote/history?" + p);
    rows.value = d.rows;
    total.value = d.total;
    stats.value = d.stats;
    track("history_view", date.value + (kw.value.trim() ? " kw:" + kw.value.trim() : "") + " → " + d.total + " 只");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function mktBadgeCls(m) {
  if (!m) return "";
  if (m.includes("主板")) return "mkt-mb";
  if (m.includes("创业板")) return "mkt-cyb";
  if (m.includes("科创板")) return "mkt-kcb";
  if (m.includes("北交所")) return "mkt-bjs";
  return "";
}

function loadMore() {
  renderCap.value += 300;
}

function showAll() {
  renderCap.value = sorted.value.length;
}

onMounted(loadDates);
</script>

<template>
  <div class="hisWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">历史榜单</span>
        <span class="secNote">每交易日收盘落库 · 支持板块/股价/换手率多维筛选与全量排序</span>
      </div>

      <!-- 筛选栏 -->
      <div class="filterBar">
        <div class="fItem">
          <span class="fLabel">日期</span>
          <select v-model="date" class="sel" @change="onSelectChange" :disabled="!dates.length">
            <option v-if="!dates.length" value="">暂无历史数据</option>
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>

        <div class="fItem">
          <span class="fLabel">板块</span>
          <select v-model="market" class="sel" @change="onSelectChange">
            <option value="">全部板块</option>
            <option value="主板">主板 (沪深)</option>
            <option value="沪主板">沪主板</option>
            <option value="深主板">深主板</option>
            <option value="创业板">创业板</option>
            <option value="科创板">科创板</option>
            <option value="北交所">北交所</option>
          </select>
        </div>

        <div class="fItem">
          <span class="fLabel">股价</span>
          <div class="rangeBox">
            <input v-model="pmin" type="number" step="0.5" class="numIn" placeholder="最低" @input="onInputDebounce" />
            <span class="rangeSep">—</span>
            <input v-model="pmax" type="number" step="0.5" class="numIn" placeholder="最高" @input="onInputDebounce" />
          </div>
        </div>

        <div class="fItem">
          <span class="fLabel">涨跌幅 %</span>
          <div class="rangeBox">
            <input v-model="cmin" type="number" step="0.5" class="numIn" placeholder="最低" @input="onInputDebounce" />
            <span class="rangeSep">—</span>
            <input v-model="cmax" type="number" step="0.5" class="numIn" placeholder="最高" @input="onInputDebounce" />
          </div>
        </div>

        <div class="fItem">
          <span class="fLabel">换手率 %</span>
          <div class="rangeBox">
            <input v-model="tmin" type="number" step="0.5" class="numIn" placeholder="最低" @input="onInputDebounce" />
            <span class="rangeSep">—</span>
            <input v-model="tmax" type="number" step="0.5" class="numIn" placeholder="最高" @input="onInputDebounce" />
          </div>
        </div>

        <div class="fItem">
          <span class="fLabel">搜索</span>
          <input v-model="kw" class="kwIn" placeholder="代码 / 名称" @input="onInputDebounce" />
        </div>

        <label class="chkLabel">
          <input type="checkbox" v-model="noST" @change="onSelectChange" />
          <span>剔除 ST</span>
        </label>

        <button v-if="hasFilters" class="resetBtn" @click="resetFilters" title="清空所有筛选条件">重置筛选</button>
      </div>

      <!-- 统计与计数条 -->
      <div class="statBar">
        <span v-if="stats" class="dayStats">
          {{ stats.valid }} 只有效 ·
          <b class="up">{{ stats.up }}</b> 涨 /
          <b class="down">{{ stats.down }}</b> 跌 ·
          涨停 <b class="up">{{ stats.limit_up }}</b> /
          跌停 <b class="down">{{ stats.limit_down }}</b>
        </span>
        <span class="barSpacer"></span>
        <span class="cnt">
          共 <b>{{ total }}</b> 只符合条件
          <template v-if="sorted.length > visibleRows.length">
            （当前显示前 {{ visibleRows.length }} 只）
          </template>
        </span>
      </div>

      <!-- 表格展示 -->
      <div class="tblWrap" :class="{ loading }">
        <table v-if="visibleRows.length">
          <thead>
            <tr>
              <th v-for="h in HEAD" :key="h.k" :class="[h.l ? 'l' : '', thCls(h.k)]"
                  @click="onTh(h.k)">{{ h.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in visibleRows" :key="r.f12">
              <td class="l">{{ r.f12 }}</td>
              <td class="l name">
                <router-link class="nameLink" :to="'/stock/' + r.f12">{{ r.f14 }}</router-link>
                <span v-if="r.limit_up === 1" class="lmBadge up">涨停</span>
                <span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span>
              </td>
              <td class="l">
                <span class="mktBadge" :class="mktBadgeCls(r.market)">{{ r.market || '—' }}</span>
              </td>
              <td>{{ fmtN(r.f2) }}</td>
              <td :class="cls(r.f3)">{{ fmtN(r.f3) }}</td>
              <td><b>{{ fmtN(r.f8) }}</b></td>
              <td class="l dimTxt">{{ r.f100 || "—" }}</td>
              <td>{{ fmtYiT(r.f6) }}</td>
              <td>{{ fmtYiT(r.f20) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">
          {{ loading ? "加载中…" : (dates.length ? "没有匹配的记录，可尝试放宽筛选条件" : "还没有历史数据——每交易日 15:06 收盘后自动落库") }}
        </div>
      </div>

      <!-- 分批加载更多控制 -->
      <div v-if="sorted.length > visibleRows.length" class="loadMoreBar">
        <span>已显示 {{ visibleRows.length }} / {{ sorted.length }} 只</span>
        <button class="moreBtn" @click="loadMore">加载更多 (+300)</button>
        <button class="moreBtn ghost" @click="showAll">显示全部</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hisWrap { padding: 12px 0 48px; }
.blk { margin-top: 10px; }
.secHead {
  display: flex; align-items: baseline; gap: 12px;
  padding-bottom: 10px; border-bottom: 1px solid var(--line);
}
.secName { font-size: 15px; font-weight: 650; letter-spacing: .04em; }
.secName::before {
  content: ""; display: inline-block; width: 3px; height: 12px; border-radius: 2px;
  background: var(--brand-red, #ff4d4f); margin-right: 8px; vertical-align: -1px;
}
.secNote { color: var(--dim); font-size: 12px; }

/* 筛选工具栏 */
.filterBar {
  display: flex; align-items: center; gap: 12px; margin: 14px 0 8px; flex-wrap: wrap;
  background: var(--panel-2); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--line);
}
.fItem { display: flex; align-items: center; gap: 6px; }
.fLabel { font-size: 12px; color: var(--dim); white-space: nowrap; }

.sel, .kwIn, .numIn {
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  color: var(--txt); font-size: 12.5px; padding: 4px 8px; font-family: inherit;
  outline: none; transition: border-color .15s;
}
.sel:focus, .kwIn:focus, .numIn:focus { border-color: var(--accent); }
.sel { cursor: pointer; }
.kwIn { width: 120px; }
.rangeBox { display: flex; align-items: center; gap: 3px; }
.numIn { width: 62px; text-align: center; font-family: var(--mono); }
.numIn::-webkit-outer-spin-button,
.numIn::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.rangeSep { font-size: 11px; color: var(--dim); }

.chkLabel {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px;
  color: var(--txt); cursor: pointer; user-select: none; margin-left: 2px;
}
.chkLabel input { cursor: pointer; }

.resetBtn {
  background: transparent; border: 1px solid var(--line); border-radius: 6px;
  color: var(--dim); font-size: 12px; padding: 4px 10px; cursor: pointer;
  transition: all .15s; margin-left: auto;
}
.resetBtn:hover { color: var(--accent); border-color: var(--accent); }

/* 统计条 */
.statBar {
  display: flex; align-items: center; gap: 10px; margin: 8px 0 12px;
  padding: 0 4px; font-size: 12px; color: var(--dim); flex-wrap: wrap;
}
.dayStats b { font-family: var(--mono); }
.barSpacer { flex: 1; }
.cnt b { color: var(--txt); font-family: var(--mono); }

/* 表格 */
.tblWrap { overflow-x: auto; }
.tblWrap.loading { opacity: .55; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: right; color: var(--dim); font-weight: 500; font-size: 11.5px;
  letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line-strong);
  cursor: pointer; white-space: nowrap; user-select: none;
}
th.l, td.l { text-align: left; }
th.sorted { color: var(--accent); }
th.sorted.asc::after { content: " ↑"; }
th.sorted.desc::after { content: " ↓"; }
td {
  text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line);
  font-family: var(--mono); white-space: nowrap;
}
td.name { font-family: inherit; }
.nameLink { color: var(--txt); text-decoration: none; font-weight: 600; }
.nameLink:hover { color: var(--accent); }
tr:hover td { background: var(--hover); }
.dimTxt { color: var(--dim); font-family: inherit; }
.up { color: var(--up); }
.down { color: var(--down); }

/* 涨跌停徽标 */
.lmBadge {
  display: inline-block; font-size: 10px; padding: 1px 4px; border-radius: 3px;
  font-weight: 600; margin-left: 6px; vertical-align: 1px;
}
.lmBadge.up { background: rgba(245, 34, 45, .15); color: var(--up); }
.lmBadge.down { background: rgba(82, 196, 26, .15); color: var(--down); }

/* 板块标签 */
.mktBadge {
  display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 3px;
  background: var(--panel-2); color: var(--dim); border: 1px solid var(--line);
}
.mktBadge.mkt-mb { color: #597ef7; border-color: rgba(89, 126, 247, .25); background: rgba(89, 126, 247, .08); }
.mktBadge.mkt-cyb { color: #13c2c2; border-color: rgba(19, 194, 194, .25); background: rgba(19, 194, 194, .08); }
.mktBadge.mkt-kcb { color: #fa8c16; border-color: rgba(250, 140, 22, .25); background: rgba(250, 140, 22, .08); }
.mktBadge.mkt-bjs { color: #9254de; border-color: rgba(146, 84, 222, .25); background: rgba(146, 84, 222, .08); }

/* 加载更多 */
.loadMoreBar {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 18px 0; color: var(--dim); font-size: 12px;
}
.moreBtn {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 6px;
  color: var(--txt); font-size: 12px; padding: 5px 14px; cursor: pointer; transition: all .15s;
}
.moreBtn:hover { border-color: var(--accent); color: var(--accent); }
.moreBtn.ghost { color: var(--dim); }

.empty { padding: 48px 0; text-align: center; color: var(--dim); font-size: 13px; line-height: 1.9; }
</style>
