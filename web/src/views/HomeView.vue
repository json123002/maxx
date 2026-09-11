<template>
  <div class="home">
    <!-- ===== 刊头：日期 + 问候 + 数据快照时间 ===== -->
    <header class="mast">
      <div>
        <div class="mastDate">{{ dateStr }}</div>
        <h1 class="mastHi">{{ greeting }}，{{ authState.user?.username }}</h1>
      </div>
      <div v-if="fetchedAt" class="mastMeta" :class="{ stale }">
        <i class="liveDot"></i>
        {{ stale ? "快照待更新" : "数据更新于" }} {{ fetchedAt }} · {{ source || "东方财富" }}
      </div>
    </header>

    <!-- ===== 市场脉搏 ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">市场脉搏</span>
        <span class="secEn">Market Pulse</span>
      </div>
      <div class="pulse">
        <!-- 情绪温度 -->
        <div class="pTemp" :title="sentiTitle">
          <div class="pTempNum" :class="'lv' + senti.lv">{{ senti.temp ?? "—" }}</div>
          <div class="pTempCap">情绪温度 · {{ senti.level || "—" }}</div>
          <div class="pTempTrack"><i :class="'lv' + senti.lv" :style="{ width: (senti.temp ?? 0) + '%' }"></i></div>
        </div>
        <!-- 涨跌家数 -->
        <div class="pBreadth">
          <div class="bNums">
            <span><b class="up">{{ stats.up ?? "—" }}</b> 上涨</span>
            <span><b class="down">{{ stats.down ?? "—" }}</b> 下跌</span>
          </div>
          <div class="bBar">
            <i class="up" :style="{ width: upPct + '%' }"></i>
            <i class="down" :style="{ width: 100 - upPct + '%' }"></i>
          </div>
          <div class="bCap">两市共 {{ stats.valid ?? "—" }} 只有效个股<span v-if="stats.flat != null"> · 平盘 {{ stats.flat }}</span></div>
        </div>
        <!-- 涨跌停 -->
        <div class="pLimits">
          <div class="lItem"><b class="up">{{ stats.limit_up ?? "—" }}</b><span>涨停</span></div>
          <div class="lSep"></div>
          <div class="lItem"><b class="down">{{ stats.limit_down ?? "—" }}</b><span>跌停</span></div>
          <div class="lSep"></div>
          <div class="lItem"><b>{{ stats.big_down ?? "—" }}</b><span>大跌 &gt;5%</span></div>
        </div>
      </div>
    </section>

    <div class="cols">
      <!-- ===== 选股工具 ===== -->
      <section class="blk">
        <div class="secHead">
          <span class="secName">选股工具</span>
          <span class="secEn">Toolkit</span>
        </div>
        <div class="tools">
          <div v-for="(f, i) in features" :key="f.title" class="tool" :class="{ off: !f.path }"
               @click="f.path && $router.push(f.path)">
            <span class="tIdx">{{ String(i + 1).padStart(2, "0") }}</span>
            <span class="tMain">
              <span class="tTitle">
                <component :is="f.icon" class="tIcon" />{{ f.title }}
              </span>
              <span class="tDesc">{{ f.desc }}</span>
            </span>
            <span v-if="f.path" class="tArrow">→</span>
            <span v-else class="tSoon">即将上线</span>
          </div>
        </div>
      </section>

      <!-- ===== 换手活跃榜(主板·综合评分) ===== -->
      <section class="blk">
        <div class="secHead">
          <span class="secName">活跃精选</span>
          <span class="secEn">主板 · 综合</span>
          <router-link to="/screener" class="secMore">进入筛选 →</router-link>
        </div>
        <div v-if="hot.length" class="hot">
          <a v-for="(s, i) in hot" :key="s.f12" class="hRow" :href="quoteUrl(s.f12)" target="_blank" rel="noopener">
            <span class="hIdx">{{ i + 1 }}</span>
            <span class="hName">{{ s.f14 }}<i class="hCode">{{ s.f12 }}</i><span v-if="s.limit_up === 1" class="lmBadge up">涨停</span><span v-else-if="s.limit_down === 1" class="lmBadge down">跌停</span></span>
            <span class="hPx" :class="cls(s.f3)">{{ fmtN(s.f2) }}</span>
            <span class="hChg" :class="cls(s.f3)">{{ s.f3 > 0 ? "+" : "" }}{{ fmtN(s.f3) }}%</span>
            <span class="hTov">{{ fmtN(s.f8, 1) }}%</span>
          </a>
        </div>
        <div v-else class="hEmpty">暂无快照数据</div>
      </section>
    </div>

    <!-- ===== 我的自选(用户最关心的问题:我的股票今天怎么样) ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">我的自选</span>
        <span class="secEn">Watchlist</span>
        <router-link to="/watchlist" class="secMore">管理自选 →</router-link>
      </div>
      <div v-if="watchRows.length" class="watchStrip">
        <router-link v-for="r in watchRows" :key="r.f12" class="wCard" :to="'/stock/' + r.f12">
          <span class="wName">{{ r.f14 }}
            <span v-if="r.limit_up === 1" class="lmBadge up">涨停</span>
            <span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span>
          </span>
          <span class="wNums">
            <b :class="cls(r.f3)">{{ typeof r.f3 === "number" ? (r.f3 > 0 ? "+" : "") + fmtN(r.f3) + "%" : "—" }}</b>
            <i class="wTov">换手 {{ fmtN(r.f8) }}%</i>
          </span>
        </router-link>
      </div>
      <div v-else class="watchEmpty">
        还没有自选股，去 <router-link to="/watchlist">添加自选</router-link> 或在筛选结果里点 ★
      </div>
    </section>

    <!-- ===== 免责声明 ===== -->
    <footer class="disclaimer">
      <span>
        数据来自东方财富，页面内容仅为客观数据的整理与展示，不构成任何推荐或投资建议。
        市场有风险，决策需独立。
      </span>
      <span class="ver">v{{ version }}</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import {
  FundViewOutlined, FireOutlined, CrownOutlined, FundOutlined, RocketOutlined,
} from "@ant-design/icons-vue";
import { api } from "../api/client";
import { authState } from "../stores/auth";
import { fmtN, cls, quoteUrl } from "../utils/format";
import { version } from "../../package.json";

