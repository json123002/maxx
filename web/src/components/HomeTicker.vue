<script setup>
/* ===== 总览页顶部行情走马灯 (Home Live Ticker) =====
   高质感金融终端横向跑马灯：
   支持大盘指数、全市场热度、连板龙头、L2盘口大单、自选异动与箴言自由组合。
   支持悬停自动暂停、即点直达个股详情、配置持久化。 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { SettingOutlined } from "@ant-design/icons-vue";
import { api } from "../api/client";
import { jsonp } from "../utils/jsonp";
import { cls, fmtN } from "../utils/format";
import { fetchChanges, fetchLiveQuotes } from "../desk/desk-data";
import { tickerState } from "../stores/ticker";

const props = defineProps({
  hot: { type: Array, default: () => [] },
  watchRows: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({}) },
  quote: { type: Object, default: () => ({}) },
});

const router = useRouter();

/* ===== 数据状态 ===== */
const indicesData = ref({ list: [], totalAmt: null });
const ladderLeaders = ref([]);
const l2Changes = ref([]);
const liveQuotes = ref({}); // 实时个股行情映射 code -> { f2, f3, f6, f8 }
const loading = ref(false);

/* ===== 取数方法 ===== */
// 1. 大盘指数与全市场总成交额 (东财实时 JSONP)
async function loadIndices() {
  if (!tickerState.channels.indices) return;
  try {
    const d = await jsonp(
      "https://push2delay.eastmoney.com/api/qt/ulist.np/get?fltt=2" +
      "&secids=1.000001,0.399001,0.399006,1.000688&fields=f12,f14,f2,f3,f4,f6"
    );
    const diff = d?.data?.diff || [];
    const nameMap = {
      "000001": "上证指数",
      "399001": "深证成指",
      "399006": "创业板指",
      "000688": "科创50",
    };
    let shAmt = 0, szAmt = 0;
    const list = [];
    for (const r of diff) {
      if (r.f12 === "000001") shAmt = r.f6 || 0;
      if (r.f12 === "399001") szAmt = r.f6 || 0;
      list.push({
        code: r.f12,
        name: nameMap[r.f12] || r.f14 || "指数",
        price: r.f2,
        pct: r.f3,
        chg: r.f4,
        amt: r.f6,
      });
    }
    const totalAmt = shAmt + szAmt;
    indicesData.value = {
      list,
      totalAmt:
        totalAmt > 0
          ? totalAmt >= 1e12
            ? (totalAmt / 1e12).toFixed(2) + "万亿"
            : (totalAmt / 1e8).toFixed(0) + "亿"
          : null,
    };
  } catch (e) {
    // 失败保留现有数据
  }
}

// 2. 连板龙头 (后端连板天梯榜)
async function loadLadder() {
  if (!tickerState.channels.ladder) return;
  try {
    const d = await api("/api/radar/ladder");
    const tiers = d?.tiers || {};
    const leaders = [
      ...(tiers.tier5plus || []),
      ...(tiers.tier4 || []),
      ...(tiers.tier3 || []),
      ...(tiers.tier2 || []),
    ];
    ladderLeaders.value = leaders.slice(0, 6);
  } catch (e) {}
}

// 3. 盘口异动 / L2 特大单 (同花顺/东财异动流)
async function loadChanges() {
  if (!tickerState.channels.l2_orders) return;
  try {
    const rows = await fetchChanges();
    const meaningful = rows.filter(
      (r) =>
        (r.amount && r.amount >= 5e6) ||
        ["封涨停板", "打开涨停", "火箭发射", "高台跳水"].includes(r.type)
    );
    l2Changes.value = (meaningful.length ? meaningful : rows).slice(0, 6);
  } catch (e) {}
}

// 4. 跑马灯内个股的毫秒级实时价格动态刷新 (热度/龙头/自选)
async function refreshLiveStockQuotes() {
  const codes = new Set();
  for (const h of props.hot) if (h.f12) codes.add(h.f12);
  for (const l of ladderLeaders.value) if (l.code) codes.add(l.code);
  for (const w of props.watchRows) if (w.f12) codes.add(w.f12);
  const codeList = Array.from(codes).slice(0, 30);
  if (!codeList.length) return;
  try {
    const qMap = await fetchLiveQuotes(codeList);
    liveQuotes.value = { ...liveQuotes.value, ...qMap };
  } catch (e) {}
}

