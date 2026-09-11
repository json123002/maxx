<script setup>
/* ===== 历史榜单回看：每交易日收盘落库的全市场快照 =====
   选日期 → 后端按换手率降序返回;支持代码/名称搜索、列头排序;
   点名称进个股详情页。埋点 history_view 记录回看行为。 */
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { api, track } from "../api/client";
import { cls, cmpRows, fmtN, fmtYiT } from "../utils/format";

const dates = ref([]);
const date = ref("");
const rows = ref([]);
const total = ref(0);
const stats = ref(null);
const kw = ref("");
const loading = ref(false);
const sortKey = ref("f8"), sortDir = ref(-1);

const HEAD = [
  { k: "f12", name: "代码", l: true },
  { k: "f14", name: "名称", l: true },
  { k: "f2", name: "收盘价" },
  { k: "f3", name: "涨跌幅 %" },
  { k: "f8", name: "换手率 %" },
  { k: "f100", name: "行业", l: true },
  { k: "f6", name: "成交额" },
  { k: "f20", name: "总市值" },
];

const sorted = computed(() =>
  rows.value.slice().sort(cmpRows(sortKey.value, sortDir.value)));

function thCls(k) {
  return { sorted: k === sortKey.value,
           asc: k === sortKey.value && sortDir.value === 1,
           desc: k === sortKey.value && sortDir.value === -1 };
}
function onTh(k) {
  if (sortKey.value === k) sortDir.value *= -1;
  else { sortKey.value = k; sortDir.value = (k === "f12" || k === "f14" || k === "f100") ? 1 : -1; }
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

let kwTimer = null;
function onKw() {
  clearTimeout(kwTimer);
  kwTimer = setTimeout(load, 300);
}

async function load() {
  if (!date.value) return;
  loading.value = true;
  try {
    const p = new URLSearchParams({ date: date.value });
    if (kw.value.trim()) p.set("kw", kw.value.trim());
    const d = await api("/api/quote/history?" + p);
    rows.value = d.rows;
    total.value = d.total;
    stats.value = d.stats;
    track("history_view", date.value + (kw.value.trim() ? " kw:" + kw.value.trim() : "")
          + " → " + d.total + " 只");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadDates);
</script>

<template>
  <div class="hisWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">历史榜单</span>
        <span class="secNote">每交易日收盘落库 · 按换手率排序</span>
      </div>

      <div class="bar">
        <select v-model="date" class="dateSel" @change="load" :disabled="!dates.length">
          <option v-if="!dates.length" value="">暂无历史数据</option>
          <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
        </select>
        <input v-model="kw" class="kwIn" placeholder="代码 / 名称" @input="onKw" />
        <span v-if="stats" class="dayStats">
          {{ stats.valid }} 只有效 ·
          <b class="up">{{ stats.up }}</b> 涨 /
          <b class="down">{{ stats.down }}</b> 跌 ·
          涨停 <b class="up">{{ stats.limit_up }}</b> /
          跌停 <b class="down">{{ stats.limit_down }}</b>
        </span>
        <span class="barSpacer"></span>
        <span class="cnt" v-if="total">共 {{ total }} 只</span>
      </div>

      <div class="tblWrap" :class="{ loading }">
        <table v-if="sorted.length">
          <thead>
            <tr>
              <th v-for="h in HEAD" :key="h.k" :class="[h.l ? 'l' : '', thCls(h.k)]"
                  @click="onTh(h.k)">{{ h.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in sorted" :key="r.f12">
              <td class="l">{{ r.f12 }}</td>
              <td class="l name">
                <router-link class="nameLink" :to="'/stock/' + r.f12">{{ r.f14 }}</router-link>
                <span v-if="r.limit_up === 1" class="lmBadge up">涨停</span>
                <span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span>
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
          {{ loading ? "加载中…" : (dates.length ? "该日期没有匹配的记录" : "还没有历史数据——每交易日 15:06 收盘后自动落库") }}
        </div>
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
  background: var(--brand-red); margin-right: 8px; vertical-align: -1px;
}
.secNote { color: var(--dim); font-size: 12px; }

.bar { display: flex; align-items: center; gap: 10px; margin: 14px 0 10px; flex-wrap: wrap; }
.dateSel, .kwIn {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  color: var(--txt); font-size: 13px; padding: 6px 10px; font-family: inherit;
  outline: none;
}
.dateSel:focus, .kwIn:focus { border-color: var(--accent); }
.kwIn { width: 140px; }
.dayStats { font-size: 12.5px; color: var(--dim); }
.dayStats b { font-family: var(--mono); }
.barSpacer { flex: 1; }
.cnt { font-size: 12px; color: var(--dim); }

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
.empty { padding: 48px 0; text-align: center; color: var(--dim); font-size: 13px; line-height: 1.9; }
</style>
