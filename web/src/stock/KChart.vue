<script setup>
/* ===== 日K蜡烛图(canvas,无第三方图表库)=====
   - 主图:蜡烛 + MA5/10/20;副图:成交量柱
   - 交互:滚轮缩放(光标锚定) · 左右拖拽平移 · 双击复位 · 区间快捷切换
   - 十字光标:桌面鼠标移动显示 OHLC/涨跌幅/换手/量
   - 主题变量取色,明暗切换/窗口缩放自动重绘 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from "vue";
import { detectPhases, selectVisiblePhase } from "./phases.js";
import { themeMode } from "../utils/theme";

const props = defineProps({
  bars: { type: Array, default: () => [] }, // [{date,open,close,high,low,vol,pct,turnover}]
});

const wrap = ref(null);
const cv = ref(null);
const hoverIdx = ref(-1); // 绝对下标
let ro = null;

// 可视窗口:end 为右边界(开区间),count 为可见根数
const view = reactive({ end: 0, count: 90 });
const RANGES = [
  { name: "3月", n: 60 }, { name: "半年", n: 120 },
  { name: "一年", n: 250 }, { name: "全部", n: 0 },
];
/* ---------- 周期阶段标注 ---------- */
const showPhases = ref(true);
const phases = computed(() => detectPhases(props.bars));
const phaseTypes = reactive({ flat: true, rise: true, bounce: true });
const selectedPhase = shallowRef(null);
const statusText = { forming: '正在形成 · 待确认', ongoing: '已确认 · 延续中', completed: '已确认 · 区间结束' };
const enabledPhases = computed(() => phases.value.filter(p => phaseTypes[p.type]).sort((a, b) => b.e - a.e || b.s - a.s));
const visiblePhases = computed(() => enabledPhases.value.filter(p => p.s < view.end && p.e >= view.end - view.count));
const activePhase = computed(() => selectVisiblePhase(enabledPhases.value, view.end - view.count, view.end, selectedPhase.value, hoverIdx.value));
function focusPhase(event) {
  selectedPhase.value = enabledPhases.value[Number(event.target.value)];
  const ph = selectedPhase.value;
  if (!ph) return;
  hoverIdx.value = -1;
  view.count = Math.min(props.bars.length, Math.max(40, ph.days + 16));
  view.end = Math.min(props.bars.length, Math.max(view.count, ph.e + 9));
  draw();
}
const signed = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
const PHASE_STYLE = {
  flat:   { fill: "rgba(120,144,180,0.10)", border: "rgba(120,144,180,0.55)", tag: "rgba(120,144,180,0.9)" },
  rise:   { fill: "rgba(235,77,75,0.08)",  border: "rgba(235,77,75,0.5)",  tag: "rgba(235,77,75,0.9)" },
  bounce: { fill: "rgba(32,178,130,0.08)", border: "rgba(32,178,130,0.5)", tag: "rgba(32,178,130,0.9)" },
};

function setRange(n) {
  selectedPhase.value = null;
  hoverIdx.value = -1;
  const total = props.bars.length;
  view.count = n ? Math.min(n, total) : total;
  view.end = total;
  draw();
}

const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtP = (v) => (typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—");
const fmtVol = (v) => (v >= 1e8 ? (v / 1e8).toFixed(2) + "亿手" : v >= 1e4 ? (v / 1e4).toFixed(1) + "万手" : Math.round(v) + "手");

function maArr(bars, p) {
  const out = new Array(bars.length).fill(null);
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= p) sum -= bars[i - p].close;
    if (i >= p - 1) out[i] = sum / p;
  }
  return out;
}

// 布局常量(draw 与事件换算共用)
const PAD_L = 8, PAD_R = 56, PAD_T = 52, AXIS_H = 20;
const MIN_BARS = 20;

