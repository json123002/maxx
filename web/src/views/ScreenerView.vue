<script setup>
/* ===== 换手率筛选页组装:筛选面板 + 结果区 + 分析弹窗
   (初始化对齐旧 screener-app.js:恢复上次条件 → URL 参数覆盖 → 可选自动查询)===== */
import { computed, onMounted, provide, ref } from "vue";
import { useRoute } from "vue-router";
import FilterPanel from "../screener/FilterPanel.vue";
import ResultsPanel from "../screener/ResultsPanel.vue";
import AnalysisModal from "../analysis/AnalysisModal.vue";
import { useScreener } from "../screener/useScreener";
import { track } from "../api/client";

const route = useRoute();
const s = useScreener();
provide("screener", s);
const { tab, allRows, hasRun, hasMore, restoreFilters, applyUrlQuery, run } = s;

// 分析弹窗(同事实现,契约:ref.open(code),K线/资金流内部自取)
const anaRef = ref(null);
function openAnalysis(code) {
  track("analysis_view", code);
  anaRef.value && anaRef.value.open(code);
}

// 初始化:恢复上次条件 → URL 参数覆盖(hash 模式下取 route.query)
restoreFilters();
const auto = applyUrlQuery(route.query);
onMounted(() => {
  if (auto) run();
});

// 旧版挂在 body 上的 data-tab / data-empty / hasmore,现挂在本页根 div.screenerRoot
const emptyFlag = computed(() => (!hasRun.value || allRows.value.length === 0 ? "1" : "0"));
</script>

<template>
  <div class="screenerRoot" :data-tab="tab" :data-empty="emptyFlag" :class="{ hasmore: hasMore }">
    <FilterPanel />
    <ResultsPanel @analysis="openAnalysis" />
    <AnalysisModal ref="anaRef" :rows="allRows" />
  </div>
</template>
