<script setup>
/* ===== 个股详情页(自研看盘终端,不跳第三方)=====
   全宽布局:顶条(报价/操作) + 左侧K线主区 + 右侧数据栏(关键价位/资金流/概览)。
   数据:后端快照(报价/市值/涨跌停) + 东财日K(K线/均线) + 资金流(近10日主力)。
   「分析」按钮才打开战法分析弹窗;点名称在自选页进的是本页。 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { api, track } from "../api/client";
import { cls, fmtN, fmtYiT } from "../utils/format";
import { fetchKline, fetchMoneyFlow } from "../analysis/data";
import { inWatch, loadWatchCodes, toggleWatch } from "../stores/watchlist";
import AnalysisModal from "../analysis/AnalysisModal.vue";
import KChart from "../stock/KChart.vue";
import MinuteChart from "../stock/MinuteChart.vue";
import { activePersonalSource, loadQuoteSource } from "../stores/quotesource";

const route = useRoute();
const router = useRouter();
const code = route.params.code;

const quote = ref(null);      // 后端快照行(f 字段)
const bars = ref([]);         // 日K
const flows = ref([]);        // 资金流(近10日)
const kSrc = ref("");
const kLoading = ref(true);   // K线取数中(空态显示加载动画,失败才显示"加载失败")
const notFound = ref(false);
const liveSrc = ref("");      // 报价实时来源(自己/公共行情源),空=快照

/* ---------- 图表模式:分时(m)/日K(d) ---------- */
// 分时走启用中的行情源(自己的或公共);默认东财快照无分时,选项置灰,点击提示
const chartMode = ref("d");
const minData = ref(null);    // /api/quote/intraday 返回 {date,prev_close,source,points}
const minLoading = ref(false);
const hasSource = computed(() => !!activePersonalSource());

function pickChart(mode) {
  if (mode === chartMode.value) return;
  if (mode === "m") {
    if (!hasSource.value) {
      message.info("当前接口：东方财富，暂不支持分时线（可在 设置·行情设置 启用自己的行情源）");
      return;
    }
    chartMode.value = "m";
    loadIntraday();
  } else {
    chartMode.value = "d";
  }
}

async function loadIntraday() {
  minLoading.value = true;
  try {
    minData.value = await api("/api/quote/intraday/" + code);
  } catch (err) {
    if (err.message !== "unauthorized") {
      message.error(err.message || "分时数据获取失败");
      chartMode.value = "d";
    }
  } finally {
    minLoading.value = false;
  }
}

/* ---------- 取数 ---------- */
onMounted(async () => {
  loadWatchCodes();
  loadQuoteSource();   // 页签可用性依赖行情源状态(应用启动已拉过,这里兜底)
  try {
    const d = await api("/api/quote/stock/" + code);
    quote.value = d.row;
    track("stock_view", code + " " + (d.row.f14 || ""));
  } catch (err) {
    if (err.message === "unauthorized") return;
    notFound.value = true;
    return;
  }
  // 启用了行情源(自己的或公共) → 报价用其实时字段覆盖快照;失败静默留在快照
  api("/api/quote/realtime?codes=" + code).then((d) => {
    const r = (d.rows || [])[0];
    if (d.live && r && quote.value) {
      Object.assign(quote.value, { f2: r.f2, f3: r.f3, f6: r.f6, f8: r.f8 });
      liveSrc.value = d.source;
    }
  }).catch(() => {});
  // K线/资金流失败不阻塞整页
  fetchKline(code, 250).then((r) => { bars.value = r.bars; kSrc.value = r.source; })
    .catch(() => {})
    .finally(() => { kLoading.value = false; });
  fetchMoneyFlow(code).then((f) => { flows.value = f; }).catch(() => {});
});

