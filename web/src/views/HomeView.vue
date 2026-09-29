<template>
  <div class="home">
    <!-- ===== 顶部行情走马灯情报条 ===== -->
    <HomeTicker
      :hot="hot"
      :watch-rows="watchRows"
      :stats="stats"
      :quote="currentQuote"
    />

    <!-- ===== 刊头：日期 + 问候 + 股市箴言（居中） + 数据快照时间 ===== -->
    <header class="mast">
      <div class="mastLeft">
        <div class="mastDate">{{ dateStr }}</div>
        <h1 class="mastHi">{{ greeting }}，{{ authState.user?.username }}</h1>
      </div>

      <!-- 中间：哲学箴言与市场寄语 (无多余边框，与背景浑然一体，简约优雅) -->
      <div class="mastCenter">
        <div
          class="mastQuote"
          :class="{ fading: quoteFading }"
          @click="nextQuote"
          title="点击换一条"
        >
          <span class="quoteMark">“</span>
          <span class="quoteText">{{ currentQuote.text }}</span>
          <span class="quoteMark">”</span>
          <span v-if="currentQuote.author" class="quoteAuthor">—— {{ currentQuote.author }}</span>
          <span class="quoteRefresh" aria-label="换一条">
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19"/>
            </svg>
          </span>
        </div>
      </div>

      <div class="mastRight">
        <div v-if="fetchedAt" class="mastMeta" :class="{ stale }">
          <i class="liveDot"></i>
          {{ stale ? "快照待更新" : "数据更新于" }} {{ fetchedAt }} · 东方财富{{ source ? " · " + source : "" }}
        </div>
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
          <span v-if="hotSrc" class="secNote" :title="'排名来自全市场快照,报价实时来自 ' + hotSrc">
            <i class="srcDot live"></i>报价实时 · {{ hotSrc }}
          </span>
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
        <span v-if="watchSrc" class="secNote" :class="{ live: watchLive }"
              :title="watchLive ? '实时行情来自你在设置里启用的行情源' : '未启用自定义行情源,展示最新快照'">
          <i class="srcDot" :class="{ live: watchLive }"></i>{{ watchSrc }}
        </span>
        <router-link to="/watchlist" class="secMore">管理自选 →</router-link>
        <router-link to="/settings" class="secMore">行情设置 →</router-link>
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
        还没有自选股，去 <router-link to="/watchlist">添加自选</router-link> 或在筛选结果里点 ★<br />
        也可以在 <router-link to="/settings">设置 · 行情设置</router-link> 里配置自己的行情接口
      </div>
    </section>

    <!-- ===== 免责声明 ===== -->
    <footer class="disclaimer">
      <span>
        数据来自东方财富，页面内容仅为客观数据的整理与展示，不构成任何推荐或投资建议。
        本站为个人技术研究工具，不提供证券投资咨询服务，不收取任何费用。
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
import HomeTicker from "../components/HomeTicker.vue";

