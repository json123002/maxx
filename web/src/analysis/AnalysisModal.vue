<template>
  <div class="anaModal" :class="{ open: visible }" @click="onOverlayClick">
    <div class="anaBox">
      <div v-if="head" class="anaHead">
        <div class="anaTitle">
          <b>{{ head.name }}</b><span class="cd">{{ head.code }}</span>
          <span class="pr"><b>{{ head.priceTxt }}</b> <span :class="head.pctCls">{{ head.pctTxt }}</span></span>
        </div>
        <button class="anaClose" title="关闭" @click="close">×</button>
      </div>
      <div ref="bodyRef" class="anaBody" :class="{ anaBodyFade: fading, anaContentFade: entering }" @click="onBodyClick">
        <div v-if="phase === 'loading'" class="anaLoading">
          <div class="anaSpinner"></div>
          <div class="anaLoadTxt">正在获取日K与资金流数据<span class="anaDots"><span></span><span></span><span></span></span></div>
        </div>
        <template v-else>
          <div v-if="phase === 'error'" class="anaLoading">{{ errorMsg }}</div>
          <div v-if="phase === 'ready'" class="anaBasis">数据：{{ klineSrc }} · {{ basisNote }}</div>
          <!-- 多页签：综合分析 / 趋势波段 / 趋势启动 / 超跌反弹 / 3030战法 / 资金流向 / 基本面 -->
          <div class="anaTabs">
            <button v-for="(m, i) in mods" :key="i" class="anaTab" :class="{ on: i === activeTab }" :data-i="i">{{ m.title.split(" · ")[0] }}</button>
          </div>
          <div class="anaPanes">
            <div v-for="(m, i) in mods" :key="i" class="anaPane" :data-i="i" v-show="i === activeTab">
              <div class="anaSecTitle">{{ m.title }}</div>
              <div v-html="m.html"></div>
            </div>
          </div>
          <div v-if="phase === 'ready'" class="anaDisc">以上为公开行情数据按 skills 各战法思路在浏览器端计算的技术面概率框架，板块强度/公告事件/解禁减持/深度财务未经核验，不构成投资建议，不预测收益。</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
/* ===== 个股分析弹窗(移植自旧 screener-analysis.js 的 openAnalysis/closeAnalysis/renderTabs)===== */
import { ref, onBeforeUnmount } from "vue";
import { message } from "ant-design-vue";
import { fmtN, cls } from "../utils/format";
import { fetchKline, fetchMoneyFlow, fetchIndexKline, KLINE_DAYS } from "./data";
import { smaLast, rsiWilder, macdLast } from "./indicators";
import {
  computeSentiment, stockHeat,
  evalTrend, evalStartup, evalOversold, eval3030, evalMoneyFlow, evalFundamental, evalOverall,
} from "./strategies";

const props = defineProps({
  rows: { type: Array, default: () => [] },   // 筛选结果全量行(find row / computeSentiment / 板块共振共用)
});

const visible = ref(false);
const head = ref(null);
const phase = ref("loading");   // loading / error / ready
const errorMsg = ref("");
const klineSrc = ref("");
const basisNote = ref("");
const mods = ref([]);
const activeTab = ref(0);
const fading = ref(false);      // anaBodyFade:淡出 220ms
const entering = ref(false);    // anaContentFade:淡入 320ms
const bodyRef = ref(null);

function close() {
  visible.value = false;
  unbindEsc();
}

// 关闭:点遮罩(仅点遮罩本身,不穿透到内容)
function onOverlayClick(e) {
  if (e.target === e.currentTarget) close();
}

// Esc 监听在 open 时挂载、关闭时移除(组件常驻,避免重复挂全局监听)
function onKeydown(e) { if (e.key === "Escape") close(); }
let escOn = false;
function bindEsc() { if (!escOn) { document.addEventListener("keydown", onKeydown); escOn = true; } }
function unbindEsc() { if (escOn) { document.removeEventListener("keydown", onKeydown); escOn = false; } }
onBeforeUnmount(unbindEsc);

