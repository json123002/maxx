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
const review = ref(false); // 收盘落库后的复盘视角(竞价/额比为今日实际值)
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

onMounted(load);
</script>

<template>
  <div class="radarWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">涨停雷达 · 一进二</span>
        <span class="secNote">昨日首板 × 今日竞价/量能/资金粗筛（打板战法）</span>
        <button class="ghostBtn" :disabled="loading" @click="load">
          {{ loading ? "刷新中…" : "刷新" }}
        </button>
      </div>

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
        <template v-if="review">今日已收盘（复盘视角）：显示今日首板；竞价涨幅/额比是首板当日的旧值，不计入判定（标 ~），下个交易日早盘恢复实盘口径。<br /></template>
        粗筛层不含：竞价金额占流通比、上板时间、分时均线结构——点名称进个股详情做终检。
        打板是极高风险的确定性交易，不符合条件一票否决；本页仅作客观数据筛选，不构成投资建议。
      </p>
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