function draw() {
  const el = cv.value, box = wrap.value;
  if (!el || !box) return;
  const bars = props.bars;
  const dpr = window.devicePixelRatio || 1;
  const W = Math.max(box.clientWidth, 10), H = Math.max(box.clientHeight, 10);
  el.width = W * dpr; el.height = H * dpr;
  el.style.width = W + "px"; el.style.height = H + "px";
  const ctx = el.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  if (!bars.length) return;

  const n = bars.length;
  view.count = Math.min(n, Math.max(MIN_BARS, view.count));
  view.end = Math.max(view.count, Math.min(view.end, n));
  const start = view.end - view.count;
  const slice = bars.slice(start, view.end);
  const m = slice.length;

  const priceH = Math.floor(H * 0.68);
  const volTop = priceH + 16, volH = H - volTop - AXIS_H;
  const plotW = W - PAD_L - PAD_R;
  const step = plotW / m;
  const bw = Math.max(1.5, Math.min(11, step * 0.64));
  const x = (i) => PAD_L + step * (i + 0.5); // i 为 slice 内下标

  // 值域按可视窗口计算(含均线),缩放时自动撑满
  const mas = [5, 10, 20].map((p) => maArr(bars, p));
  let hi = -Infinity, lo = Infinity, vMax = 0;
  slice.forEach((b, i) => {
    const ai = start + i;
    hi = Math.max(hi, b.high); lo = Math.min(lo, b.low); vMax = Math.max(vMax, b.vol);
    mas.forEach((ma) => { if (ma[ai] != null) { hi = Math.max(hi, ma[ai]); lo = Math.min(lo, ma[ai]); } });
  });
  const pad = (hi - lo) * 0.05 || 1; hi += pad; lo -= pad;
  const y = (v) => PAD_T + ((hi - v) / (hi - lo)) * (priceH - PAD_T);
  const vy = (v) => volTop + (1 - v / (vMax || 1)) * volH;

  const cUp = cssVar("--up"), cDown = cssVar("--down");
  const cLine = cssVar("--line"), cDim = cssVar("--dim"), cTxt = cssVar("--txt");
  const cPanel = cssVar("--panel") || "#000";
  const cMA = ["#f5a623", "#b678ff", "#4aa8ff"]; // MA5/10/20

  ctx.font = "10.5px " + (cssVar("--mono") || "monospace");
  ctx.textBaseline = "middle";

  // 网格 + 右价格轴
  ctx.textAlign = "left";
  for (let g = 0; g <= 4; g++) {
    const v = hi - ((hi - lo) * g) / 4;
    const gy = y(v);
    ctx.strokeStyle = cLine; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD_L, gy); ctx.lineTo(W - PAD_R, gy); ctx.stroke();
    ctx.fillStyle = cDim;
    ctx.fillText(fmtP(v), W - PAD_R + 6, gy);
  }
  // 底日期轴(最多 8 个)
  const nLbl = Math.max(1, Math.min(8, m, Math.floor(plotW / 75)));
  ctx.textAlign = "center";
  for (let k = 0; k < nLbl; k++) {
    const i = Math.round((k * (m - 1)) / Math.max(nLbl - 1, 1));
    ctx.fillStyle = cDim;
    ctx.fillText(slice[i].date.slice(2), Math.max(PAD_L + 24, Math.min(W - PAD_R - 24, x(i))), H - AXIS_H / 2);
  }
  // 主副图分隔线
  ctx.strokeStyle = cLine;
  ctx.beginPath(); ctx.moveTo(PAD_L, volTop - 8); ctx.lineTo(W - PAD_R, volTop - 8); ctx.stroke();

  // 周期阶段框(横盘/横盘后上涨/触底反弹,画在蜡烛下层)
  if (showPhases.value) {
    ctx.save();
    ctx.beginPath(); ctx.rect(PAD_L, PAD_T, plotW, priceH - PAD_T); ctx.clip();
    ctx.textAlign = "left";
    const tagEnds = [-Infinity, -Infinity, -Infinity];
    for (const ph of enabledPhases.value) {
      const ps = Math.max(ph.s, start), pe = Math.min(ph.e, view.end - 1);
      if (ps > pe) continue;
      const st = PHASE_STYLE[ph.type];
      const x0 = x(ps - start) - step / 2, x1 = x(pe - start) + step / 2;
      const y0 = Math.max(PAD_T, y(ph.high) - 3), y1 = Math.min(priceH, y(ph.low) + 3);
      ctx.fillStyle = st.fill;
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      ctx.strokeStyle = st.border; ctx.lineWidth = activePhase.value === ph ? 2 : 1;
      ctx.setLineDash(ph.status === 'forming' ? [2, 4] : [6, 3]);
      ctx.strokeRect(x0 + 0.5, y0 + 0.5, Math.max(1, x1 - x0 - 1), Math.max(1, y1 - y0 - 1));
      ctx.setLineDash([]);
      // 信号确认日与历史起点分开画。
      if (ph.confirmedAt != null && ph.confirmedAt >= ps && ph.confirmedAt <= pe) {
        const cx = x(ph.confirmedAt - start);
        ctx.strokeStyle = st.tag; ctx.setLineDash([2, 3]);
        ctx.beginPath(); ctx.moveTo(cx, y0); ctx.lineTo(cx, y1); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = st.tag; ctx.beginPath();
        ctx.moveTo(cx, y0 + 8); ctx.lineTo(cx - 4, y0); ctx.lineTo(cx + 4, y0); ctx.fill();
      }
      const label = ph.label + (ph.status === 'forming' ? ' · 待确认' : '');
      const tw = ctx.measureText(label).width + 10;
      const lane = tagEnds.findIndex(end => end + 4 <= x0);
      if (lane >= 0 && x0 + tw <= W - PAD_R) {
        const ty = PAD_T + 2 + lane * 17;
        tagEnds[lane] = x0 + tw;
        ctx.fillStyle = st.tag; ctx.fillRect(x0, ty, tw, 15);
        ctx.fillStyle = '#fff'; ctx.fillText(label, x0 + 5, ty + 7.5);
      }
    }
    ctx.restore();
  }

  // 蜡烛(红涨绿跌)
  slice.forEach((b, i) => {
    const up = b.close >= b.open;
    const c = up ? cUp : cDown;
    const cx = x(i);
    ctx.strokeStyle = c; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, y(b.high)); ctx.lineTo(cx, y(b.low)); ctx.stroke();
    const yO = y(b.open), yC = y(b.close);
    const top = Math.min(yO, yC), hgt = Math.max(Math.abs(yC - yO), 1);
    if (up) { // 阳线空心
      ctx.fillStyle = cPanel;
      ctx.fillRect(cx - bw / 2, top, bw, hgt);
      ctx.strokeRect(cx - bw / 2, top, bw, hgt);
    } else {
      ctx.fillStyle = c;
      ctx.fillRect(cx - bw / 2, top, bw, hgt);
    }
  });

  // MA 线(跨窗口取绝对下标,保证窗口边缘连线正确)
  mas.forEach((ma, mi) => {
    ctx.strokeStyle = cMA[mi]; ctx.lineWidth = 1.2;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < m; i++) {
      const v = ma[start + i];
      if (v == null) continue;
      const px = x(i), py = y(v);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    }
    ctx.stroke();
  });

  // 成交量柱
  slice.forEach((b, i) => {
    ctx.fillStyle = b.close >= b.open ? cUp : cDown;
    ctx.globalAlpha = 0.75;
    ctx.fillRect(x(i) - bw / 2, vy(b.vol), bw, volTop + volH - vy(b.vol));
    ctx.globalAlpha = 1;
  });

  // MA 图例(左上)
  ctx.textAlign = "left";
  let lx = PAD_L + 2;
  const cur = hoverIdx.value >= start && hoverIdx.value < view.end ? hoverIdx.value : n - 1;
  [5, 10, 20].forEach((p, mi) => {
    const v = mas[mi][cur];
    const t = "MA" + p + " " + (v == null ? "—" : fmtP(v));
    ctx.fillStyle = cMA[mi];
    ctx.fillText(t, lx, 9);
    lx += ctx.measureText(t).width + 14;
  });

  // 十字光标 + 信息层
  if (hoverIdx.value >= start && hoverIdx.value < view.end) {
    const i = hoverIdx.value - start;
    const b = slice[i];
    const cx = x(i), cy = y(b.close);
    ctx.strokeStyle = cDim; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, PAD_T); ctx.lineTo(cx, H - AXIS_H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(PAD_L, cy); ctx.lineTo(W - PAD_R, cy); ctx.stroke();
    ctx.setLineDash([]);
    // 右轴收盘价标签
    const lbl = fmtP(b.close);
    const lw = ctx.measureText(lbl).width + 10;
    ctx.fillStyle = cDim;
    ctx.fillRect(W - PAD_R + 1, cy - 8, lw, 16);
    ctx.fillStyle = cPanel;
    ctx.fillText(lbl, W - PAD_R + 6, cy);
    // 信息行(MA 图例下方)
    const up = b.close >= b.open;
    ctx.fillStyle = cTxt;
    const info = b.date + "  开 " + fmtP(b.open) + "  高 " + fmtP(b.high) +
      "  低 " + fmtP(b.low) + "  收 " + fmtP(b.close);
    ctx.fillText(info, PAD_L + 2, 22);
    let ix = PAD_L + 2 + ctx.measureText(info + "   ").width;
    ctx.fillStyle = up ? cUp : cDown;
    const pctTxt = (isFinite(b.pct) ? (b.pct > 0 ? "+" : "") + b.pct.toFixed(2) + "%" : "—");
    ctx.fillText(pctTxt, ix, 22);
    ix += ctx.measureText(pctTxt + "   ").width;
    ctx.fillStyle = cDim;
    ctx.fillText("量 " + fmtVol(b.vol) +
      (isFinite(b.turnover) ? "  换手 " + b.turnover.toFixed(2) + "%" : ""), ix, 22);
  }
}

