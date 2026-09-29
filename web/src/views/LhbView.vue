<script setup>
/* ===== 龙虎榜:每日榜单 + 营业部席位画像 =====
   榜单页:日期切换 → 个股上榜汇总(净买额绝对值降序),点行展开买卖五席位;
   席位榜:胜率/上榜次数/净买额排序,点行出席位画像弹窗(含次日结果明细)。
   数据每日 18:05 后由服务端采集,首次部署自动回填约 60 个交易日。 */
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { track } from "../api/client";
import { cls, fmtN, fmtYiT } from "../utils/format";
import {
  fetchLhbDates, fetchLhbDaily, fetchLhbStockSeats, fetchLhbSeats, fetchLhbSeat,
} from "../lhb/lhb-data";

const tab = ref("daily");   // daily | seats

/* ---------- 每日榜单 ---------- */
const dates = ref([]);
const date = ref("");
const rows = ref([]);
const summary = ref(null);
const loading = ref(false);
const expanded = ref("");          // 展开的 code
const seatDetail = ref(null);      // { buy, sell } | null
const seatLoading = ref(false);

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
  const key = r.code + r.explain;
  if (expanded.value === key) { expanded.value = ""; return; }
  expanded.value = key;
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
const seatRows = ref([]);
const seatsLoading = ref(false);
const SORTS = [
  { k: "win_rate", name: "胜率" },
  { k: "apps", name: "上榜次数" },
  { k: "net", name: "累计净买" },
];

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

async function openProfile(name) {
  profileLoading.value = true;
  profile.value = null;
  try {
    profile.value = await fetchLhbSeat(name);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "画像加载失败");
  } finally {
    profileLoading.value = false;
  }
}
function closeProfile() { profile.value = null; profileLoading.value = false; }

const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const pctCls = (v) => (v == null ? "" : cls(v * 100));

const profileShown = computed(() => profileLoading.value || profile.value);

function switchTab(t) {
  tab.value = t;
  if (t === "seats" && !seatRows.value.length) loadSeats();
}

onMounted(loadDates);
</script>