// 功能入口:与登录页转盘同一套选题,后续功能上线时补上 path 即可
const features = [
  { title: "换手率筛选", icon: FundViewOutlined, path: "/screener",
    desc: "量价先行,按换手率/涨跌幅/行业/自定义指标一键锁定活跃强势股。" },
  { title: "涨停雷达", icon: FireOutlined, path: "",
    desc: "捕捉涨停基因,站上市场最强风口。" },
  { title: "龙头战法", icon: CrownOutlined, path: "",
    desc: "主线合力所向,骑上龙头不放手。" },
  { title: "主力护航", icon: FundOutlined, path: "",
    desc: "主力资金流向一目了然,跟庄不追高。" },
  { title: "趋势长红", icon: RocketOutlined, path: "",
    desc: "顺势而为,账户长红,一路长红。" },
];

// ===== 刊头:日期 / 星期 / 分时段问候 =====
const now = new Date();
const WEEK = "日一二三四五六";
const dateStr = `${now.getFullYear()} 年 ${now.getMonth() + 1} 月 ${now.getDate()} 日 · 星期${WEEK[now.getDay()]}`;
const greeting = computed(() => {
  const hh = now.getHours();
  if (hh < 6) return "夜深了";
  if (hh < 11) return "早上好";
  if (hh < 14) return "中午好";
  if (hh < 18) return "下午好";
  return "晚上好";
});

// ===== 行情快照:meta(统计) + list(活跃榜) =====
const fetchedAt = ref("");
const source = ref("");
const stale = ref(false);
const stats = reactive({ valid: null, up: null, down: null, flat: null, limit_up: null, limit_down: null, big_down: null });
const senti = reactive({ temp: null, level: "", lv: 3 });
const sentiTitle = ref("");
const hot = ref([]);
const watchRows = ref([]);   // 我的自选(最多展示 8 只)

async function loadWatch() {
  try {
    const d = await api("/api/watchlist");
    watchRows.value = (d.rows || []).slice(0, 8);
  } catch { /* 自选加载失败不影响主页其他区块 */ }
}