/* ---------- 坐标换算 ---------- */
function absIdxFromX(px) {
  const rect = cv.value.getBoundingClientRect();
  const plotW = rect.width - PAD_L - PAD_R;
  const m = view.count;
  const i = Math.floor((px - PAD_L) / (plotW / m));
  return Math.max(0, Math.min(props.bars.length - 1, view.end - view.count + i));
}

/* ---------- 滚轮缩放(光标锚定) ---------- */
function onWheel(e) {
  if (!props.bars.length) return;
  e.preventDefault();
  const rect = cv.value.getBoundingClientRect();
  const px = e.clientX - rect.left;
  const anchor = absIdxFromX(px);           // 光标下的K线
  const ratio = (anchor - (view.end - view.count)) / view.count;
  const factor = e.deltaY > 0 ? 1.18 : 1 / 1.18;
  const n = props.bars.length;
  view.count = Math.min(n, Math.max(MIN_BARS, Math.round(view.count * factor)));
  view.end = Math.max(view.count, Math.min(n, Math.round(anchor + (1 - ratio) * view.count)));
  hoverIdx.value = -1;
  draw();
}

/* ---------- 拖拽平移 / 十字光标 ---------- */
let drag = null;
function onPointerDown(e) {
  if (e.pointerType === "mouse" && e.button !== 0) return;
  drag = { x: e.clientX, end: view.end };
  cv.value.setPointerCapture(e.pointerId);
}
function onPointerMove(e) {
  const rect = cv.value.getBoundingClientRect();
  const px = e.clientX - rect.left;
  if (drag) {
    const step = (rect.width - PAD_L - PAD_R) / view.count;
    const shift = Math.round((drag.x - e.clientX) / step);
    const n = props.bars.length;
    view.end = Math.max(view.count, Math.min(n, drag.end + shift));
    hoverIdx.value = -1;
    draw();
  } else if (e.pointerType === "mouse") {
    hoverIdx.value = absIdxFromX(px);
    draw();
  }
}
function onPointerUp() { drag = null; }
function onLeave() { if (!drag) { hoverIdx.value = -1; draw(); } }
function onDblClick() { setRange(90); } // 双击复位到默认窗口