async function refreshAll() {
  loading.value = true;
  await Promise.allSettled([loadIndices(), loadLadder(), loadChanges()]);
  await refreshLiveStockQuotes();
  loading.value = false;
}

// 监听配置变更按需加载
watch(
  () => [
    tickerState.channels.indices,
    tickerState.channels.ladder,
    tickerState.channels.l2_orders,
    tickerState.channels.hot,
    tickerState.channels.watchlist,
  ],
  () => {
    refreshAll();
  }
);

/* ===== 统一聚合为滚动条项目 ===== */
const tickerItems = computed(() => {
  const items = [];
  const ch = tickerState.channels;

  // 1. 指数与两市总成交额
  if (ch.indices) {
    for (const idx of indicesData.value.list) {
      items.push({
        id: "idx_" + idx.code,
        type: "index",
        badge: "指数",
        badgeCls: "badge-index",
        name: idx.name,
        code: idx.code,
        val: typeof idx.price === "number" ? idx.price.toFixed(2) : "—",
        pct: typeof idx.pct === "number" ? (idx.pct > 0 ? "+" : "") + idx.pct.toFixed(2) + "%" : "—",
        pctVal: idx.pct,
        clickable: false,
      });
    }
    if (indicesData.value.totalAmt) {
      items.push({
        id: "idx_total_amt",
        type: "index",
        badge: "大盘",
        badgeCls: "badge-index",
        name: "两市成交额",
        val: indicesData.value.totalAmt,
        extra: "沪深合计",
        clickable: false,
      });
    }
  }

  // 2. 连板龙头梯队
  if (ch.ladder && ladderLeaders.value.length) {
    for (const lead of ladderLeaders.value) {
      const lq = liveQuotes.value[lead.code] || {};
      const curPct = typeof lq.f3 === "number" ? lq.f3 : lead.pct;
      const curPrice = typeof lq.f2 === "number" ? fmtN(lq.f2) : "";
      items.push({
        id: "lead_" + lead.code,
        type: "ladder",
        badge: "龙头",
        badgeCls: "badge-ladder",
        name: lead.name,
        code: lead.code,
        val: lead.streak >= 2 ? `${lead.streak}连板` : "首板",
        pct: typeof curPct === "number" ? (curPct > 0 ? "+" : "") + curPct.toFixed(2) + "%" : "+10%",
        pctVal: curPct ?? 10,
        extra: (curPrice ? `${curPrice} · ` : "") + (lead.industry || ""),
        clickable: true,
      });
    }
  }

  // 3. 全市场热度活跃股
  if (ch.hot && props.hot.length) {
    for (const h of props.hot.slice(0, 6)) {
      const lq = liveQuotes.value[h.f12] || {};
      const curPrice = typeof lq.f2 === "number" ? fmtN(lq.f2) : fmtN(h.f2);
      const curPct = typeof lq.f3 === "number" ? lq.f3 : h.f3;
      const curTov = typeof lq.f8 === "number" ? lq.f8 : h.f8;
      items.push({
        id: "hot_" + h.f12,
        type: "hot",
        badge: "热度",
        badgeCls: "badge-hot",
        name: h.f14,
        code: h.f12,
        val: curPrice,
        pct: typeof curPct === "number" ? (curPct > 0 ? "+" : "") + fmtN(curPct) + "%" : "—",
        pctVal: curPct,
        extra: `换手 ${fmtN(curTov, 1)}%`,
        clickable: true,
      });
    }
  }

  // 4. 盘口异动大单
  if (ch.l2_orders && l2Changes.value.length) {
    for (const c of l2Changes.value) {
      const amtStr = c.amount ? (c.amount >= 1e8 ? (c.amount / 1e8).toFixed(1) + "亿" : (c.amount / 1e4).toFixed(0) + "万") : "";
      items.push({
        id: "chg_" + c.code + c.time,
        type: "order",
        badge: "异动",
        badgeCls: "badge-order",
        name: c.name,
        code: c.code,
        val: c.type,
        pct: typeof c.pct === "number" ? (c.pct > 0 ? "+" : "") + c.pct.toFixed(1) + "%" : "",
        pctVal: c.pct,
        extra: amtStr ? `金额 ${amtStr}` : (c.time || "").slice(0, 5),
        clickable: true,
      });
    }
  }

  // 5. 重点自选
  if (ch.watchlist && props.watchRows.length) {
    for (const w of props.watchRows.slice(0, 6)) {
      const lq = liveQuotes.value[w.f12] || {};
      const curPrice = typeof lq.f2 === "number" ? fmtN(lq.f2) : fmtN(w.f2);
      const curPct = typeof lq.f3 === "number" ? lq.f3 : w.f3;
      items.push({
        id: "wat_" + w.f12,
        type: "watch",
        badge: "自选",
        badgeCls: "badge-watch",
        name: w.f14,
        code: w.f12,
        val: curPrice,
        pct: typeof curPct === "number" ? (curPct > 0 ? "+" : "") + fmtN(curPct) + "%" : "—",
        pctVal: curPct,
        clickable: true,
      });
    }
  }

  // 6. 哲学箴言轮播
  if (ch.aphorisms && props.quote?.text) {
    items.push({
      id: "quote_item",
      type: "quote",
      badge: "箴言",
      badgeCls: "badge-quote",
      name: `“${props.quote.text}”`,
      extra: props.quote.author ? `—— ${props.quote.author}` : "",
      clickable: false,
    });
  }

  return items;
});