const upPct = computed(() =>
  stats.valid ? Math.round((stats.up / stats.valid) * 1000) / 10 : 50);

// 与筛选页 updateSentiBadge 同口径(量能分量缺失时按中性 15 计)
function computeSenti(s) {
  if (!s.valid) { senti.temp = null; senti.level = ""; return; }
  const upRatio = s.up / s.valid;
  const limitScore = (s.limit_up + s.limit_down) > 0
    ? (s.limit_up / (s.limit_up + s.limit_down)) * 30 : 15;
  const temp = Math.round(upRatio * 40 + limitScore + 15);
  senti.temp = temp;
  senti.level = temp < 20 ? "冰点" : temp < 40 ? "低迷" : temp < 60 ? "中性" : temp < 80 ? "活跃" : "亢奋";
  senti.lv = temp < 20 ? 1 : temp < 40 ? 2 : temp < 60 ? 3 : temp < 80 ? 4 : 5;
  sentiTitle.value = `市场情绪 ${temp}/100 · ${senti.level}`
    + `\n· 上涨 ${s.up} 家 · 下跌 ${s.down ?? (s.valid - s.up)} 家 · 平盘 ${s.flat ?? "—"} 家`
    + `\n· 涨停 ${s.limit_up} / 跌停 ${s.limit_down}`
    + "\n· 指数量能:缺失(按中性计)";
}

// 活跃精选:仅沪深主板,按 换手45% + 涨幅35% + 量比20% 的秩次综合评分取 TOP6
const MAIN_BOARD_FS = "m%3A1%2Bt%3A2,m%3A0%2Bt%3A6"; // 沪主板 + 深主板
function rankMap(rows, key) {
  const sorted = [...rows].sort((a, b) => (a[key] ?? -Infinity) - (b[key] ?? -Infinity));
  const m = new Map();
  sorted.forEach((r, i) => m.set(r.f12, i / Math.max(1, sorted.length - 1)));
  return m;
}
function pickTopComposite(rows, n) {
  if (!rows.length) return [];
  const rTov = rankMap(rows, "f8"), rChg = rankMap(rows, "f3"), rVol = rankMap(rows, "f10");
  return [...rows]
    .map((r) => ({ r, s: 0.45 * rTov.get(r.f12) + 0.35 * rChg.get(r.f12) + 0.2 * rVol.get(r.f12) }))
    .sort((a, b) => b.s - a.s)
    .slice(0, n)
    .map((x) => x.r);
}

async function load() {
  try {
    const [meta, list] = await Promise.all([
      api("/api/quote/meta"),
      api(`/api/quote/list?markets=${MAIN_BOARD_FS}&limit=40`),
    ]);
    fetchedAt.value = (meta.fetched_at || "").replace("T", " ").slice(5, 16);
    source.value = meta.source;
    stale.value = !!meta.stale;
    Object.assign(stats, meta.stats, { down: meta.stats.down ?? (meta.stats.valid - meta.stats.up) });
    computeSenti(meta.stats);
    hot.value = pickTopComposite(list.rows || [], 6);
    // 缓存本次结果,下次进页面先渲染缓存(1M 小水管下避免白屏等待)
    try {
      sessionStorage.setItem("home-cache", JSON.stringify({
        fetchedAt: fetchedAt.value, source: source.value,
        stats: meta.stats, hot: hot.value,
      }));
    } catch (e) {}
  } catch { /* 未登录跳转由 api client 处理;其余失败保持占位 */ }
}

// 缓存优先:上次数据立即上屏,随后 load() 静默刷新
try {
  const c = JSON.parse(sessionStorage.getItem("home-cache") || "null");
  if (c && c.stats) {
    fetchedAt.value = c.fetchedAt || "";
    source.value = c.source || "";
    Object.assign(stats, c.stats);
    computeSenti(c.stats);
    hot.value = c.hot || [];
  }
} catch (e) {}

// 交易时段每分钟静默刷新一次
let timer = null;
onMounted(() => {
  load();
  loadWatch();
  timer = setInterval(() => {
    const d = new Date(), mins = d.getHours() * 60 + d.getMinutes();
    if (d.getDay() % 6 !== 0 && mins >= 555 && mins <= 910) { load(); loadWatch(); }
  }, 60_000);
});
onUnmounted(() => clearInterval(timer));
</script>