/* ---------- 自选 ---------- */
async function onStar() {
  const added = !inWatch(code);
  try {
    await toggleWatch(code, added);
    message.success(added ? "已添加自选" : "已移除自选");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

/* ---------- 分析弹窗 ---------- */
const anaRef = ref(null);
const anaRows = computed(() => (quote.value ? [quote.value] : []));

/* ---------- 派生指标 ---------- */
const ma = (p) => {
  const bs = bars.value;
  if (bs.length < p) return null;
  return bs.slice(-p).reduce((s, b) => s + b.close, 0) / p;
};
const hiLo = (n) => {
  const bs = bars.value.slice(-n);
  if (!bs.length) return [null, null];
  return [Math.max(...bs.map((b) => b.high)), Math.min(...bs.map((b) => b.low))];
};
const hi20 = computed(() => hiLo(20)[0]);
const lo20 = computed(() => hiLo(20)[1]);
const hiY = computed(() => hiLo(250)[0]);
const loY = computed(() => hiLo(250)[1]);

const price = computed(() => quote.value?.f2 ?? bars.value.at(-1)?.close ?? null);
const pct = computed(() => quote.value?.f3 ?? bars.value.at(-1)?.pct ?? null);

// 关键价位:距现价的乖离,辅助判断空间
function off(v) {
  if (v == null || price.value == null) return "";
  const d = (v / price.value - 1) * 100;
  return (d > 0 ? "+" : "") + d.toFixed(1) + "%";
}
const levels = computed(() => {
  const q = quote.value || {};
  return [
    { name: "涨停价", v: q.f350 },
    { name: "跌停价", v: q.f351 },
    { name: "昨收", v: q.f18 },
    { name: "MA5", v: ma(5) },
    { name: "MA10", v: ma(10) },
    { name: "MA20", v: ma(20) },
    { name: "20日高", v: hi20.value },
    { name: "20日低", v: lo20.value },
    { name: "年内高", v: hiY.value },
    { name: "年内低", v: loY.value },
  ];
});

const basics = computed(() => {
  const q = quote.value || {};
  return [
    { name: "成交额", v: fmtYiT(q.f6) },
    { name: "换手率", v: fmtN(q.f8) + "%" },
    { name: "量比", v: fmtN(q.f10) },
    { name: "振幅", v: fmtN(q.f7) + "%" },
    { name: "总市值", v: fmtYiT(q.f20) },
    { name: "流通市值", v: fmtYiT(q.f21) },
    { name: "市盈率", v: fmtN(q.f9, 1) },
    { name: "市净率", v: fmtN(q.f23) },
    { name: "60日涨幅", v: typeof q.f24 === "number" ? q.f24.toFixed(1) + "%" : "—" },
    { name: "年初至今", v: typeof q.f25 === "number" ? q.f25.toFixed(1) + "%" : "—" },
  ];
});

/* ---------- 资金流 ---------- */
const fmtFlow = (v) => {
  const a = Math.abs(v);
  const s = a >= 1e8 ? (v / 1e8).toFixed(2) + "亿" : (v / 1e4).toFixed(0) + "万";
  return v > 0 ? "+" + s : s;
};
const flowMax = computed(() => Math.max(...flows.value.map((f) => Math.abs(f.main)), 1));
const flowSum = computed(() => flows.value.reduce((s, f) => s + f.main, 0));

function goBack() {
  if (window.history.length > 1) router.back();
  else router.push("/watchlist");
}
</script>

<template>
  <div class="stockWrap">
    <!-- ===== 顶条:返回 | 名称 报价 | 自选 分析 ===== -->
    <div class="topBar">
      <button class="ghostBtn" @click="goBack">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        返回
      </button>
      <template v-if="quote">
        <span class="sName">{{ quote.f14 }}</span>
        <span class="sCode">{{ quote.f12 }}</span>
        <span class="sInd">{{ quote.f100 || "—" }}</span>
        <span class="bigPrice" :class="cls(pct)">{{ fmtN(price) }}</span>
        <span class="bigChg" :class="cls(pct)">
          {{ typeof pct === "number" ? (pct > 0 ? "+" : "") + pct.toFixed(2) + "%" : "—" }}
        </span>
        <span v-if="liveSrc" class="liveTag" title="报价来自你在设置里启用的行情源(或他人公开源),其余字段为系统快照">
          <i class="liveTagDot"></i>{{ liveSrc }}
        </span>
      </template>
      <span class="srcNote">{{ kSrc }}</span>
      <span class="topSpacer"></span>
      <button class="starBtn" :class="{ on: inWatch(code) }"
              :title="inWatch(code) ? '移除自选' : '添加自选'" @click="onStar">
        <svg width="16" height="16" viewBox="0 0 24 24" :fill="inWatch(code) ? 'currentColor' : 'none'"
             stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
          <path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z" />
        </svg>
      </button>
      <button class="pill" @click="anaRef && anaRef.open(code)">分析</button>
    </div>

    <div v-if="notFound" class="empty">未找到该股票，可能已退市或代码有误</div>

    <!-- ===== 终端主区:左K线 + 右数据栏 ===== -->
    <div v-else class="termGrid">
      <div class="chartCol">
        <div class="chartTabs">
          <button class="tabBtn" :class="{ on: chartMode === 'm', off: !hasSource }"
                  :title="hasSource ? '5分钟分时,来自启用的行情源' : '需要启用自己的行情源(或公共源)'"
                  @click="pickChart('m')">分时</button>
          <button class="tabBtn" :class="{ on: chartMode === 'd' }" @click="pickChart('d')">日K</button>
        </div>
        <div class="chartBody">
          <MinuteChart v-if="chartMode === 'm'"
                       :points="minData?.points || []" :prev-close="minData?.prev_close ?? null"
                       :date="minData?.date || ''" :source="minData?.source || ''"
                       :loading="minLoading" />
          <KChart v-else :bars="bars" :loading="kLoading" />
        </div>
      </div>

      <aside class="sideCol">
        <!-- 关键价位 -->
        <section class="sideBlk">
          <div class="sideHead">
            <span class="secName">关键价位</span>
            <span class="secNote">距现价</span>
          </div>
          <div class="lvRow" v-for="l in levels" :key="l.name">
            <span class="lvName">{{ l.name }}</span>
            <span class="lvVal">{{ fmtN(l.v) }}</span>
            <span class="lvOff" :class="cls(l.v != null && price != null ? l.v - price : 0)">{{ off(l.v) }}</span>
          </div>
        </section>

        <!-- 资金流向 -->
        <section class="sideBlk" v-if="flows.length">
          <div class="sideHead">
            <span class="secName">资金流向</span>
            <span class="flowSum" :class="cls(flowSum)">累计 {{ fmtFlow(flowSum) }}</span>
          </div>
          <div class="flowRow" v-for="f in flows" :key="f.date">
            <span class="fDate">{{ f.date.slice(5) }}</span>
            <span class="fTrack">
              <span class="fAxis"></span>
              <span class="fBar" :class="f.main >= 0 ? 'up' : 'down'"
                    :style="{
                      width: (Math.abs(f.main) / flowMax * 50) + '%',
                      left: f.main >= 0 ? '50%' : (50 - Math.abs(f.main) / flowMax * 50) + '%',
                    }"></span>
            </span>
            <span class="fVal" :class="cls(f.main)">{{ fmtFlow(f.main) }}</span>
          </div>
          <div class="sideNote">近 {{ flows.length }} 日主力净流入</div>
        </section>

        <!-- 行情概览 -->
        <section class="sideBlk">
          <div class="sideHead"><span class="secName">行情概览</span></div>
          <div class="lvRow" v-for="b in basics" :key="b.name">
            <span class="lvName">{{ b.name }}</span>
            <span class="lvVal">{{ b.v }}</span>
          </div>
        </section>

        <div class="disc">数据来自东方财富公开行情快照与日K，仅作客观参考，不构成投资建议。</div>
      </aside>
    </div>

    <AnalysisModal ref="anaRef" :rows="anaRows" />
  </div>
</template>

<style scoped>
/* ===== 全宽终端布局:内容区撑满,左侧图区自适应,右栏 320px ===== */
.stockWrap {
  height: 100%; display: flex; flex-direction: column; min-height: 0;
}

/* ===== 顶条 ===== */
.topBar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding-bottom: 12px; border-bottom: 1px solid var(--line);
}
.topSpacer { flex: 1; }
.sName { font-size: 17px; font-weight: 650; }
.sCode { color: var(--dim); font-family: var(--mono); font-size: 12.5px; }
.sInd {
  color: var(--dim); font-size: 11.5px; border: 1px solid var(--line);
  border-radius: 999px; padding: 1px 9px;
}
.bigPrice { font-size: 24px; font-weight: 700; font-family: var(--mono); letter-spacing: -.01em; margin-left: 8px; }
.bigChg { font-size: 14px; font-weight: 600; font-family: var(--mono); }
/* 实时报价来源角标(自己的/公共行情源) */
.liveTag {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--accent); font-family: var(--mono);
  border: 1px solid var(--accent); border-radius: 999px; padding: 1px 8px;
}
.liveTagDot {
  width: 5px; height: 5px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}
