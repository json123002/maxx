<script setup>
/* ===== 涨停雷达：一进二候选（服务端粗筛） =====
   昨日首板涨停 ∩ 今日竞价/换手/额比/资金/空间粗筛,六维 ✅⚠️❌ 徽章。
   竞价金额占比、上板时间、分时结构需盘中精细数据,点名称进个股详情终检。
   埋点 radar_view。 */
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { api, track } from "../api/client";
import { cls, fmtN } from "../utils/format";

const date = ref("");
const rows = ref([]);
const stat = ref(null);
const note = ref("");
const rules = ref({});
const review = ref(false); // 快照仍停留在首板日的复盘视角(竞价/额比为首板当日旧值)
const loading = ref(false);
const expanded = ref(""); // 展开「判定理由」的股票代码

const firstCnt = computed(() => rows.value.filter((r) => r.board === 1).length);
const lianbanCnt = computed(() => rows.value.length - firstCnt.value);

const DIM_TXT = { good: "✓", warn: "~", bad: "✗" };
const DIM_LABEL = { open: "竞价涨幅", tov: "换手", amt: "额比",
                    main: "主力净流入", dist: "距前高", gene: "基因" };

function dimRows(r) {
  const pct = (v) => (v > 0 ? "+" : "") + fmtN(v) + "%";
  return [
    { k: "open", actual: r.open_pct != null ? pct(r.open_pct) : "无数据" },
    { k: "tov", actual: r.tov != null ? fmtN(r.tov) + "%" : "无数据" },
    { k: "amt", actual: r.amt_ratio != null ? fmtN(r.amt_ratio) + " 倍" : "无数据" },
    { k: "main", actual: r.main_net_yi != null ? fmtN(r.main_net_yi) + " 亿" : "无数据" },
    { k: "dist", actual: r.dist_high != null
        ? (r.dist_high >= 0 ? "涨停价已突破前高" : "距前高 " + fmtN(r.dist_high) + "%")
        : "无前高参考" },
    { k: "gene", actual: (r.kill_a ? "A杀 ×" + r.kill_a + "，" : "无 A杀，")
        + (r.zhaban == null ? "炸板未统计(无日K)，"
           : r.zhaban ? "炸板 ×" + r.zhaban + "，" : "")
        + "近一年最高 " + r.max_streak + " 连板" },
  ].map((d) => ({ ...d, label: DIM_LABEL[d.k], mark: r.dims[d.k],
                  rule: rules.value[d.k] || "" }));
}

function whyLine(r) {
  const bad = dimRows(r).filter((d) => d.mark === "bad").map((d) => d.label);
  const warn = dimRows(r).filter((d) => d.mark === "warn").map((d) => d.label);
  if (r.verdict === "放弃") return "一票否决：" + bad.join("、");
  if (r.verdict === "观察") return "待确认：" + warn.join("、");
  return "六维全部达标";
}

function toggle(r) {
  expanded.value = expanded.value === r.f12 ? "" : r.f12;
}