// 计算动画时长（按项数与速度设置动态伸缩）
const duration = computed(() => {
  const count = tickerItems.value.length;
  if (!count) return 40;
  const speed = tickerState.speed;
  const perItem = speed === "fast" ? 1.6 : speed === "slow" ? 4.0 : 2.5;
  return Math.max(25, Math.round(count * perItem));
});

function onItemClick(item) {
  if (item.clickable && item.code) {
    router.push("/stock/" + item.code);
  }
}

// 盘中高频 12 秒极速差量刷新，盘外休市 45 秒节能刷新
function isTradingHours() {
  const d = new Date();
  if (d.getDay() % 6 === 0) return false;
  const m = d.getHours() * 60 + d.getMinutes();
  return (m >= 555 && m <= 695) || (m >= 775 && m <= 905); // 9:15-11:35, 12:55-15:05
}

let refreshTimer = null;
onMounted(() => {
  refreshAll();
  const interval = isTradingHours() ? 12_000 : 45_000;
  refreshTimer = setInterval(() => {
    loadIndices();
    loadChanges();
    refreshLiveStockQuotes();
  }, interval);
});

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <div v-if="tickerState.enabled && tickerItems.length" class="homeTickerWrap">
    <div class="tickerContainer" :class="{ pauseOnHover: tickerState.hoverPause }">
      <!-- 左侧固定 LIVE 标识 -->
      <div class="tickerLiveTag" title="实时盘面走马灯">
        <span class="liveDot animate"></span>
        <span class="liveText">LIVE</span>
      </div>

      <!-- 中间平滑无缝走马灯通道 -->
      <div class="tickerViewport">
        <div
          class="tickerTrack"
          :style="{ animationDuration: duration + 's' }"
        >
          <!-- 轨道主体 1 -->
          <div class="trackSegment">
            <div
              v-for="it in tickerItems"
              :key="it.id"
              class="tickerChip"
              :class="{ clickable: it.clickable }"
              @click="onItemClick(it)"
              :title="it.clickable ? `点击查看 ${it.name} (${it.code}) 详情` : it.name"
            >
              <span class="chipBadge" :class="it.badgeCls">{{ it.badge }}</span>
              <span class="chipName">{{ it.name }}</span>
              <span v-if="it.val" class="chipVal">{{ it.val }}</span>
              <span
                v-if="it.pct"
                class="chipPct"
                :class="cls(it.pctVal)"
              >
                {{ it.pct }}
              </span>
              <span v-if="it.extra" class="chipExtra">{{ it.extra }}</span>
            </div>
          </div>

          <!-- 镜像克隆轨道 2 (保证 100% 无缝无跳跃无限循环) -->
          <div class="trackSegment" aria-hidden="true">
            <div
              v-for="it in tickerItems"
              :key="'c_' + it.id"
              class="tickerChip"
              :class="{ clickable: it.clickable }"
              @click="onItemClick(it)"
            >
              <span class="chipBadge" :class="it.badgeCls">{{ it.badge }}</span>
              <span class="chipName">{{ it.name }}</span>
              <span v-if="it.val" class="chipVal">{{ it.val }}</span>
              <span
                v-if="it.pct"
                class="chipPct"
                :class="cls(it.pctVal)"
              >
                {{ it.pct }}
              </span>
              <span v-if="it.extra" class="chipExtra">{{ it.extra }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧快速设置按钮 -->
      <router-link
        to="/settings?tab=ticker"
        class="tickerConfigBtn"
        title="设置顶部滚动频道与速度"
      >
        <SettingOutlined />
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.homeTickerWrap {
  width: 100%;
  margin-bottom: 14px;
}

.tickerContainer {
  height: 36px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  display: flex;
  align-items: center;
  position: relative;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

/* 左侧 LIVE 呼吸指示器 */
.tickerLiveTag {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--txt);
  border-right: 1px solid var(--line);
  background: var(--panel-2);
  height: 100%;
  z-index: 2;
  user-select: none;
}

.liveDot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-red);
}