<template>
  <div class="lhbWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">龙虎榜</span>
        <span class="secNote">每日收盘后采集 · 席位胜率按次日收盘口径回填</span>
        <span class="barSpacer"></span>
        <div class="tabBtns">
          <button :class="{ on: tab === 'daily' }" @click="switchTab('daily')">每日榜单</button>
          <button :class="{ on: tab === 'seats' }" @click="switchTab('seats')">席位画像</button>
        </div>
      </div>

      <!-- ===== 每日榜单 ===== -->
      <template v-if="tab === 'daily'">
        <div class="bar">
          <button class="dayBtn" @click="stepDay(-1)" :disabled="!dates.length">← 前一日</button>
          <select v-model="date" class="dateSel" @change="loadDaily" :disabled="!dates.length">
            <option v-if="!dates.length" value="">暂无数据(首日 18:05 后自动采集)</option>
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
          <button class="dayBtn" @click="stepDay(1)" :disabled="!dates.length">后一日 →</button>
          <span v-if="summary" class="dayStats">
            上榜 <b>{{ rows.length }}</b> 条 ·
            净买入 <b class="up">{{ fmtYiT(summary.buy) }}</b> /
            净卖出 <b class="down">{{ fmtYiT(summary.sell) }}</b>
          </span>
        </div>

        <div class="tblWrap" :class="{ loading }">
          <table v-if="rows.length">
            <thead>
              <tr>
                <th class="l">代码</th><th class="l">名称</th><th class="l">上榜原因</th>
                <th>收盘价</th><th>涨跌幅 %</th><th>净买入</th>
                <th>买入</th><th>卖出</th><th>换手 %</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="r in rows" :key="r.id">
                <tr class="clk" @click="toggleRow(r)">
                  <td class="l">{{ r.code }}</td>
                  <td class="l name">
                    <router-link class="nameLink" :to="'/stock/' + r.code" @click.stop>{{ r.name }}</router-link>
                  </td>
                  <td class="l dimTxt">{{ r.explain }}</td>
                  <td>{{ fmtN(r.close_price) }}</td>
                  <td :class="cls(r.change_rate)">{{ fmtN(r.change_rate) }}</td>
                  <td><b :class="cls(r.net_amt / 1e6)">{{ fmtYiT(r.net_amt) }}</b></td>
                  <td>{{ fmtYiT(r.buy_amt) }}</td>
                  <td>{{ fmtYiT(r.sell_amt) }}</td>
                  <td>{{ fmtN(r.turnover_rate) }}</td>
                </tr>
                <tr v-if="expanded === r.code + r.explain" class="expRow">
                  <td colspan="9">
                    <div v-if="seatLoading" class="expLoading">席位明细加载中…</div>
                    <div v-else-if="seatDetail" class="seatCols">
                      <div class="seatCol">
                        <div class="seatColT up">买入席位</div>
                        <div v-for="s in seatDetail.buy" :key="s.id" class="seatLine">
                          <span class="seatName clk" @click="openProfile(s.dept_name)">{{ s.dept_name }}</span>
                          <span>{{ fmtYiT(s.buy) }}</span>
                        </div>
                        <div v-if="!seatDetail.buy.length" class="dimTxt">无买入席位数据</div>
                      </div>
                      <div class="seatCol">
                        <div class="seatColT down">卖出席位</div>
                        <div v-for="s in seatDetail.sell" :key="s.id" class="seatLine">
                          <span class="seatName clk" @click="openProfile(s.dept_name)">{{ s.dept_name }}</span>
                          <span>{{ fmtYiT(s.sell) }}</span>
                        </div>
                        <div v-if="!seatDetail.sell.length" class="dimTxt">无卖出席位数据</div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
          <div v-else class="empty">
            {{ loading ? "加载中…" : "该交易日没有龙虎榜数据——榜单每日 18:05 后自动采集，周末及非交易日无数据" }}
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
          <span class="barSpacer"></span>
          <span class="cnt">上榜 ≥3 次 · 胜率=次日收涨占比</span>
        </div>

        <div class="tblWrap" :class="{ loading: seatsLoading }">
          <table v-if="seatRows.length">
            <thead>
              <tr>
                <th class="l">营业部席位</th><th>上榜次数</th><th>胜率</th>
                <th>次日开盘溢价</th><th>次日收盘涨幅</th><th>次日最高溢价</th>
                <th>累计净买</th><th>最近上榜</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in seatRows" :key="s.dept_name" class="clk" @click="openProfile(s.dept_name)">
                <td class="l name">{{ s.dept_name }}</td>
                <td>{{ s.appearances }}</td>
                <td><b :class="s.win_rate == null ? '' : (s.win_rate >= 0.5 ? 'up' : 'down')">{{ s.win_rate == null ? "—" : (s.win_rate * 100).toFixed(0) + "%" }}</b></td>
                <td :class="pctCls(s.avg_open_premium)">{{ pct(s.avg_open_premium) }}</td>
                <td :class="pctCls(s.avg_close_pct)">{{ pct(s.avg_close_pct) }}</td>
                <td :class="pctCls(s.avg_max_premium)">{{ pct(s.avg_max_premium) }}</td>
                <td :class="cls((s.total_net || 0) / 1e6)">{{ fmtYiT(s.total_net) }}</td>
                <td class="dimTxt">{{ s.last_date }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">
            {{ seatsLoading ? "加载中…" : "暂无席位画像——需先积累上榜数据,次日收盘后回填胜率" }}
          </div>
        </div>
      </template>
    </section>

    <!-- ===== 席位画像弹窗 ===== -->
    <div v-if="profileShown" class="pMask" @click.self="closeProfile">
      <div class="pBox">
        <div v-if="profileLoading" class="expLoading">画像加载中…</div>
        <template v-else-if="profile">
          <div class="pHead">
            <b>{{ profile.stat.dept_name }}</b>
            <button class="pClose" @click="closeProfile">×</button>
          </div>
          <div class="pStats">
            上榜 <b>{{ profile.stat.appearances }}</b> 次 ·
            胜率 <b :class="profile.stat.win_rate >= 0.5 ? 'up' : 'down'">{{ profile.stat.win_rate == null ? "—" : (profile.stat.win_rate * 100).toFixed(0) + "%" }}</b> ·
            次日开盘 <span :class="pctCls(profile.stat.avg_open_premium)">{{ pct(profile.stat.avg_open_premium) }}</span> ·
            次日收盘 <span :class="pctCls(profile.stat.avg_close_pct)">{{ pct(profile.stat.avg_close_pct) }}</span> ·
            累计净买 <b>{{ fmtYiT(profile.stat.total_net) }}</b>
          </div>
          <div v-if="profile.stat.top_stocks.length" class="pTags">
            偏好:
            <router-link v-for="t in profile.stat.top_stocks" :key="t.code" class="pTag"
                         :to="'/stock/' + t.code">{{ t.name }}×{{ t.n }}</router-link>
          </div>
          <div v-if="profile.stat.co_seats.length" class="pTags">
            联动:
            <span v-for="cstat in profile.stat.co_seats" :key="cstat.dept" class="pTag dim">{{ cstat.dept }}×{{ cstat.n }}</span>
          </div>
          <table class="pTbl" v-if="profile.recent.length">
            <thead>
              <tr><th class="l">日期</th><th class="l">股票</th><th>方向</th>
                <th>净额</th><th>次日开盘</th><th>次日收盘</th></tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in profile.recent" :key="i">
                <td class="l dimTxt">{{ r.trade_date }}</td>
                <td class="l">{{ r.name }}</td>
                <td :class="r.side === 'B' ? 'up' : 'down'">{{ r.side === 'B' ? "买" : "卖" }}</td>
                <td :class="cls((r.net || 0) / 1e6)">{{ fmtYiT(r.net) }}</td>
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
.barSpacer { flex: 1; }

.tabBtns { display: flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 999px; padding: 2px; }
.tabBtns button {
  background: none; border: none; border-radius: 999px; cursor: pointer;
  color: var(--dim); font-size: 12px; font-family: inherit; padding: 3px 12px;
}
.tabBtns button.on { color: var(--accent); background: var(--accent-dim); }
.tabBtns.sm button { font-size: 11.5px; padding: 2px 10px; }

.bar { display: flex; align-items: center; gap: 10px; margin: 14px 0 10px; flex-wrap: wrap; }
.dateSel, .kwIn {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  color: var(--txt); font-size: 13px; padding: 6px 10px; font-family: inherit; outline: none;
}
.dateSel:focus, .kwIn:focus { border-color: var(--accent); }
.kwIn { width: 180px; }
.dayBtn {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  color: var(--dim); font-size: 12px; padding: 6px 10px; cursor: pointer; font-family: inherit;
}
.dayBtn:hover { color: var(--txt); }
.dayStats { font-size: 12.5px; color: var(--dim); }
.dayStats b { font-family: var(--mono); }
.cnt { font-size: 12px; color: var(--dim); }

.tblWrap { overflow-x: auto; }
.tblWrap.loading { opacity: .55; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: right; color: var(--dim); font-weight: 500; font-size: 11.5px;
  letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line-strong);
  white-space: nowrap; user-select: none;
}
th.l, td.l { text-align: left; }
td { text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line); font-family: var(--mono); white-space: nowrap; }
td.name { font-family: inherit; }
tr.clk { cursor: pointer; }
tr:hover td { background: var(--hover); }
.nameLink { color: var(--txt); text-decoration: none; font-weight: 600; }
.nameLink:hover { color: var(--accent); }
.dimTxt { color: var(--dim); font-family: inherit; }
.up { color: var(--up); }
.down { color: var(--down); }
.empty { padding: 48px 0; text-align: center; color: var(--dim); font-size: 13px; line-height: 1.9; }

