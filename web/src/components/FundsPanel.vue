<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Modal } from "ant-design-vue";
import { api } from "../api/client";
import { virtualWindow } from "../utils/virtual-window.js";

const props = defineProps({ code: { type: String, required: true } });
const data = ref(null), loading = ref(false), error = ref("");
const minimum = ref(0), side = ref("all"), detailMode = ref("trades");
const scrollTop = ref(0), tradeViewport = ref(null);
let version = 0, controller;
const summary = computed(() => data.value?.summary);
const tiers = computed(() => summary.value?.tiers || []);
const maxTier = computed(() => Math.max(1, ...tiers.value.map(t => Math.abs(t.net || 0))));
const history = computed(() => data.value?.history || []);
const maxHistory = computed(() => Math.max(1, ...history.value.map(d => Math.abs(d.net || 0))));
const filteredRows = computed(() => (data.value?.rows || []).filter(r => r.amount >= minimum.value && (side.value === 'all' || r.side === side.value)));
const tradeTotals = computed(() => filteredRows.value.reduce((s,r) => { s[r.side] += r.amount; return s; }, {buy:0,sell:0,neutral:0}));
const windowRange = computed(() => virtualWindow(filteredRows.value.length, Math.max(0, scrollTop.value - 32)));
const visibleRows = computed(() => filteredRows.value.slice(windowRange.value.start, windowRange.value.end));
function resetScroll() { scrollTop.value = 0; nextTick(() => { if (tradeViewport.value) tradeViewport.value.scrollTop = 0; }); }
const signClass = value => value == null ? "" : value > 0 ? "moneyUp" : value < 0 ? "moneyDown" : "";
const wan = value => Number.isFinite(value) ? (value / 10000).toLocaleString("zh-CN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "—";
const cash = value => Number.isFinite(value) ? value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : "—";
const pct = (v, m, scale = 80) => Math.abs(v || 0) / m * scale;

async function load() {
  controller?.abort();
  controller = new AbortController();
  const current = ++version;
  loading.value = true;
  error.value = "";
  try {
    const result = await api(`/api/desk/funds/${props.code}?all_rows=true`, { signal: controller.signal });
    if (current === version) { data.value = result; resetScroll(); }
  } catch (e) {
    if (current === version && e.name !== "AbortError" && e.message !== "unauthorized") error.value = e.message || "资金数据获取失败";
  } finally {
    if (current === version) loading.value = false;
  }
}
function filter(amount, direction = side.value) {
  minimum.value = amount;
  side.value = direction;
  resetScroll();
}
function darkPool() {
  Modal.info({ title: "暗盘资金 · 数据能力", okText: "知道了", content:
    "当前麦蕊接口未提供同花顺暗盘资金及其专有算法，也未提供可还原拆单的逐委托订单编号。此处不会将普通小单、被动买卖或资金差额当作暗盘数据。你可以展开主被动汇总，查看接口实际提供的四类资金。" });
}
watch(() => props.code, () => {
  data.value = null; minimum.value = 0; side.value = "all"; resetScroll(); load();
}, { immediate: true });
onBeforeUnmount(() => { version++; controller?.abort(); });
</script>

<template>
  <div class="fundsPanel" :aria-busy="loading">
    <header class="fundsTop"><span title="资金汇总约30分钟、明细约60分钟更新；非实时L2。汇总与明细日期可能不同，以各自日期为准。">{{ data?.source || '麦蕊智数' }} · {{ summary?.date || data?.trade_date || '加载中' }} · 金额单位：万元 · 非实时L2 ⓘ</span><button :disabled="loading" @click="load">{{ loading ? '更新中…' : '刷新' }}</button></header>
    <div v-if="error" class="fundsError">{{ error }}<span v-if="data">；当前保留上次成功数据</span><router-link to="/settings">行情设置 →</router-link></div>
    <div v-if="loading && !data" class="fundsLoading">正在获取分档资金与整日成交记录…</div>
    <template v-if="data">
      <p v-for="w in data.warnings" :key="w" class="fundsWarning">{{ w }}</p>
      <section v-if="summary">
        <div class="fundsHeading"><h3>大单流向 <small>（万元）</small></h3></div>
        <div class="moneyOverview">
          <div class="moneyStats">
            <div><span>大单流入</span><b class="moneyUp">{{ wan(summary.buy) }}</b></div>
            <div><span>大单流出</span><b class="moneyDown">{{ wan(summary.sell) }}</b></div>
            <div><span>大单净流入</span><b :class="signClass(summary.net)">{{ wan(summary.net) }}</b></div>
            <div><span>暗盘资金</span><button class="textAction" @click="darkPool">查看能力 ↗</button></div>
            <p title="主买／主卖中的特大单与大单金额之和">特大单＋大单 · 主买／主卖口径</p>
          </div>
          <div class="tierChart">
            <svg viewBox="0 0 440 185" role="img" aria-label="特大单、大单、中单、小单主动净额，单位万元">
              <line x1="10" x2="430" y1="80" y2="80" class="zeroLine" />
              <g v-for="(t, i) in tiers" :key="t.key">
                <rect :x="32 + i * 106" :y="t.net >= 0 ? 80 - pct(t.net, maxTier,50) : 80" width="34" :height="pct(t.net, maxTier,50)" :class="t.net >= 0 ? 'barUp' : 'barDown'" rx="3"><title>{{ t.name }}净额 {{ wan(t.net) }}万元</title></rect>
                <text :x="49 + i * 106" :y="t.net >= 0 ? 72 - pct(t.net, maxTier,50) : 96 + pct(t.net, maxTier,50)" text-anchor="middle" :class="signClass(t.net)">{{ wan(t.net) }}</text>
                <text :x="49 + i * 106" y="177" text-anchor="middle" class="tierName">{{ t.name }}</text>
              </g>
            </svg>
          </div>
        </div>
      </section>
      <section v-if="history.length">
        <div class="fundsHeading"><h3>近 {{ history.length }} 日大单流向 <small>（万元）</small></h3><span>{{ history[0].date }} — {{ history.at(-1).date }}</span></div>
        <div class="fundPeriods"><div v-for="n in [3,5,10,20]" :key="n"><span>近 {{ Math.min(n, history.length) }} 日累计</span><b :class="signClass(history.slice(-n).every(d => d.net !== null) ? history.slice(-n).reduce((s,d)=>s+d.net,0) : null)">{{ wan(history.slice(-n).every(d => d.net !== null) ? history.slice(-n).reduce((s,d)=>s+d.net,0) : null) }}</b></div></div>
        <svg class="historyChart" viewBox="0 0 720 130" role="img" aria-label="大单主动净流入历史，单位万元">
          <line x1="10" x2="710" y1="55" y2="55" class="zeroLine"/>
          <g v-for="(d,i) in history" :key="d.date">
            <rect :x="14 + i * (692 / history.length)" :width="Math.max(4, 692 / history.length - 6)" :y="d.net >= 0 ? 55 - pct(d.net,maxHistory,40) : 55" :height="pct(d.net,maxHistory,40)" :class="d.net >= 0 ? 'barUp' : 'barDown'" rx="2"><title>{{ d.date }} 净流入 {{ wan(d.net) }}万元</title></rect>
            <text v-if="i === 0 || i === history.length-1 || i % 5 === 0" :x="20 + i * (692 / history.length)" y="124" class="historyDate">{{ d.date.slice(5) }}</text>
          </g>
        </svg>
      </section>
      <section>
        <div class="fundsHeading"><h3>大资金动向 · 成交明细</h3><span>日期 {{ data.trade_date || '暂无' }} · {{ data.available_count.toLocaleString() }} 条可用</span></div>
        <div class="detailModes"><button :class="{on:detailMode === 'trades'}" @click="detailMode = 'trades'">成交明细</button><button :class="{on:detailMode === 'summary'}" @click="detailMode = 'summary'">主动／被动汇总</button><small>{{ detailMode === 'trades' ? '买卖方向为源分类，逐笔主动／被动标记未提供' : '供应商分档汇总 · 单位：万元' }}</small></div>
        <template v-if="detailMode === 'summary'">
          <div v-if="tiers.length" class="fundsTableWrap"><table class="fundsTable"><thead><tr><th>分单类型</th><th>主动买</th><th>主动卖</th><th>被动买</th><th>被动卖</th><th>主动净额</th></tr></thead><tbody><tr v-for="t in tiers" :key="t.key"><td>{{ t.name }}</td><td class="moneyUp">{{ wan(t.active_buy) }}</td><td class="moneyDown">{{ wan(t.active_sell) }}</td><td>{{ wan(t.passive_buy) }}</td><td>{{ wan(t.passive_sell) }}</td><td :class="signClass(t.net)">{{ wan(t.net) }}</td></tr></tbody></table></div>
          <p v-else class="fundsCaption">当前没有可用主被动汇总</p>
          <p class="fundsCaption">汇总日期 {{ summary?.date || '暂无' }}。被动与对手方主动存在对应关系，不可重复相加；缺失字段显示“—”。</p>
        </template>
        <template v-else>
        <div class="tradeFilters"><div><button v-for="f in [[0,'全部金额'],[1000000,'≥100万'],[10000000,'≥1000万'],[50000000,'≥5000万']]" :key="f[0]" :class="{on:minimum === f[0]}" :disabled="loading" @click="filter(f[0])">{{ f[1] }}</button></div><div><button v-for="s in [['all','全部方向'],['buy','买盘'],['sell','卖盘'],['neutral','中性']]" :key="s[0]" :class="{on:side === s[0]}" :disabled="loading" @click="filter(minimum,s[0])">{{ s[1] }}</button></div></div>
        <div class="tradeTotals"><span>符合 {{ filteredRows.length.toLocaleString() }} 条</span><span>买盘 <b class="moneyUp">{{ wan(tradeTotals.buy) }} 万</b></span><span>卖盘 <b class="moneyDown">{{ wan(tradeTotals.sell) }} 万</b></span><span>中性 {{ wan(tradeTotals.neutral) }} 万</span></div>
        <div v-if="filteredRows.length" ref="tradeViewport" class="fundsTableWrap tradeTableWrap" tabindex="0" aria-label="成交明细虚拟滚动列表" @scroll="scrollTop = $event.target.scrollTop"><table class="fundsTable virtualTradeTable" :aria-rowcount="filteredRows.length + 1"><thead><tr><th>时间</th><th>方向（源分类）</th><th>金额（万元）</th><th>成交量（手）</th><th>价格（元）</th></tr></thead><tbody>
          <tr v-if="windowRange.top" class="virtualSpacer" aria-hidden="true"><td colspan="5" :style="{height:windowRange.top+'px'}"></td></tr>
          <tr v-for="(r,i) in visibleRows" :key="r.id" :aria-rowindex="windowRange.start + i + 2"><td>{{ r.time }}</td><td :class="r.side === 'buy' ? 'moneyUp' : r.side === 'sell' ? 'moneyDown' : ''">{{ r.side === 'buy' ? '买盘' : r.side === 'sell' ? '卖盘' : '中性' }}</td><td>{{ wan(r.amount) }}</td><td>{{ cash(r.volume) }}</td><td>{{ r.price.toFixed(2) }}</td></tr>
          <tr v-if="windowRange.bottom" class="virtualSpacer" aria-hidden="true"><td colspan="5" :style="{height:windowRange.bottom+'px'}"></td></tr>
        </tbody></table></div>
        <div v-else class="fundsLoading">{{ data.available_count ? '当日已返回的记录中，没有符合当前条件的成交' : '接口未返回有效成交明细' }}</div>
        </template>
        <details class="fundsNotes"><summary>数据说明与金额核对</summary><p class="fundsCaption">整日已返回数据本地筛选、虚拟滚动，无需翻页。金额＝成交价×股数。仅含09:25集合竞价及09:30—11:30、13:00—15:00记录，剔除 {{ data.excluded_count }} 条其他时段或无效数据，不含盘后固定价格交易。历史趋势仅统计实际返回的交易日，最多20日。</p>
        <p v-if="data.available_count" class="fundsCaption">金额核对：有效明细总额 {{ wan(data.detail_amount) }} 万元；分档主买＋主卖总额 {{ wan(data.summary_turnover) }} 万元。两者按各自接口独立统计。</p>
        </details>
      </section>
    </template>
  </div>
</template>

<style scoped>
.fundsPanel { color: var(--txt); font-size: 13px; min-width: 0; }
.fundsTop { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 26px; margin-bottom: 4px; }
.fundsTop h2 { font-size: 18px; font-weight: 650; margin: 0 0 5px; }
.fundsTop span,.fundsSource,.fundsHeading > span { color: var(--dim); font-size: 11px; }
.fundsPanel button { font-family: inherit; cursor: pointer; }
.fundsTop > button { padding: 3px 10px; background: var(--panel); border: 1px solid var(--line); color: var(--txt); border-radius: 6px; font-size: 11px; flex: none; }
button:disabled { opacity: .5; cursor: default; }
.fundsSource { line-height: 1.8; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.fundsSource span { display: block; }
.fundsError,.fundsWarning { color: var(--dim); background: var(--panel-2); border-radius: 8px; padding: 12px; line-height: 1.8; }
.fundsError a { display: inline-block; margin-left: 12px; color: var(--accent); }
.fundsLoading { text-align: center; color: var(--dim); padding: 36px 10px; }
.fundsHeading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin: 14px 0 10px; }
.fundsHeading h3 { margin: 0; font-size: 13px; font-weight: 650; border-left: 3px solid var(--up); padding-left: 8px; }
.fundsHeading small { color: var(--dim); font-size: 12px; font-weight: 400; }
.textAction { border: 0; color: var(--accent); background: transparent; padding: 0; font-size: 12px; }
.moneyOverview { display: grid; grid-template-columns: minmax(230px,.85fr) minmax(260px,1fr); gap: 12px; max-width: 900px; }
.moneyStats,.tierChart { background: var(--panel-2); border-radius: 8px; padding: 12px 16px; }
.moneyStats > div { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 5px 0; font-size: 12px; }
.moneyStats b { font-size: 17px; font-weight: 550; font-family: var(--mono); font-variant-numeric: tabular-nums; }
.moneyStats p { color: var(--dim); font-size: 10px; line-height: 1.6; margin: 6px 0 0; }
.tierChart { display: flex; align-items: center; padding: 8px; }
.tierChart svg { display: block; width: 100%; height: 152px; }
svg text { fill: var(--txt); font: 12px var(--mono); }
svg text.moneyUp { fill: var(--up); } svg text.moneyDown { fill: var(--down); }
svg .tierName { fill: var(--dim); font: 13px var(--font); }
.zeroLine { stroke: var(--line-strong); stroke-width: 1; }
.barUp { fill: var(--up); } .barDown { fill: var(--down); }
.moneyUp { color: var(--up); } .moneyDown { color: var(--down); }
.fundsTableWrap { overflow: auto; margin-top: 16px; }
.fundsTable { width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }
.fundsTable th,.fundsTable td { padding: 11px 12px; text-align: right; border-bottom: 1px solid var(--line); }
.fundsTable th { font-weight: 500; color: var(--dim); background: var(--panel); position: sticky; top: 0; }
.fundsTable th:first-child,.fundsTable td:first-child { text-align: left; }
.fundsTable td { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.fundsCaption { color: var(--dim); font-size: 10px; line-height: 1.9; margin: 12px 0; }
.fundPeriods { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; background: var(--panel-2); padding: 10px 14px; border-radius: 8px; }
.fundPeriods span { display: block; color: var(--dim); font-size: 11px; margin-bottom: 8px; }
.fundPeriods b { font: 500 13px var(--mono); }
.historyChart { width: 100%; height: 115px; margin-top: 8px; }
svg .historyDate { fill: var(--dim); font-size: 10px; }
.tradeFilters { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
.tradeFilters > div { display: flex; flex-wrap: wrap; gap: 5px; }
.tradeFilters button { border: 1px solid var(--line); padding: 6px 9px; color: var(--dim); background: var(--panel-2); font-size: 11px; border-radius: 6px; }
.tradeFilters button.on { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.tradeTotals { display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 15px; font-size: 11px; color: var(--dim); }
.tradeTotals b { font-weight: 500; }
.tradeTableWrap { height: 420px; overflow-anchor: none; border: 1px solid var(--line); border-radius: 8px; }
.virtualTradeTable { table-layout: fixed; border-collapse: separate; border-spacing: 0; min-width: 520px; }
.virtualTradeTable th { height: 32px; padding: 0 12px; line-height: 31px; box-sizing: border-box; z-index: 1; }
.virtualTradeTable td { height: 34px; padding: 0 12px; line-height: 33px; box-sizing: border-box; }
.virtualTradeTable .virtualSpacer td { padding: 0; border: 0; line-height: 0; }
.detailModes { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.detailModes button { border: 0; border-bottom: 2px solid transparent; background: none; color: var(--dim); padding: 6px 8px; font-size: 12px; }
.detailModes button.on { color: var(--accent); border-bottom-color: var(--accent); }
.detailModes small { margin-left: auto; color: var(--dim); font-size: 10px; }
.fundsNotes { color: var(--dim); font-size: 10px; margin-top: 12px; }
.fundsNotes summary { cursor: pointer; }
@media(max-width: 700px) { .moneyOverview { grid-template-columns: 1fr; } .moneyStats b { font-size: 17px; } .fundPeriods { grid-template-columns: 1fr 1fr; } .fundsHeading > span { width: 100%; } .detailModes small { width: 100%; margin-left: 0; } }
</style>