.srcNote { color: var(--dim); font-size: 11.5px; }
.up { color: var(--up); }
.down { color: var(--down); }
.ghostBtn {
  display: inline-flex; align-items: center; gap: 5px;
  background: none; border: 1px solid var(--line); border-radius: 999px;
  padding: 4px 13px; font-size: 12.5px; font-family: inherit;
  color: var(--dim); cursor: pointer; transition: color .15s, border-color .15s;
}
.ghostBtn:hover { color: var(--txt); border-color: var(--line-strong); }
.starBtn {
  background: none; border: none; cursor: pointer; padding: 4px;
  color: var(--line-strong); line-height: 0; transition: color .15s, transform .1s;
}
.starBtn:hover { transform: scale(1.15); }
.starBtn.on { color: #f5a623; }
.pill {
  background: var(--btn-bg); color: var(--btn-txt);
  border: none; border-radius: 999px; padding: 6px 20px;
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: opacity .15s, transform .1s;
}
.pill:hover { opacity: .88; }
.pill:active { transform: scale(.98); }

/* ===== 主区 ===== */
.termGrid {
  flex: 1; min-height: 0; display: flex; gap: 16px; padding-top: 14px;
}
.chartCol {
  flex: 1; min-width: 0; min-height: 0;
  border: 1px solid var(--line); border-radius: 12px;
  background: var(--panel); overflow: hidden;
  display: flex; flex-direction: column;
}
/* 分时/日K 页签 */
.chartTabs {
  display: flex; gap: 4px; padding: 10px 12px 0; flex-shrink: 0;
}
.tabBtn {
  background: none; border: 1px solid transparent; border-radius: 999px;
  padding: 3px 13px; font-size: 12px; font-family: inherit;
  color: var(--dim); cursor: pointer; transition: color .15s, border-color .15s;
}
.tabBtn:hover { color: var(--txt); }
.tabBtn.on { color: var(--txt); font-weight: 650; border-color: var(--line-strong); }
.tabBtn.off { opacity: .55; }
.chartBody { flex: 1; min-height: 0; }
.sideCol {
  width: 320px; flex-shrink: 0; overflow-y: auto; min-height: 0;
  scrollbar-width: thin; scrollbar-color: var(--scroll) transparent;
}

/* ===== 右栏区块 ===== */
.sideBlk { margin-bottom: 22px; }
.sideHead {
  display: flex; align-items: baseline; gap: 10px;
  padding-bottom: 8px; border-bottom: 1px solid var(--line); margin-bottom: 4px;
}
.secName { font-size: 13.5px; font-weight: 650; letter-spacing: .04em; }
.secName::before {
  content: ""; display: inline-block; width: 3px; height: 11px; border-radius: 2px;
  background: var(--brand-red); margin-right: 7px; vertical-align: -1px;
}
.secNote, .sideNote { color: var(--dim); font-size: 11px; }
.sideNote { margin-top: 6px; }

.lvRow {
  display: flex; align-items: baseline; gap: 8px;
  padding: 6px 2px; border-bottom: 1px solid var(--line);
}
.lvRow:last-child { border-bottom: none; }
.lvName { color: var(--dim); font-size: 12px; width: 52px; flex-shrink: 0; }
.lvVal { font-size: 13px; font-weight: 600; font-family: var(--mono); }
.lvOff { margin-left: auto; font-size: 11px; font-family: var(--mono); color: var(--dim); }

/* ===== 资金流 ===== */
.flowSum { margin-left: auto; font-size: 12px; font-weight: 600; font-family: var(--mono); }
.flowRow {
  display: flex; align-items: center; gap: 10px;
  padding: 5px 2px; border-bottom: 1px solid var(--line);
}
.flowRow:last-of-type { border-bottom: none; }
.fDate { color: var(--dim); font-size: 11px; font-family: var(--mono); width: 38px; flex-shrink: 0; }
.fTrack { position: relative; flex: 1; height: 13px; }
.fAxis { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--line-strong); }
.fBar { position: absolute; top: 1px; bottom: 1px; border-radius: 3px; }
.fBar.up { background: var(--up); }
.fBar.down { background: var(--down); }
.fVal { font-size: 11.5px; font-family: var(--mono); width: 64px; text-align: right; flex-shrink: 0; }

.disc { color: var(--dim); font-size: 11px; line-height: 1.8; padding: 4px 2px 8px; }
.empty { padding: 64px 0; text-align: center; color: var(--dim); }

/* ===== 手机:上下堆叠,图区固定高,页面整体滚动 ===== */
@media (max-width: 900px) {
  .stockWrap { height: auto; }
  .termGrid { flex-direction: column; }
  .chartCol { height: 520px; flex: none; }
  .sideCol { width: auto; overflow: visible; }
  .srcNote { display: none; }
}
</style>