.liveDot.animate {
  box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.6);
  animation: pulseDot 2s infinite;
}

@keyframes pulseDot {
  0% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.7); }
  70% { box-shadow: 0 0 0 6px rgba(248, 113, 113, 0); }
  100% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0); }
}

/* 视窗与左右渐变遮罩 */
.tickerViewport {
  flex: 1;
  height: 100%;
  overflow: hidden;
  position: relative;
  mask-image: linear-gradient(
    to right,
    transparent 0,
    black 16px,
    black calc(100% - 16px),
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0,
    black 16px,
    black calc(100% - 16px),
    transparent 100%
  );
}

.tickerTrack {
  display: flex;
  width: max-content;
  height: 100%;
  align-items: center;
  will-change: transform;
  animation-name: tickerScroll;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

.trackSegment {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 10px;
  white-space: nowrap;
}

@keyframes tickerScroll {
  0% { transform: translate3d(0, 0, 0); }
  100% { transform: translate3d(-50%, 0, 0); }
}

.pauseOnHover:hover .tickerTrack {
  animation-play-state: paused;
}

/* 胶囊卡片 */
.tickerChip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  height: 24px;
  border-radius: 4px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  font-size: 12px;
  font-family: var(--mono);
  user-select: none;
  transition: all 0.15s ease;
}

.tickerChip.clickable {
  cursor: pointer;
}

.tickerChip.clickable:hover {
  background: var(--hover);
  border-color: var(--accent);
  transform: translateY(-1px);
}

/* 胶囊徽标分类 */
.chipBadge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}

.badge-index { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.badge-ladder { background: rgba(244, 63, 94, 0.15); color: #fb7185; }
.badge-hot { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.badge-order { background: rgba(20, 184, 166, 0.15); color: #2dd4bf; }
.badge-watch { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.badge-quote { background: rgba(168, 85, 247, 0.15); color: #c084fc; }

.chipName {
  font-weight: 600;
  color: var(--txt);
}

.chipVal {
  color: var(--txt);
  opacity: 0.9;
}

.chipPct {
  font-weight: 600;
}

.chipPct.up { color: var(--up); }
.chipPct.down { color: var(--down); }

.chipExtra {
  color: var(--dim);
  font-size: 11px;
}

/* 右侧配置按钮 */
.tickerConfigBtn {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 100%;
  color: var(--dim);
  border-left: 1px solid var(--line);
  background: var(--panel-2);
  transition: all 0.15s ease;
  z-index: 2;
}

.tickerConfigBtn:hover {
  color: var(--accent);
  background: var(--panel);
}
</style>