onMounted(() => {
  view.end = props.bars.length;
  view.count = Math.min(90, props.bars.length || 90);
  draw();
  ro = new ResizeObserver(draw);
  ro.observe(wrap.value);
});
onBeforeUnmount(() => ro && ro.disconnect());
watch(() => props.bars, () => setRange(90));
watch(themeMode, () => setTimeout(draw, 0)); // 等 data-theme 落到 DOM 再取色
watch(phaseTypes, draw);
</script>

<template>
  <div class="kRoot">
  <div ref="wrap" class="kWrap">
    <div class="kRanges">
      <button class="kRange" :class="{ on: showPhases }" @click="showPhases = !showPhases; draw()">周期</button>
      <button v-for="r in RANGES" :key="r.name" class="kRange"
              :class="{ on: r.n ? view.count === Math.min(r.n, bars.length) : view.count === bars.length }"
              @click="setRange(r.n)">{{ r.name }}</button>
    </div>
    <canvas
      ref="cv"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @mouseleave="onLeave"
      @dblclick="onDblClick"
    ></canvas>
    <div v-if="!bars.length" class="kEmpty">K线数据加载失败</div>
  </div>
  <div v-if="showPhases" class="phasePanel">
    <div class="phaseScope">当前视窗识别 {{ visiblePhases.length }} 个阶段 · 历史共 {{ enabledPhases.length }} 个 · 框选为规则识别，非买卖信号</div>
    <div class="phaseFilters">
      <label v-for="(name, type) in { flat: '横盘整理', rise: '横盘后上涨', bounce: '触底反弹' }" :key="type" :class="type">
        <input type="checkbox" v-model="phaseTypes[type]">{{ name }}
      </label>
      <select v-if="enabledPhases.length" aria-label="定位历史阶段" :value="enabledPhases.indexOf(activePhase)" @change="focusPhase">
        <option disabled :value="-1">当前视窗无阶段 · 可选择历史定位</option>
        <option v-for="(ph, i) in enabledPhases" :key="ph.type + ph.s" :value="i">{{ visiblePhases.includes(ph) ? '当前' : '历史' }} · {{ ph.startDate }} · {{ ph.label }}</option>
      </select>
    </div>
    <template v-if="activePhase">
      <div class="phaseSummary"><strong>{{ activePhase.label }}</strong><span>{{ statusText[activePhase.status] }}</span></div>
      <div>{{ activePhase.startDate }} ~ {{ activePhase.endDate }} · {{ activePhase.days }} 个交易日 · 收盘区间涨跌 {{ signed(activePhase.pct) }}</div>
      <div>价格范围 {{ fmtP(activePhase.low) }} ~ {{ fmtP(activePhase.high) }} · 确认日 {{ activePhase.confirmedDate || '待确认' }}
        <span v-if="activePhase.type !== 'flat'"> · 确认日量 / 前5日均量 {{ activePhase.volumeRatio == null ? '暂无' : activePhase.volumeRatio.toFixed(2) + '倍' }}{{ activePhase.volumeRatio == null ? '' : activePhase.volumeRatio >= 1.5 ? '（放量支持）' : '（未达1.5倍）' }}</span>
      </div>
      <div v-if="activePhase.type === 'rise'">前置横盘 {{ activePhase.baseStartDate }} ~ {{ activePhase.baseEndDate }} · 箱顶 {{ fmtP(activePhase.referencePrice) }}</div>
      <div v-if="activePhase.type === 'flat'">平台振幅 {{ activePhase.rangePct.toFixed(1) }}% · {{ activePhase.days < 20 ? '短周期平台（8～19日）' : '中期横盘（20日及以上）' }}</div>
      <div v-if="activePhase.confirmationMethod">确认依据：{{ activePhase.confirmationMethod }}</div>
      <div v-if="activePhase.type === 'rise'">突破阈值 {{ fmtP(activePhase.threshold) }} · 确认后最高收盘涨幅 {{ signed(activePhase.maxGainPct) }} · 回撤阈值 {{ activePhase.pullbackPct.toFixed(1) }}% · {{ activePhase.endReason }}</div>
      <div v-if="activePhase.type === 'bounce'">底部低价 {{ fmtP(activePhase.referencePrice) }} · 低点至区间末收盘反弹 {{ signed(activePhase.reboundPct) }}</div>
    </template>
    <div v-else>{{ !bars.length ? '等待日K数据' : !Object.values(phaseTypes).some(Boolean) ? '请选择阶段类型' : '当前视窗没有符合规则的阶段，可切换半年 / 一年或选择历史定位' }}</div>
    <details><summary>识别规则与确认口径</summary>
      <p>短平台至少8日，中期横盘至少20日；整体振幅≤12%，首尾分组均价偏移≤4%，净位移 / 逐日收盘位移总和≤0.55，以排除单边爬升。突破先越过箱顶加较大者（1.5%箱顶、0.5倍14日平均真实波幅），再满足收盘突破3%、量达前5日均量1.5倍、连续两日站稳中的一项。</p>
      <p>突破后最多跟踪40日；跌回箱顶判为失效，或最高收盘回撤达到确认日冻结阈值（2倍平均真实波幅 / 收盘价，限制8%～15%）结束。反弹需创20日低点、较前20日最高价回落≥15%，至少等待2日，20日内收盘反弹≥8%；创新低或收盘回撤8%结束。终止当日包含在框内。</p>
      <p>箭头与竖虚线标记确认日；起点仅用于历史复盘，待确认区间可能消失。已确认区间可继续延伸，日内未收盘数据仍会变化。不复权数据可能受除权影响。</p>
    </details>
  </div>
  </div>