async function load() {
  loading.value = true;
  try {
    const d = await api("/api/radar/1to2");
    date.value = d.date;
    rows.value = d.rows;
    stat.value = d.stat || null;
    note.value = d.note || "";
    rules.value = d.rules || {};
    review.value = !!d.review;
    expanded.value = "";
    track("radar_view", d.date + " → " + d.rows.length + " 只候选");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

const activeTab = ref("ladder"); // ladder | 1to2
const ladderLoading = ref(false);
const ladderData = ref({
  summary: { total_limit_up: 0, total_broken: 0, broken_rate: 0, max_streak: 0, promotions: {}, hot_industries: [] },
  tiers: { tier5plus: [], tier4: [], tier3: [], tier2: [], tier1: [] },
  broken: [],
});

async function loadLadder() {
  ladderLoading.value = true;
  try {
    const d = await api("/api/radar/ladder");
    ladderData.value = d;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "天梯数据加载失败");
  } finally {
    ladderLoading.value = false;
  }
}

async function refreshActive() {
  if (activeTab.value === "ladder") {
    await loadLadder();
  } else {
    await load();
  }
}

onMounted(() => {
  loadLadder();
  load();
});
</script>

<template>
  <div class="radarWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">涨停雷达 · 操盘复盘</span>
        <div class="tabNav">
          <button class="navTab" :class="{ act: activeTab === 'ladder' }" @click="activeTab = 'ladder'">
            连板天梯 & 情绪
          </button>
          <button class="navTab" :class="{ act: activeTab === '1to2' }" @click="activeTab = '1to2'">
            一进二量化雷达
          </button>
        </div>
        <button class="ghostBtn" :disabled="loading || ladderLoading" @click="refreshActive">
          {{ (loading || ladderLoading) ? "刷新中…" : "刷新" }}
        </button>
      </div>

      <!-- 连板天梯 Tab -->
      <div v-if="activeTab === 'ladder'" class="ladderSection">
        <!-- 情绪概览看板 -->
        <div class="ladderMetrics">
          <div class="metricCard">
            <span class="mLabel">涨停总数</span>
            <span class="mVal up">{{ ladderData.summary.total_limit_up }} <small>家</small></span>
          </div>
          <div class="metricCard">
            <span class="mLabel">连板高度标的</span>
            <span class="mVal" :class="ladderData.summary.max_streak >= 3 ? 'up' : ''">
              {{ ladderData.summary.max_streak ? ladderData.summary.max_streak + ' 连板' : '—' }}
            </span>
          </div>
          <div class="metricCard">
            <span class="mLabel">炸板率</span>
            <span class="mVal" :class="ladderData.summary.broken_rate > 30 ? 'down' : ''">
              {{ ladderData.summary.broken_rate }}%
              <small class="mSub">({{ ladderData.summary.total_broken }} 炸板)</small>
            </span>
          </div>
          <div v-if="ladderData.summary.promotions && ladderData.summary.promotions.promotion_rate != null" class="metricCard">
            <span class="mLabel">昨日连板晋级率</span>
            <span class="mVal accent">
              {{ ladderData.summary.promotions.promotion_rate }}%
              <small class="mSub">({{ ladderData.summary.promotions.promoted_today }}/{{ ladderData.summary.promotions.yesterday_limits }})</small>
            </span>
          </div>
          <div v-if="ladderData.summary.hot_industries && ladderData.summary.hot_industries.length" class="metricCard hotCard">
            <span class="mLabel">最强主攻风口</span>
            <div class="hotTags">
              <span v-for="h in ladderData.summary.hot_industries" :key="h.industry" class="hotTag">
                {{ h.industry }} <b>{{ h.count }}</b>
              </span>
            </div>
          </div>
        </div>

        <!-- 天梯层级展示 -->
        <div class="tierGroups">
          <!-- 5板及以上 -->
          <div v-if="ladderData.tiers.tier5plus && ladderData.tiers.tier5plus.length" class="tierBlock">
            <div class="tierTitle high">
              <span class="tierBadge">高度空间板</span>
              <span class="tierDesc">市场绝对核心，引领全场情绪周期 ({{ ladderData.tiers.tier5plus.length }} 只)</span>
            </div>
            <div class="stockGrid">
              <div v-for="s in ladderData.tiers.tier5plus" :key="s.code" class="stockCard">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="streakTag highTag">{{ s.streak }} 连板</span>
                </div>
                <div class="scMeta">
                  <span class="scCode">{{ s.code }}</span>
                  <span class="scInd">{{ s.industry }}</span>
                </div>
                <div class="scStats">
                  <span>涨幅 <b class="up">+{{ fmtN(s.pct) }}%</b></span>
                  <span>换手 <b>{{ fmtN(s.turnover) }}%</b></span>
                  <span>金额 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">
                    主力 <b>{{ s.main_net_yi > 0 ? '+' : '' }}{{ s.main_net_yi }}亿</b>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 4板 -->
          <div v-if="ladderData.tiers.tier4 && ladderData.tiers.tier4.length" class="tierBlock">
            <div class="tierTitle mid">
              <span class="tierBadge">4 连板</span>
              <span class="tierDesc">中位强势股，争夺高标空间 ({{ ladderData.tiers.tier4.length }} 只)</span>
            </div>
            <div class="stockGrid">
              <div v-for="s in ladderData.tiers.tier4" :key="s.code" class="stockCard">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="streakTag">{{ s.streak }} 连板</span>
                </div>
                <div class="scMeta">
                  <span class="scCode">{{ s.code }}</span>
                  <span class="scInd">{{ s.industry }}</span>
                </div>
                <div class="scStats">
                  <span>换手 <b>{{ fmtN(s.turnover) }}%</b></span>
                  <span>金额 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">主力 <b>{{ s.main_net_yi }}亿</b></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 3板 -->
          <div v-if="ladderData.tiers.tier3 && ladderData.tiers.tier3.length" class="tierBlock">
            <div class="tierTitle">
              <span class="tierBadge">3 连板</span>
              <span class="tierDesc">主线中坚力量 ({{ ladderData.tiers.tier3.length }} 只)</span>
            </div>
            <div class="stockGrid">
              <div v-for="s in ladderData.tiers.tier3" :key="s.code" class="stockCard">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="streakTag">{{ s.streak }} 连板</span>
                </div>
                <div class="scMeta">
                  <span class="scCode">{{ s.code }}</span>
                  <span class="scInd">{{ s.industry }}</span>
                </div>
                <div class="scStats">
                  <span>换手 <b>{{ fmtN(s.turnover) }}%</b></span>
                  <span>金额 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">主力 <b>{{ s.main_net_yi }}亿</b></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 2板 -->
          <div v-if="ladderData.tiers.tier2 && ladderData.tiers.tier2.length" class="tierBlock">
            <div class="tierTitle">
              <span class="tierBadge">2 连板</span>
              <span class="tierDesc">昨日首板晋级确认，新题材发酵试金石 ({{ ladderData.tiers.tier2.length }} 只)</span>
            </div>
            <div class="stockGrid">
              <div v-for="s in ladderData.tiers.tier2" :key="s.code" class="stockCard">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="streakTag">2 连板</span>
                </div>
                <div class="scMeta">
                  <span class="scCode">{{ s.code }}</span>
                  <span class="scInd">{{ s.industry }}</span>
                </div>
                <div class="scStats">
                  <span>换手 <b>{{ fmtN(s.turnover) }}%</b></span>
                  <span>金额 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">主力 <b>{{ s.main_net_yi }}亿</b></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 首板 -->
          <div v-if="ladderData.tiers.tier1 && ladderData.tiers.tier1.length" class="tierBlock">
            <div class="tierTitle">
              <span class="tierBadge">首板突破</span>
              <span class="tierDesc">首板新秀，明日一进二候选来源 ({{ ladderData.tiers.tier1.length }} 只)</span>
            </div>
            <div class="stockGrid compact">
              <div v-for="s in ladderData.tiers.tier1" :key="s.code" class="stockCard compact">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="scCode">{{ s.code }}</span>
                </div>
                <div class="scMeta">
                  <span class="scInd">{{ s.industry }}</span>
                  <span>换手 {{ fmtN(s.turnover) }}%</span>
                </div>
                <div class="scStats">
                  <span>金额 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">主力 <b>{{ s.main_net_yi }}亿</b></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 炸板池 -->
          <div v-if="ladderData.broken && ladderData.broken.length" class="tierBlock">
            <div class="tierTitle broken">
              <span class="tierBadge broken">炸板观察池</span>
              <span class="tierDesc">日内触及涨停但被砸开，短线分歧度检测 (前 {{ ladderData.broken.length }} 只)</span>
            </div>
            <div class="stockGrid compact">
              <div v-for="s in ladderData.broken" :key="s.code" class="stockCard compact brokenCard">
                <div class="scTop">
                  <router-link :to="'/stock/' + s.code" class="scName">{{ s.name }}</router-link>
                  <span class="scCode">{{ s.code }}</span>
                  <span class="up">+{{ fmtN(s.pct) }}%</span>
                </div>
                <div class="scMeta">
                  <span class="scInd">{{ s.industry }}</span>
                  <span>换手 {{ fmtN(s.turnover) }}%</span>
                </div>
                <div class="scStats">
                  <span>成交 <b>{{ s.amount_yi != null ? s.amount_yi + '亿' : '—' }}</b></span>
                  <span v-if="s.main_net_yi != null" :class="cls(s.main_net_yi)">主力 <b>{{ s.main_net_yi }}亿</b></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 一进二粗筛 Tab -->
      <div v-else class="oneToTwoSection">
        <div class="bar">
          <span v-if="date" class="dayStats">首板日 <b>{{ date }}</b></span>
          <span v-if="review" class="reviewTag">复盘视角</span>
          <span v-if="stat" class="dayStats">
            <b class="vdGood">{{ stat["候选"] || 0 }}</b> 候选 ·
            <b class="vdWarn">{{ stat["观察"] || 0 }}</b> 观察 ·
            <b class="vdBad">{{ stat["放弃"] || 0 }}</b> 放弃
          </span>
          <span class="barSpacer"></span>
          <span class="cnt" v-if="rows.length">共 {{ firstCnt }} 只首板<template
            v-if="lianbanCnt">，另有 {{ lianbanCnt }} 只连板（非首板，列末参考）</template></span>
        </div>

        <div class="tblWrap" :class="{ loading }">
          <table v-if="rows.length">
            <thead>
              <tr>
                <th class="l">代码</th><th class="l">名称</th><th class="l">行业</th>
                <th>流通市值</th>
                <th title="高开 3-6% 为最佳">竞价涨幅</th>
                <th title="名义换手 10-25% 为佳（实际换手口径需自由流通股本，此处偏宽）">换手 %</th>
                <th title="今日成交额 / 昨日成交额,0.5-1.5 为佳">额比</th>
                <th title="主力净流入 > 1 亿为佳">主力净流入</th>
                <th title="涨停价相对 120 日日K最高价:突破或空间 >20% 为佳,距前高 8% 左右最危险">距前高</th>
                <th title="近一年股性:A杀 / 炸板(盘中触板未封) / 最高连板;有 A杀或炸板 ≥3 次 = 不合格">基因</th>
                <th>判定</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="r in rows" :key="r.f12">
              <tr class="pickRow" :class="{ exp: expanded === r.f12 }" @click="toggle(r)">
                <td class="l">{{ r.f12 }}</td>
                <td class="l name">
                  <router-link class="nameLink" :to="'/stock/' + r.f12"
                               @click.stop>{{ r.f14 }}</router-link>
                  <span v-if="r.limit_up === 1" class="lmBadge up">涨停</span>
                  <span v-if="r.board > 1" class="lmBadge cont"
                        title="昨日已是连板（非首板），一进二窗口已过，仅供参考">已{{ r.board }}板</span>
                </td>
                <td class="l dimTxt">{{ r.f100 || "—" }}</td>
                <td>{{ r.free_cap_yi != null ? r.free_cap_yi + "亿" : "—" }}</td>
                <td><span class="dim" :class="r.dims.open">{{ DIM_TXT[r.dims.open] }}</span>
                  {{ r.open_pct != null ? (r.open_pct > 0 ? "+" : "") + fmtN(r.open_pct) + "%" : "—" }}</td>
                <td><span class="dim" :class="r.dims.tov">{{ DIM_TXT[r.dims.tov] }}</span>
                  {{ fmtN(r.tov) }}</td>
                <td><span class="dim" :class="r.dims.amt">{{ DIM_TXT[r.dims.amt] }}</span>
                  {{ r.amt_ratio != null ? fmtN(r.amt_ratio) : "—" }}</td>
                <td :class="cls(r.main_net_yi)">
                  <span class="dim" :class="r.dims.main">{{ DIM_TXT[r.dims.main] }}</span>
                  {{ r.main_net_yi != null ? fmtN(r.main_net_yi) + "亿" : "—" }}</td>
                <td><span class="dim" :class="r.dims.dist">{{ DIM_TXT[r.dims.dist] }}</span>
                  {{ r.dist_high != null ? (r.dist_high >= 0 ? "突破" : fmtN(r.dist_high) + "%") : "—" }}</td>
                <td><span class="dim" :class="r.dims.gene">{{ DIM_TXT[r.dims.gene] }}</span>
                  <span class="dimTxt">{{ r.kill_a ? "A杀×" + r.kill_a + " " : ""
                    }}{{ r.zhaban ? "炸×" + r.zhaban + " " : "" }}最高{{ r.max_streak }}板</span></td>
                <td><span class="vdBadge" :class="'v-' + r.verdict">{{ r.verdict }}</span></td>
              </tr>
              <tr v-if="expanded === r.f12" class="whyRow">
                <td colspan="11">
                  <div class="whyVerdict" :class="'v-' + r.verdict">{{ whyLine(r) }}</div>
                  <div class="whyGrid">
                    <div v-for="d in dimRows(r)" :key="d.k" class="whyItem">
                      <span class="dim" :class="d.mark">{{ DIM_TXT[d.mark] }}</span>
                      <b>{{ d.label }}</b>
                      <span class="whyAct">{{ d.actual }}</span>
                      <span class="whyRule">{{ d.rule }}</span>
                    </div>
                  </div>
                  <div class="whyFoot">本层未评估：竞价金额占流通比 ≥0.6%、上板时间（&lt;150亿需 10:30 前封板）、分时均线结构——点名称进个股详情终检</div>
                </td>
              </tr>
              </template>
            </tbody>
          </table>
          <div v-else class="empty">
            {{ loading ? "加载中…" : (note || "暂无候选") }}
          </div>
        </div>

        <p class="note">
          <template v-if="review">复盘视角（快照仍为首板日数据：收盘后/周末/节假日/盘前）：竞价涨幅/额比是首板当日的旧值，不计入判定（标 ~），下个交易日早盘快照刷新后恢复实盘口径。<br /></template>
          粗筛层不含：竞价金额占流通比、上板时间、分时均线结构——点名称进个股详情做终检。
          打板是极高风险的博弈行为，不符合条件一票否决；本页仅作客观数据筛选，不构成投资建议。
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.radarWrap { padding: 12px 0 48px; }
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
.ghostBtn {
  margin-left: auto; background: none; border: 1px solid var(--line);
  border-radius: 999px; padding: 4px 14px; font-size: 12px; font-family: inherit;
  color: var(--dim); cursor: pointer; transition: color .15s, border-color .15s;
}
.ghostBtn:hover:not(:disabled) { color: var(--txt); border-color: var(--line-strong); }
.ghostBtn:disabled { opacity: .55; cursor: not-allowed; }

.tabNav { display: flex; gap: 6px; margin-left: 12px; }
.navTab {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 6px;
  padding: 4px 12px; font-size: 12px; color: var(--dim); cursor: pointer;
  transition: all .15s ease;
}
.navTab:hover { color: var(--txt); border-color: var(--line-strong); }
.navTab.act {
  background: var(--hover); color: var(--accent); border-color: var(--accent);
  font-weight: 600;
}

/* 连板天梯看板样式 */
.ladderSection { margin-top: 14px; }
.ladderMetrics {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px; margin-bottom: 20px;
}
.metricCard {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;
}
.mLabel { font-size: 11.5px; color: var(--dim); }
.mVal { font-size: 18px; font-weight: 700; font-family: var(--mono); color: var(--txt); }
.mVal small { font-size: 12px; font-weight: 400; }
.mSub { font-size: 11px; color: var(--dim); margin-left: 4px; }
.hotCard { grid-column: span 2; }
@media (max-width: 768px) { .hotCard { grid-column: span 1; } }
.hotTags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.hotTag {
  background: var(--panel); border: 1px solid var(--line); border-radius: 4px;
  padding: 2px 6px; font-size: 11px; color: var(--txt);
}
.hotTag b { color: var(--up); font-family: var(--mono); margin-left: 2px; }

/* 阶梯容器 */
.tierGroups { display: flex; flex-direction: column; gap: 20px; }
.tierBlock {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
  padding: 14px;
}
.tierTitle { display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }
.tierBadge {
  font-size: 13px; font-weight: 700; border-radius: 4px; padding: 2px 8px;
  background: var(--hover); color: var(--txt); border-left: 3px solid var(--line-strong);
}
.tierTitle.high .tierBadge {
  background: rgba(235, 77, 75, 0.15); color: var(--up); border-left-color: var(--up);
}
.tierTitle.mid .tierBadge {
  background: rgba(243, 156, 18, 0.15); color: var(--accent); border-left-color: var(--accent);
}
.tierTitle.broken .tierBadge {
  background: rgba(149, 165, 166, 0.15); color: var(--dim); border-left-color: var(--dim);
}
.tierDesc { font-size: 12px; color: var(--dim); }

.stockGrid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.stockGrid.compact {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.stockCard {
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px; display: flex; flex-direction: column; gap: 6px;
  transition: border-color .15s, transform .15s;
}
.stockCard:hover { border-color: var(--line-strong); transform: translateY(-1px); }
.stockCard.brokenCard { opacity: 0.85; border-style: dashed; }
.scTop { display: flex; justify-content: space-between; align-items: center; }
.scName { font-weight: 600; font-size: 13.5px; color: var(--txt); text-decoration: none; }
.scName:hover { color: var(--accent); }
.streakTag {
  font-size: 11px; font-weight: 700; font-family: var(--mono);
  background: rgba(243, 156, 18, 0.12); color: var(--accent);
  padding: 1px 6px; border-radius: 4px;
}
.highTag {
  background: rgba(235, 77, 75, 0.18); color: var(--up);
}
.scMeta { display: flex; justify-content: space-between; font-size: 11px; color: var(--dim); }
.scCode { font-family: var(--mono); }
.scStats {
  display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px;
  font-size: 11px; color: var(--dim); padding-top: 4px; border-top: 1px dashed var(--line);
}
.scStats b { font-family: var(--mono); color: var(--txt); }

.bar { display: flex; align-items: center; gap: 14px; margin: 14px 0 10px; flex-wrap: wrap; }
.dayStats { font-size: 12.5px; color: var(--dim); }
.dayStats b { font-family: var(--mono); }
.vdGood { color: var(--up); }
.vdWarn { color: var(--accent); }
.vdBad { color: var(--down); }
.barSpacer { flex: 1; }
.cnt { font-size: 12px; color: var(--dim); }
.reviewTag {
  font-size: 11px; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 999px; padding: 1px 9px;
}

.tblWrap { overflow-x: auto; }
.tblWrap.loading { opacity: .55; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: right; color: var(--dim); font-weight: 500; font-size: 11.5px;
  letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line-strong);
  white-space: nowrap; user-select: none;
}
th.l, td.l { text-align: left; }
td {
  text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line);
  font-family: var(--mono); white-space: nowrap;
}
td.name { font-family: inherit; }
.nameLink { color: var(--txt); text-decoration: none; font-weight: 600; }
.nameLink:hover { color: var(--accent); }
tr:hover td { background: var(--hover); }
.dimTxt { color: var(--dim); font-family: inherit; font-size: 11.5px; }
.up { color: var(--up); }
.down { color: var(--down); }