.expRow td { background: var(--panel-2); white-space: normal; }
.expLoading { padding: 12px; color: var(--dim); font-size: 12px; }
.seatCols { display: flex; gap: 24px; padding: 10px 8px; flex-wrap: wrap; }
.seatCol { flex: 1; min-width: 260px; }
.seatColT { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.seatLine { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; padding: 3px 0; font-family: var(--mono); }
.seatName { font-family: inherit; color: var(--txt); }
.seatName.clk:hover { color: var(--accent); }

.pMask {
  position: fixed; inset: 0; z-index: 60; background: rgba(0, 0, 0, .45);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.pBox {
  background: var(--panel); border: 1px solid var(--line-strong); border-radius: 12px;
  width: 100%; max-width: 720px; max-height: calc(100vh - 80px); overflow-y: auto; padding: 16px 18px;
}
.pHead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.pHead b { font-size: 14px; }
.pClose { background: none; border: none; color: var(--dim); font-size: 20px; cursor: pointer; }
.pClose:hover { color: var(--txt); }
.pStats { font-size: 12.5px; color: var(--dim); margin-bottom: 8px; }
.pStats b, .pStats span { font-family: var(--mono); }
.pTags { font-size: 12px; color: var(--dim); margin-bottom: 6px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.pTag {
  background: var(--accent-dim); color: var(--accent); border-radius: 4px;
  padding: 1px 8px; font-size: 11.5px; text-decoration: none;
}
.pTag.dim { background: var(--panel-2); color: var(--dim); }
.pTbl { margin-top: 10px; }
.pTbl td, .pTbl th { padding: 5px 8px; }
</style>
