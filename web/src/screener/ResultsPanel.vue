<script setup>
/* ===== 结果区:页签 / 排序 / 桌面表格 / 手机卡片 / 无限滚动 / CSV 导出
   (移植自旧 screener-app.js 渲染部分,表格和卡片两套都渲染,显隐由全局 css 媒体查询控制)===== */
import { computed, inject, onMounted, onUnmounted, ref } from "vue";
import { message } from "ant-design-vue";
import { cls, fmtN, fmtYiC, fmtYiT, quoteUrl } from "../utils/format";
import { fmtMetric, metricCardExtras } from "./metrics";
import { IS_MOBILE } from "./useScreener";
import { inWatch, loadWatchCodes, toggleWatch } from "../stores/watchlist";

const emit = defineEmits(["analysis"]);

const s = inject("screener");
const {
  tab, allRows, lastTotal, hasRun, metrics, senti, srcBadge,
  sortKey, sortDir, indSortKey, indSortDir,
  sortChips, extraCols, tableRows, cardRows, indRows, hasMore, capNote,
} = s;
const { setSort, setIndSort, loadMore, exportCSV, selectIndustry } = s;

// 桌面个股表头:基础列(自定义指标列由 extraCols 动态追加,最后跟「分析」列)
const stockHead = [
  { k: "f12", name: "代码", l: true },
  { k: "f14", name: "名称", l: true },
  { k: "f2", name: "最新价" },
  { k: "f3", name: "涨跌幅 %" },
  { k: "f8", name: "换手率 %" },
  { k: "f100", name: "行业", l: true },
  { k: "f6", name: "成交额" },
  { k: "f20", name: "总市值" },
  { k: "f9", name: "市盈率" },
];
const indHead = [
  { k: "name", name: "行业", l: true },
  { k: "n", name: "股票数" },
  { k: "avgT", name: "平均换手率 %" },
  { k: "avgC", name: "平均涨跌幅 %" },
  { k: "upN", name: "上涨家数" },
  { k: "amount", name: "总成交额" },
];

// markSorted 视觉态:当前排序列高亮 + 升/降箭头样式
function stockThCls(k) {
  return { sorted: k === sortKey.value, asc: k === sortKey.value && sortDir.value === 1, desc: k === sortKey.value && sortDir.value === -1 };
}
function indThCls(k) {
  return { sorted: k === indSortKey.value, asc: k === indSortKey.value && indSortDir.value === 1, desc: k === indSortKey.value && indSortDir.value === -1 };
}
function onStockTh(k) {
  setSort(k, k === "f12" || k === "f14" || k === "f100" ? 1 : -1);
}

// 手机卡片:涨跌幅文本 / 附加指标文本
function chgText(v) {
  return typeof v === "number" ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "—";
}
function cardExtras(r) {
  return metricCardExtras(metrics.value, r);
}
// 行业卡片固定按平均换手率降序(旧版行为,不跟随行业表排序)
const indCards = computed(() => indRows.value.slice().sort((a, b) => b.avgT - a.avgT));

// 行业标签点击(无行业的「—」标签不触发,对齐旧版 data-ind 为空直接 return)
function onTag(ind) {
  if (!ind) return;
  selectIndustry(ind);
}