/* 维度徽章:✓ 达标 / ~ 待确认 / ✗ 否决 */
.dim { font-weight: 700; margin-right: 3px; }
.dim.good { color: var(--up); }
.dim.warn { color: var(--accent); }
.dim.bad { color: var(--down); }

.vdBadge {
  font-size: 11px; font-weight: 600; border-radius: 999px; padding: 1px 9px;
}
.vdBadge.v-候选 { color: var(--up); border: 1px solid var(--up); }
.vdBadge.v-观察 { color: var(--accent); border: 1px solid var(--accent); }
.vdBadge.v-放弃 { color: var(--dim); border: 1px solid var(--line); }

/* ===== 判定理由展开行 ===== */
.pickRow { cursor: pointer; }
.pickRow.exp td { border-bottom: none; background: var(--panel-2); }
.whyRow td {
  text-align: left; font-family: inherit; white-space: normal;
  background: var(--panel-2); padding: 4px 14px 14px;
}
.whyVerdict { font-size: 12.5px; font-weight: 600; margin: 4px 0 8px; }
.whyVerdict.v-候选 { color: var(--up); }
.whyVerdict.v-观察 { color: var(--accent); }
.whyVerdict.v-放弃 { color: var(--dim); }
.whyGrid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 6px 20px;
}
.whyItem { font-size: 12px; color: var(--txt); display: flex; gap: 6px; align-items: baseline; }
.whyItem b { font-weight: 600; }
.whyAct { font-family: var(--mono); }
.whyRule { color: var(--dim); font-size: 11.5px; }
.whyFoot { margin-top: 10px; color: var(--dim); font-size: 11.5px; }

.note { margin-top: 14px; color: var(--dim); font-size: 12px; line-height: 1.8; }
.empty { padding: 48px 0; text-align: center; color: var(--dim); font-size: 13px; line-height: 1.9; }
</style>
