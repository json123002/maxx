<script setup>
/* ===== 分时图(canvas,无第三方图表库,风格与 KChart 一致)=====
   - 5 分钟粒度收盘折线,横轴固定 09:30–15:00(午休跳过)
   - 昨收虚线基准,现价沿昨收红涨绿跌;副图成交量柱(较前价红绿)
   - 主题变量取色,明暗切换/窗口缩放自动重绘 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { themeMode } from "../utils/theme";

const props = defineProps({
  points: { type: Array, default: () => [] },   // [{t:"09:35",c,v,a}]
  prevClose: { type: Number, default: null },
  date: { type: String, default: "" },          // 交易日 YYYY-MM-DD
  source: { type: String, default: "" },
  loading: { type: Boolean, default: false },
});

const wrap = ref(null);
const cv = ref(null);
let ro = null;

const PAD_L = 10, PAD_R = 64, PAD_T = 14, AXIS_H = 20;
const OPEN_MIN = 9 * 60 + 30;        // 09:30 起算
const DAY_MIN = 240;                 // 全天 240 分钟(午休不计)
// "09:35" → 当日交易分钟位(午休折叠:13:00 视作第 121 分钟)
function slotOf(t) {
  const [hh, mm] = t.split(":").map(Number);
  const m = hh * 60 + mm;
  return m <= 11 * 60 + 30 ? m - OPEN_MIN : m - 13 * 60 + 120;
}
const fmtP = (v) => (typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—");
const fmtVol = (v) =>
  v >= 1e8 ? (v / 1e8).toFixed(2) + "亿" : v >= 1e4 ? (v / 1e4).toFixed(1) + "万" : String(Math.round(v || 0));

const hoverIdx = ref(-1);
function onMove(ev) {
  const box = cv.value.getBoundingClientRect();
  const W = box.width, plotW = W - PAD_L - PAD_R;
  const idx = Math.round(((ev.clientX - box.left - PAD_L) / plotW) * DAY_MIN / 5 - 1);
  hoverIdx.value = idx >= 0 && idx < props.points.length ? idx : -1;
}

function draw() {
  const el = cv.value, box = wrap.value;
  if (!el || !box) return;
  const pts = props.points;
  const dpr = window.devicePixelRatio || 1;
  const W = Math.max(box.clientWidth, 10), H = Math.max(box.clientHeight, 10);
  el.width = W * dpr; el.height = H * dpr;
  el.style.width = W + "px"; el.style.height = H + "px";
  const ctx = el.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  if (!pts.length) return;

  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const line = css("--line"), dim = css("--dim"), txt = css("--txt");
  const up = css("--up"), down = css("--down"), mono = css("--mono") || "monospace";
  const pc = props.prevClose ?? pts[0].c;
  const last = pts[pts.length - 1].c;
  const lineColor = last >= pc ? up : down;

  const plotW = W - PAD_L - PAD_R;
  const priceH = Math.floor((H - AXIS_H) * 0.74);
  const volTop = priceH + 18, volH = H - AXIS_H - volTop;
  const X = (m) => PAD_L + (m / DAY_MIN) * plotW;   // 分钟位 → x
  ctx.font = "11px " + mono;

  /* 价格刻度:区间含昨收,上下留 8% 余量 */
  const lo = Math.min(pc, ...pts.map((p) => p.c));
  const hi = Math.max(pc, ...pts.map((p) => p.c));
  const span = Math.max(hi - lo, pc * 0.002, 0.01);
  const y0 = lo - span * 0.08, y1 = hi + span * 0.08;
  const Y = (v) => PAD_T + (1 - (v - y0) / (y1 - y0)) * (priceH - PAD_T);

  // 横向网格 + 左右价格刻度
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const v = y0 + ((y1 - y0) * i) / 4, y = Y(v);
    ctx.strokeStyle = line; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD_L, y); ctx.lineTo(W - PAD_R, y); ctx.stroke();
    ctx.fillStyle = dim;
    ctx.fillText(v.toFixed(2), W - PAD_R + 6, y);
  }
  // 昨收虚线(价格区全宽)
  const yp = Y(pc);
  ctx.strokeStyle = dim; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(PAD_L, yp); ctx.lineTo(W - PAD_R, yp); ctx.stroke();
  ctx.setLineDash([]);
  // 竖向网格:整点时刻
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (const [m, lab] of [[0, "09:30"], [60, "10:30"], [120, "11:30/13:00"], [180, "14:00"], [240, "15:00"]]) {
    ctx.strokeStyle = line;
    ctx.beginPath(); ctx.moveTo(X(m), PAD_T); ctx.lineTo(X(m), H - AXIS_H); ctx.stroke();
    ctx.fillStyle = dim;
    ctx.fillText(lab, Math.min(Math.max(X(m), 24), W - PAD_R - 10), H - AXIS_H + 5);
  }

  /* 价格折线 + 渐变填充 */
  const grad = ctx.createLinearGradient(0, PAD_T, 0, priceH);
  grad.addColorStop(0, last >= pc ? "rgba(235,77,75,.16)" : "rgba(32,178,130,.16)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.beginPath();
  pts.forEach((p, i) => { const x = X(slotOf(p.t)), y = Y(p.c); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = lineColor; ctx.lineWidth = 1.6; ctx.lineJoin = "round"; ctx.stroke();
  ctx.lineTo(X(slotOf(pts[pts.length - 1].t)), priceH);
  ctx.lineTo(X(slotOf(pts[0].t)), priceH);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  /* 副图:成交量柱,较前一点红绿 */
  const vMax = Math.max(...pts.map((p) => p.v || 0), 1);
  const bw = Math.max(1.5, (plotW / DAY_MIN) * 5 * 0.6);
  pts.forEach((p, i) => {
    const prev = i ? pts[i - 1].c : pc;
    const x = X(slotOf(p.t));
    const h = Math.max(1, ((p.v || 0) / vMax) * volH);
    ctx.fillStyle = p.c >= prev ? up : down;
    ctx.globalAlpha = 0.75;
    ctx.fillRect(x - bw / 2, volTop + volH - h, bw, h);
    ctx.globalAlpha = 1;
  });

  /* 最新价:圆点 + 右侧价签(涨跌幅) */
  const lx = X(slotOf(pts[pts.length - 1].t)), ly = Y(last);
  ctx.fillStyle = lineColor;
  ctx.beginPath(); ctx.arc(lx, ly, 3, 0, Math.PI * 2); ctx.fill();
  const tag = fmtP(last), ty = Math.min(Math.max(ly, PAD_T + 7), priceH - 7);
  ctx.fillStyle = lineColor;
  ctx.fillRect(W - PAD_R + 2, ty - 8, PAD_R - 4, 16);
  ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(tag, W - PAD_R / 2, ty);

  /* 十字光标 + 信息行 */
  if (hoverIdx.value >= 0 && hoverIdx.value < pts.length) {
    const p = pts[hoverIdx.value], x = X(slotOf(p.t));
    ctx.strokeStyle = dim; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(x, PAD_T); ctx.lineTo(x, H - AXIS_H); ctx.stroke();
    ctx.setLineDash([]);
    const chg = pc ? ((p.c / pc - 1) * 100) : 0;
    ctx.fillStyle = txt; ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillText(p.t, PAD_L + 2, PAD_T + 2);
    ctx.fillStyle = p.c >= pc ? up : down;
    ctx.fillText(fmtP(p.c) + "  " + (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%  量 " + fmtVol(p.v),
      PAD_L + 40, PAD_T + 2);
  }
}

onMounted(() => {
  ro = new ResizeObserver(() => draw());
  ro.observe(wrap.value);
  draw();
});
onBeforeUnmount(() => ro && ro.disconnect());
watch(() => [props.points, props.prevClose, themeMode.value], () => draw(), { deep: true });
</script>

<template>
  <div class="mcWrap" ref="wrap">
    <div class="mcHead">
      <span class="mcTitle">分时 · 5分钟</span>
      <span v-if="date" class="mcDate">{{ date }}</span>
      <span v-if="source" class="mcSrc">{{ source }}</span>
    </div>
    <canvas ref="cv" class="mcCv" @mousemove="onMove" @mouseleave="hoverIdx = -1"></canvas>
    <div v-if="loading" class="mcHint">分时数据加载中…</div>
    <div v-else-if="!points.length" class="mcHint">暂无分时数据</div>
  </div>
</template>

<style scoped>
.mcWrap {
  position: relative; width: 100%; height: 100%;
  display: flex; flex-direction: column; min-height: 0;
}
.mcHead {
  display: flex; align-items: baseline; gap: 10px;
  padding: 12px 14px 4px; flex-shrink: 0;
}
.mcTitle { font-size: 12.5px; font-weight: 650; letter-spacing: .04em; }
.mcTitle::before {
  content: ""; display: inline-block; width: 3px; height: 10px; border-radius: 2px;
  background: var(--brand-red); margin-right: 6px; vertical-align: -1px;
}
.mcDate, .mcSrc { color: var(--dim); font-size: 11px; font-family: var(--mono); }
.mcCv { flex: 1; min-height: 0; display: block; cursor: crosshair; }
.mcHint {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--dim); font-size: 12.5px; pointer-events: none;
}
</style>