// 功能入口:客观量化工具矩阵，严守不荐股底线
const features = [
  { title: "换手率筛选", icon: FundViewOutlined, path: "/screener",
    desc: "按换手率/涨跌幅/行业/量比等多维量化指标客观统计全市场个股活跃度。" },
  { title: "涨停雷达", icon: FireOutlined, path: "/radar",
    desc: "连板天梯梯队复盘 × 一进二候选：客观六维粗筛，纯作盘面观察统计。" },
  { title: "板块强度", icon: CrownOutlined, path: "/sector",
    desc: "全市场行业板块涨跌幅排行、涨跌家数比、涨停梯队与领涨龙头矩阵。" },
  { title: "资金流向", icon: FundOutlined, path: "/flow",
    desc: "概念与行业分时主力资金净额、5分钟异动与资金广度分布统计。" },
  { title: "趋势统计", icon: RocketOutlined, path: "",
    desc: "全市场均线多空结构与形态阶段宏观统计，仅作环境参考，不荐股。" },
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

// ===== 刊头股市箴言与投资哲学 =====
const MARKET_QUOTES = [
  { text: "在别人贪婪时恐惧，在别人恐惧时贪婪。", author: "沃伦·巴菲特" },
  { text: "股市是把财富从浮躁者手中转移到从容者手中的工具。", author: "沃伦·巴菲特" },
  { text: "如果不想拥有一只股票十年，就不要考虑拥有它十分钟。", author: "沃伦·巴菲特" },
  { text: "时间是优秀企业的朋友，是平庸企业的敌人。", author: "沃伦·巴菲特" },
  { text: "反过来想，总是反过来想。", author: "查理·芒格" },
  { text: "赚大钱不在于买进卖出，而在于等待。", author: "查理·芒格" },
  { text: "宏观是我们必须忍受的，微观才是我们可以有所作为的。", author: "查理·芒格" },
  { text: "耐心是一种美德，尤其是在一个充斥着短期投机的市场中。", author: "查理·芒格" },
  { text: "股市中从来没有什么新鲜事，投机像山岳一样古老。", author: "杰西·利弗莫尔" },
  { text: "钱是坐着等出来的，不是靠频繁交易折腾出来的。", author: "杰西·利弗莫尔" },
  { text: "截断亏损，让利润奔跑。", author: "杰西·利弗莫尔" },
  { text: "市场短期是一台投票机，长期是一台称重机。", author: "本杰明·格雷厄姆" },
  { text: "安全边际，是投资成功的基石。", author: "本杰明·格雷厄姆" },
  { text: "周期永远不会结束，保持敬畏是对市场最好的尊重。", author: "霍华德·马克斯" },
  { text: "投资最重要的事，是认清风险并控制风险。", author: "霍华德·马克斯" },
  { text: "行情总在绝望中诞生，在犹豫中前行，在疯狂中幻灭。", author: "约翰·邓普顿" },
  { text: "决定投资命运的不是头脑，而是耐得住寂寞的定力。", author: "彼得·林奇" },
  { text: "行情就像小狗，有时跑在前面，有时落在后面，但终究会回到主人身边。", author: "安德烈·科斯托兰尼" },
  { text: "流水不争先，争的是滔滔不绝。", author: "" },
  { text: "心静如水，顺势而为；守正出奇，笃定致远。", author: "" },
  { text: "弱水三千，只取一瓢；繁花过眼，守住主线。", author: "" },
  { text: "敬畏市场，知行合一；多看少动，从容行远。", author: "" },
  { text: "宁可错过，绝不做错；知止常止，方得始终。", author: "" },
  { text: "愿你眼中有星辰，心中有纪律，行稳致远，账户长虹。", author: "" },
];

const quoteIdx = ref(Math.floor(Math.random() * MARKET_QUOTES.length));
const currentQuote = computed(() => MARKET_QUOTES[quoteIdx.value]);
const quoteFading = ref(false);

function nextQuote() {
  if (quoteFading.value) return;
  quoteFading.value = true;
  setTimeout(() => {
    let next;
    do {
      next = Math.floor(Math.random() * MARKET_QUOTES.length);
    } while (next === quoteIdx.value && MARKET_QUOTES.length > 1);
    quoteIdx.value = next;
    quoteFading.value = false;
  }, 160);
}

// ===== 行情快照:meta(统计) + list(活跃榜) =====
const fetchedAt = ref("");
const source = ref("");
const stale = ref(false);
const stats = reactive({ valid: null, up: null, down: null, flat: null, limit_up: null, limit_down: null, big_down: null });
const senti = reactive({ temp: null, level: "", lv: 3 });
const sentiTitle = ref("");
const hot = ref([]);
const hotSrc = ref("");      // 活跃精选报价的实时来源(自己的/公共源),空=快照价
const watchRows = ref([]);   // 我的自选(最多展示 8 只)
const watchSrc = ref("");    // 行情来源描述(如 "麦蕊智数 · 我的麦蕊" / "东方财富快照")
const watchLive = ref(false);// 是否实时(启用了自己的行情源)

// 自选条行情:走 /api/quote/realtime——启用了自己的行情源则取实时,
// 否则/失败自动回落最新快照(接口内兜底,codes 缺省取本人自选)
async function loadWatch() {
  try {
    const d = await api("/api/quote/realtime");
    watchRows.value = (d.rows || []).slice(0, 8);
    watchSrc.value = d.source || "";
    watchLive.value = !!d.live;
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
    overlayHotRealtime();
    // 缓存本次结果,下次进页面先渲染缓存(1M 小水管下避免白屏等待)
    try {
      sessionStorage.setItem("home-cache", JSON.stringify({
        fetchedAt: fetchedAt.value, source: source.value,
        stats: meta.stats, hot: hot.value,
      }));
    } catch (e) {}
  } catch { /* 未登录跳转由 api client 处理;其余失败保持占位 */ }
}

// 活跃精选的排名来自全市场快照(东方财富);启用源后展示的现价/涨幅/换手
// 用自己的行情源实时覆盖(6 只 ≤ 单次批量上限),失败静默留在快照价
async function overlayHotRealtime() {
  const codes = hot.value.map((r) => r.f12).join(",");
  if (!codes) return;
  try {
    const d = await api("/api/quote/realtime?codes=" + codes);
    if (!d.live) return;
    const by = new Map((d.rows || []).map((r) => [r.f12, r]));
    hot.value = hot.value.map((r) => {
      const q = by.get(r.f12);
      return q ? { ...r, f2: q.f2, f3: q.f3, f8: q.f8 } : r;
    });
    hotSrc.value = d.source || "";
  } catch { /* 实时覆盖失败不影响页面 */ }
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
  display: flex; align-items: flex-end; justify-content: space-between; gap: 20px;
  padding: 20px 0 18px; border-bottom: 1px solid var(--line-strong);
}
.mastLeft { flex: none; }
.mastDate {
  font-size: 12px; letter-spacing: .14em; color: var(--dim);
  font-family: var(--mono); text-transform: uppercase;
}
.mastHi { font-size: 30px; font-weight: 650; letter-spacing: .01em; margin-top: 8px; }

/* ===== 中间居中箴言（简约无框，自然融入背景） ===== */
.mastCenter {
  flex: 1; min-width: 0;
  display: flex; justify-content: center; align-items: flex-end;
  padding: 0 16px 4px;
}
.mastQuote {
  display: inline-flex; align-items: baseline; gap: 4px;
  background: transparent;
  border: none;
  color: var(--dim);
  font-size: 12.5px;
  cursor: pointer;
  user-select: none;
  transition: color .2s ease, opacity .2s ease, transform .2s ease;
  max-width: 100%;
}
.mastQuote:hover {
  color: var(--txt);
}
.mastQuote.fading {
  opacity: 0;
  transform: translateY(-2px);
}
.quoteMark {
  font-family: Georgia, serif;
  color: var(--accent);
  opacity: .75;
  font-size: 14px;
  line-height: 1;
}
.quoteText {
  letter-spacing: .02em;
  font-weight: 450;
  line-height: 1.5;
  transition: color .15s ease;
}
.quoteAuthor {
  color: var(--dim);
  font-size: 11.5px;
  white-space: nowrap;
  margin-left: 4px;
  opacity: .85;
}
.quoteRefresh {
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--dim);
  opacity: 0;
  margin-left: 4px;
  transform: translateY(1px);
  transition: transform .25s ease, opacity .2s ease, color .15s ease;
}
.mastQuote:hover .quoteRefresh {
  opacity: .8;
  color: var(--accent);
  transform: translateY(1px) rotate(45deg);
}

.mastRight {
  flex: none; display: flex; align-items: flex-end; padding-bottom: 2px;
}
.mastMeta {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--dim); font-family: var(--mono);
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
.secMore + .secMore { margin-left: 0; }
.secNote {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; color: var(--dim); font-family: var(--mono);
}
.srcDot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--dim);
  opacity: .6;
}
.srcDot.live { background: var(--accent); opacity: 1; box-shadow: 0 0 0 3px var(--accent-dim); }
/* 两个链接时:来源说明在中间,链接保持右对齐 */
.secNote + .secMore { margin-left: auto; }
.secNote + .secMore + .secMore { margin-left: 0; }

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
@media (max-width: 900px) {
  .mast { flex-wrap: wrap; gap: 14px; }
  .mastCenter { order: 3; width: 100%; justify-content: flex-start; padding: 4px 0 0; }
  .mastRight { margin-left: auto; }
}
@media (max-width: 640px) {
  .mast { flex-direction: column; align-items: flex-start; gap: 10px; }
  .mastCenter { justify-content: flex-start; padding: 0; }
  .mastRight { width: 100%; justify-content: flex-start; margin-left: 0; }
  .mastHi { font-size: 24px; }
  .blk { margin-top: 26px; }
}
</style>