</template>

<style scoped>
.kRoot { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.kWrap { position: relative; width: 100%; flex: 1; min-height: 160px; overflow: hidden; }
.phasePanel { flex: none; max-height: 185px; overflow: auto; border-top: 1px solid var(--line); padding: 9px 12px; font-size: 11px; line-height: 1.8; color: var(--dim); }
.phaseFilters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin-bottom: 4px; }
.phaseFilters label { display: flex; align-items: center; gap: 3px; cursor: pointer; }
.phaseFilters .flat { color: #7890b4; } .phaseFilters .rise { color: #eb4d4b; } .phaseFilters .bounce { color: #20b282; }
.phaseFilters select { max-width: 100%; background: var(--panel); color: var(--txt); border: 1px solid var(--line); border-radius: 4px; font: inherit; }
.phaseSummary { display: flex; gap: 12px; color: var(--txt); }
.phaseScope { font-size: 11px; margin-bottom: 4px; }
.phasePanel summary { cursor: pointer; } .phasePanel p { margin: 4px 0; }
canvas { display: block; cursor: crosshair; touch-action: pan-y; }
.kRanges {
  position: absolute; top: 28px; right: 62px; z-index: 2;
  display: flex; gap: 2px; background: var(--panel);
  border: 1px solid var(--line); border-radius: 999px; padding: 2px;
}
.kRange {
  background: none; border: none; border-radius: 999px; cursor: pointer;
  color: var(--dim); font-size: 11px; font-family: inherit; padding: 2px 10px;
  transition: color .15s, background .15s;
}
.kRange:hover { color: var(--txt); }
.kRange.on { color: var(--accent); background: var(--accent-dim); }
.kEmpty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--dim); font-size: 13px;
}
</style>