<style scoped>
.home { width: 100%; padding: 12px 0 8px; }

/* ===== 刊头 ===== */
.mast {
  display: flex; align-items: flex-end; justify-content: space-between; gap: 16px;
  padding: 20px 0 18px; border-bottom: 1px solid var(--line-strong);
}
.mastDate {
  font-size: 12px; letter-spacing: .14em; color: var(--dim);
  font-family: var(--mono); text-transform: uppercase;
}
.mastHi { font-size: 30px; font-weight: 650; letter-spacing: .01em; margin-top: 8px; }
.mastMeta {
  flex: none; display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--dim); font-family: var(--mono); padding-bottom: 4px;
}
.liveDot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim);
}
.mastMeta.stale .liveDot { background: var(--hot); box-shadow: 0 0 0 3px rgba(245, 158, 11, .15); }

/* ===== 区块头:细分隔线 + 左标签右英文/链接 ===== */
.blk { margin-top: 34px; }
.secHead {
  display: flex; align-items: baseline; gap: 12px;
  padding-bottom: 10px; border-bottom: 1px solid var(--line);
}
.secName { font-size: 15px; font-weight: 650; letter-spacing: .04em; }
.secName::before {
  content: ""; display: inline-block; width: 3px; height: 12px; border-radius: 2px;
  background: var(--brand-red); margin-right: 8px; vertical-align: -1px;
}
.secEn {
  font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
  color: var(--dim); font-family: var(--mono);
}
.secMore { margin-left: auto; font-size: 12.5px; color: var(--dim); text-decoration: none; transition: color .15s; }
.secMore:hover { color: var(--accent); }

/* ===== 市场脉搏 ===== */
.pulse {
  display: grid; grid-template-columns: 200px 1fr 340px; gap: 36px;
  align-items: center; padding: 24px 4px 8px;
}
.pTempNum { font-family: var(--mono); font-size: 46px; font-weight: 600; line-height: 1.05; }
.pTempNum.lv1 { color: var(--freeze); } .pTempNum.lv2 { color: var(--accent); }
.pTempNum.lv3 { color: var(--txt); }
.pTempNum.lv4 { color: var(--hot); } .pTempNum.lv5 { color: var(--up); }
.pTempCap { color: var(--dim); font-size: 12px; margin-top: 4px; }
.pTempTrack {
  height: 3px; border-radius: 999px; background: var(--panel-2); margin-top: 12px; overflow: hidden;
}
.pTempTrack i { display: block; height: 100%; border-radius: 999px; transition: width .6s cubic-bezier(.2,.8,.2,1); }
.pTempTrack i.lv1 { background: var(--freeze); } .pTempTrack i.lv2 { background: var(--accent); }
.pTempTrack i.lv3 { background: var(--dim); }
.pTempTrack i.lv4 { background: var(--hot); } .pTempTrack i.lv5 { background: var(--up); }

.pBreadth .bNums {
  display: flex; justify-content: space-between; font-size: 13px; color: var(--dim); margin-bottom: 10px;
}
.bNums b { font-family: var(--mono); font-size: 20px; font-weight: 600; margin-right: 4px; }
.bNums b.up { color: var(--up); } .bNums b.down { color: var(--down); }
.bBar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: var(--panel-2); }
.bBar i { display: block; height: 100%; transition: width .6s cubic-bezier(.2,.8,.2,1); }
.bBar i.up { background: var(--up); }
.bBar i.down { background: var(--down); }
.bCap { color: var(--dim); font-size: 11.5px; margin-top: 10px; font-family: var(--mono); }