// 自选星标:登录后拉一次代码集合;点击切换,失败提示
loadWatchCodes();
async function onStar(r) {
  const added = !inWatch(r.f12);
  try {
    await toggleWatch(r.f12, added);
    message.success(added ? "已添加自选 " + r.f14 : "已移除自选 " + r.f14);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

// 空结果提示(手机端)
const emptyHtml = computed(() =>
  hasRun.value && !allRows.value.length
    ? "没有符合条件的股票<br>试试放宽筛选条件"
    : "设置条件后点【一键查询】<br>数据来自东方财富，仅作客观筛选，不构成投资建议"
);

// 无限滚动:接近底部自动加载(仅手机端可见)
const moreBtn = ref(null);
let observer = null;
onMounted(() => {
  if ("IntersectionObserver" in window && moreBtn.value) {
    observer = new IntersectionObserver((es) => {
      if (es[0].isIntersecting && IS_MOBILE() && hasMore.value && tab.value === "stock") loadMore();
    }, { rootMargin: "300px" });
    observer.observe(moreBtn.value);
  }
});
onUnmounted(() => observer && observer.disconnect());
</script>

<template>
  <div class="panel results" id="resultsPanel">
    <div class="toolbar">
      <div class="meta">
        <div class="tabs">
          <button id="tabStock" :class="{ on: tab === 'stock' }" @click="tab = 'stock'">个股明细</button>
          <button id="tabInd" :class="{ on: tab === 'ind' }" @click="tab = 'ind'">行业汇总</button>
        </div>
        <span>共 <span id="count">{{ lastTotal }}</span> 只符合条件</span>
        <span id="sentiBadge" class="sentiBadge" :class="'lv' + senti.lv" v-show="senti.show" :title="senti.title">{{ senti.text }}</span>
        <span id="capNote" v-show="capNote.show">{{ capNote.text }}</span>
        <span class="metaSpacer"></span>
        <span class="hint">点击列头排序 · 点击行业标签快速筛选</span>
        <span id="srcBadgeM" class="srcBadge" :class="{ rt: srcBadge.rt }">{{ srcBadge.text }}</span>
        <button class="ghost" id="csvBtn" v-show="allRows.length" @click="exportCSV">导出 CSV</button>
      </div>
      <div class="sortBar" id="sortBar">
        <button v-for="c in sortChips" :key="c.k" class="sortChip" :class="{ on: c.k === sortKey }" @click="setSort(c.k, -1)">
          {{ c.name + (c.k === sortKey ? (sortDir === -1 ? " ↓" : " ↑") : "") }}
        </button>
      </div>
    </div>

    <div class="tblWrap" id="stockWrap">
      <table id="stockTbl">
        <thead>
          <tr>
            <th style="cursor:default;width:34px" title="自选"></th>
            <th v-for="h in stockHead" :key="h.k" :class="[h.l ? 'l' : '', stockThCls(h.k)]" @click="onStockTh(h.k)">{{ h.name }}</th>
            <th v-for="d in extraCols" :key="d.k" :class="stockThCls(d.k)" @click="onStockTh(d.k)">{{ d.name + (d.unit ? "(" + d.unit + ")" : "") }}</th>
            <th style="cursor:default">分析</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in tableRows" :key="r.f12">
            <td>
              <button class="starBtn" :class="{ on: inWatch(r.f12) }"
                      :title="inWatch(r.f12) ? '移除自选' : '添加自选'" @click="onStar(r)">
                <svg width="14" height="14" viewBox="0 0 24 24" :fill="inWatch(r.f12) ? 'currentColor' : 'none'"
                     stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
                  <path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z" />
                </svg>
              </button>
            </td>
            <td class="l">{{ r.f12 }}</td>
            <td class="l name"><a class="nameLink" :href="quoteUrl(r.f12)" target="_blank" rel="noopener">{{ r.f14 }}</a><span v-if="r.limit_up === 1" class="lmBadge up">涨停</span><span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span></td>
            <td>{{ fmtN(r.f2) }}</td>
            <td :class="cls(r.f3)">{{ fmtN(r.f3) }}</td>
            <td><b>{{ fmtN(r.f8) }}</b></td>
            <td class="l"><span class="tag" @click="onTag(r.f100)">{{ r.f100 || "—" }}</span></td>
            <td>{{ fmtYiT(r.f6) }}</td>
            <td>{{ fmtYiT(r.f20) }}</td>
            <td>{{ fmtN(r.f9, 1) }}</td>
            <td v-for="d in extraCols" :key="d.k">{{ fmtMetric(d, r[d.k]) }}</td>
            <td><button class="anaBtn" @click="emit('analysis', r.f12)">分析</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="tblWrap" id="indWrap">
      <table id="indTbl">
        <thead>
          <tr>
            <th v-for="h in indHead" :key="h.k" :class="[h.l ? 'l' : '', indThCls(h.k)]" @click="setIndSort(h.k)">{{ h.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="x in indRows" :key="x.name">
            <td class="l"><span class="tag" @click="selectIndustry(x.name)">{{ x.name }}</span></td>
            <td>{{ x.n }}</td>
            <td><b>{{ x.avgT.toFixed(2) }}</b></td>
            <td :class="cls(x.avgC)">{{ x.avgC.toFixed(2) }}</td>
            <td class="up">{{ x.upN }}</td>
            <td>{{ fmtYiT(x.amount) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div id="list">
      <a class="card" v-for="r in cardRows" :key="r.f12" :href="quoteUrl(r.f12)" target="_blank" rel="noopener">
        <div class="c1">
          <div class="nm"><b>{{ r.f14 }}</b><span class="cd">{{ r.f12 }}</span><span v-if="r.limit_up === 1" class="lmBadge up">涨停</span><span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span></div>
          <div class="pr"><b>{{ fmtN(r.f2) }}</b><span class="chg" :class="cls(r.f3)">{{ chgText(r.f3) }}</span></div>
        </div>
        <div class="c2">
          <span class="tov">换手 {{ fmtN(r.f8) }}%</span>
          <span class="tag" @click.prevent="onTag(r.f100)">{{ r.f100 || "—" }}</span>
          <span class="sub">额 {{ fmtYiC(r.f6) }} · 市值 {{ fmtYiC(r.f20) }} · PE {{ fmtN(r.f9, 1) }}{{ cardExtras(r) }}</span>
          <button class="anaBtn" @click.prevent.stop="emit('analysis', r.f12)">分析</button>
          <button class="starBtn" :class="{ on: inWatch(r.f12) }"
                  :title="inWatch(r.f12) ? '移除自选' : '添加自选'" @click.prevent.stop="onStar(r)">
            <svg width="14" height="14" viewBox="0 0 24 24" :fill="inWatch(r.f12) ? 'currentColor' : 'none'"
                 stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
              <path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z" />
            </svg>
          </button>
        </div>
      </a>
    </div>

    <div id="indList">
      <div class="icard" v-for="x in indCards" :key="x.name" @click="selectIndustry(x.name)">
        <div class="c1"><b>{{ x.name }}</b><span style="color:var(--dim);font-size:12.5px">{{ x.n }} 只 · 涨 {{ x.upN }} 家</span></div>
        <div class="nums">
          <span>平均换手 <b style="color:var(--accent)">{{ x.avgT.toFixed(2) }}%</b></span>
          <span>平均涨跌 <b :class="cls(x.avgC)">{{ x.avgC.toFixed(2) }}%</b></span>
          <span>成交额 <b>{{ fmtYiC(x.amount) }}</b></span>
        </div>
      </div>
    </div>

    <button id="moreBtn" ref="moreBtn" @click="loadMore">加载更多</button>
    <div class="empty" id="emptyHint" v-html="emptyHtml"></div>
  </div>
</template>