// 页签切换 + 综合页表格行/芯片跳转(事件委托,v-html 内容里的 .anaChip/.anaJump 也走这里)
function onBodyClick(e) {
  const t = e.target.closest(".anaTab, .anaChip, .anaJump");
  if (!t || t.dataset.i === undefined) return;
  activeTab.value = +t.dataset.i;
  if (bodyRef.value) bodyRef.value.scrollTop = 0;
}

// body 过渡:淡出 loading → 替换内容 → 淡入
async function swapBody(apply) {
  fading.value = true;
  await new Promise(r => setTimeout(r, 220));
  apply();
  fading.value = false;
  entering.value = true;
  setTimeout(() => { entering.value = false; }, 320);
}

async function open(code) {
  const row = props.rows.find(r => r.f12 === code);
  if (!row) { message.warning("未找到该股票数据"); return; }
  head.value = {
    name: row.f14, code: row.f12,
    priceTxt: fmtN(row.f2),
    pctTxt: typeof row.f3 === "number" ? (row.f3 > 0 ? "+" : "") + row.f3.toFixed(2) + "%" : "—",
    pctCls: cls(row.f3),
  };
  activeTab.value = 0;
  mods.value = [];
  errorMsg.value = "";
  basisNote.value = "";
  klineSrc.value = "";
  phase.value = "loading";
  visible.value = true;
  bindEsc();

  let bars = null, mf = null, idx = null, klineErr = null, src = "";
  const jobs = [
    fetchKline(code, KLINE_DAYS).then(r => { bars = r.bars; src = r.source; }).catch(e => { klineErr = e; }),
    fetchMoneyFlow(code).then(m => { mf = m; }).catch(() => {}),
    fetchIndexKline().then(i => { idx = i; }),
  ];
  await Promise.all(jobs);

  if (!bars || bars.length < 30) {
    await swapBody(() => {
      errorMsg.value = `日K数据获取失败${klineErr ? "（" + klineErr.message + "）" : ""}，可能接口限流，请稍后重试`;
      mods.value = [evalFundamental({ row })];
      phase.value = "error";
    });
    return;
  }

  const c = bars.map(b => b.close);
  const price = typeof row.f2 === "number" ? row.f2 : c[c.length - 1]; // 筛选快照现价做实时校正
  const ctx = {
    row, bars, mf, idx, price,
    ma5: smaLast(c, 5), ma10: smaLast(c, 10), ma20: smaLast(c, 20),
    ma60: smaLast(c, 60), rsi: rsiWilder(c, 14), macd: macdLast(c),
  };
  const kDate = bars[bars.length - 1].date;
  // 本地日期串（与 K 线日期同口径，避免 UTC 跨日错位）
  const _t = new Date();
  const today = `${_t.getFullYear()}-${String(_t.getMonth() + 1).padStart(2, "0")}-${String(_t.getDate()).padStart(2, "0")}`;
  const basis = kDate === today ? "日K含今日实时K" : `日K截至 ${kDate}，现价用筛选快照 ${fmtN(price)} 校正`;

  const modsArr = [evalTrend(ctx), evalStartup(ctx), evalOversold(ctx), eval3030(ctx), evalMoneyFlow(ctx), evalFundamental(ctx)];
  // 情绪变量：市场温度（全市场快照+指数量能）· 板块共振（同行业今日表现）· 个股情绪（涨停/连板）
  const senti = computeSentiment(props.rows, idx);
  const peers = row.f100 ? props.rows.filter(r => r.f100 === row.f100) : [];
  const peersUp = peers.filter(r => typeof r.f3 === "number" && r.f3 > 3).length;
  const reso = peers.length ? { name: row.f100, n: peers.length, up: peersUp, ratio: peersUp / peers.length } : null;
  const heat = stockHeat(bars, code);
  const all = [evalOverall(ctx, modsArr, senti, reso, heat), ...modsArr];   // 综合分析页签置顶
  await swapBody(() => {
    klineSrc.value = src;
    basisNote.value = basis;
    mods.value = all;
    phase.value = "ready";
  });
}

defineExpose({ open });
</script>