.pLimits { display: flex; align-items: center; justify-content: space-between; }
.lItem { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.lItem b { font-family: var(--mono); font-size: 24px; font-weight: 600; }
.lItem b.up { color: var(--up); } .lItem b.down { color: var(--down); }
.lItem span { color: var(--dim); font-size: 11.5px; }
.lSep { width: 1px; height: 34px; background: var(--line); }

/* ===== 双栏:工具 + 活跃榜 ===== */
.cols { display: grid; grid-template-columns: 1.15fr 1fr; gap: 48px; }

/* 工具:编辑排印风条目 */
.tools { display: flex; flex-direction: column; }
.tool {
  display: flex; align-items: center; gap: 18px;
  padding: 17px 6px; border-bottom: 1px solid var(--line);
  cursor: pointer; transition: background .15s, padding .2s;
}
.tool:hover { background: var(--hover); }
.tool:not(.off):hover { padding-left: 12px; }
.tool.off { cursor: default; }
.tool.off .tTitle, .tool.off .tIdx { color: var(--dim); }
.tIdx { font-family: var(--mono); font-size: 12px; color: var(--dim); flex: none; }
.tMain { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tTitle { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.tIcon { font-size: 15px; color: var(--brand-red); }
.tool.off .tIcon { color: var(--dim); }
.tDesc { font-size: 12px; color: var(--dim); line-height: 1.6; }
.tArrow {
  margin-left: auto; flex: none; color: var(--brand-red); font-size: 16px;
  transition: transform .2s;
}
.tool:hover .tArrow { transform: translateX(4px); }
.tSoon {
  margin-left: auto; flex: none; font-size: 11px; color: var(--dim);
  font-family: var(--mono); letter-spacing: .08em;
}

/* 活跃榜 */
.hot { display: flex; flex-direction: column; }
.hRow {
  display: flex; align-items: baseline; gap: 12px;
  padding: 11.5px 6px; border-bottom: 1px solid var(--line);
  text-decoration: none; color: inherit; transition: background .15s;
}
.hRow:hover { background: var(--hover); }
.hIdx {
  flex: none; width: 18px; font-family: var(--mono); font-size: 11.5px; color: var(--dim);
}
.hRow:nth-child(1) .hIdx, .hRow:nth-child(2) .hIdx, .hRow:nth-child(3) .hIdx { color: var(--brand-red); font-weight: 600; }
.hName { flex: 1; min-width: 0; font-size: 13.5px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hCode { font-style: normal; font-family: var(--mono); font-size: 11px; color: var(--dim); margin-left: 7px; }
.hPx { font-family: var(--mono); font-size: 12.5px; }
.hChg { font-family: var(--mono); font-size: 12.5px; width: 64px; text-align: right; }
.hTov {
  flex: none; width: 58px; text-align: right;
  font-family: var(--mono); font-size: 12.5px; font-weight: 600; color: var(--accent);
}
.hPx.up, .hChg.up { color: var(--up); } .hPx.down, .hChg.down { color: var(--down); }
.hEmpty { color: var(--dim); font-size: 13px; padding: 36px 6px; }

/* ===== 我的自选卡片条 ===== */
.watchStrip {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px; margin-top: 14px;
}
.wCard {
  display: flex; flex-direction: column; gap: 8px;
  border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px;
  color: var(--txt); text-decoration: none; background: var(--panel);
  transition: border-color .15s, transform .12s;
}
.wCard:hover { border-color: var(--accent); transform: translateY(-1px); }
.wName { font-size: 13px; font-weight: 600; }
.wNums { display: flex; align-items: baseline; justify-content: space-between; }
.wNums b { font-family: var(--mono); font-size: 14px; }
.wTov { font-style: normal; color: var(--dim); font-size: 11.5px; font-family: var(--mono); }
.watchEmpty { padding: 22px 4px; color: var(--dim); font-size: 12.5px; }
.watchEmpty a { color: var(--accent); }

/* ===== 免责声明 ===== */.disclaimer {
  margin-top: 44px; padding-top: 14px; border-top: 1px solid var(--line);
  color: var(--dim); font-size: 11.5px; line-height: 1.8;
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 16px; flex-wrap: wrap;
}
.disclaimer .ver {
  flex: none; font-family: var(--mono); font-size: 11px; opacity: 0.75;
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .pulse { grid-template-columns: 1fr; gap: 24px; }
  .pLimits { justify-content: space-around; }
  .cols { grid-template-columns: 1fr; gap: 0; }
}
@media (max-width: 640px) {
  .mast { flex-direction: column; align-items: flex-start; gap: 10px; }
  .mastHi { font-size: 24px; }
  .blk { margin-top: 26px; }
}
</style>
