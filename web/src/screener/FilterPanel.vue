<script setup>
/* ===== 筛选面板(移植自旧 index.html #filterPanel,事件行为对齐旧 screener-app.js)===== */
import { computed, inject, onMounted, onUnmounted, ref } from "vue";
import { MKT_DEFS } from "./useScreener";
import { metricAddOptions, metricDef } from "./metrics";

const s = inject("screener");
const {
  tMin, tMax, cMin, cMax, kw, industry, mkts, noST, noSuspend, metrics,
  querying, progressVisible, statusTxt, panelOpen, industries, industryReady, summary,
} = s;
const {
  run, cancel, refilter, onKwInput, onMktChange,
  addMetricByKey, removeMetricByKey, onMetricInput,
} = s;

// 「+ 添加指标」下拉
const metricAddSel = ref("");
const addOptions = computed(() => metricAddOptions(metrics.value));
function onAddMetric() {
  if (metricAddSel.value) addMetricByKey(metricAddSel.value);
  metricAddSel.value = "";
}

// 回车直接查询(旧版为 document 级 keydown)
function onKeydown(e) {
  if (e.key === "Enter" && !querying.value) run();
}
onMounted(() => document.addEventListener("keydown", onKeydown));
onUnmounted(() => document.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="panel" id="filterPanel" :class="{ open: panelOpen }">
    <button class="filtersToggle" id="filtersToggle" @click="panelOpen = !panelOpen">
      筛选条件
      <span class="sum" id="filterSum">{{ summary }}</span>
      <span class="arrow">▾</span>
    </button>
    <div class="filtersBody">
      <div class="row">
        <div class="field"><span>换手率 %</span>
          <input type="number" id="tMin" v-model="tMin" placeholder="最低" min="0" step="0.5" inputmode="decimal" style="width:76px" @input="refilter"> —
          <input type="number" id="tMax" v-model="tMax" placeholder="最高" min="0" step="0.5" inputmode="decimal" style="width:76px" @input="refilter">
        </div>
        <div class="field"><span>涨跌幅 %</span>
          <input type="number" id="cMin" v-model="cMin" placeholder="最低" step="0.5" inputmode="decimal" style="width:76px" @input="refilter"> —
          <input type="number" id="cMax" v-model="cMax" placeholder="最高" step="0.5" inputmode="decimal" style="width:76px" @input="refilter">
        </div>
        <div class="field"><span>行业</span>
          <select id="industrySel" v-model="industry" style="width:150px" :disabled="!industryReady"
                  :title="industryReady ? '' : '先执行一键查询，再按行业筛选'" @change="refilter">
            <option value="">全部行业</option>
            <option v-for="x in industries" :key="x.name" :value="x.name">{{ x.name }} ({{ x.n }})</option>
          </select>
        </div>
        <div class="field"><span>搜索</span>
          <input type="text" id="kw" v-model="kw" placeholder="代码 / 名称" enterkeyhint="search" style="width:120px" @input="onKwInput">
        </div>
      </div>
      <div class="row" style="margin-top:16px">
        <div class="field mkts"><span>市场</span>
          <label v-for="(m, i) in MKT_DEFS" :key="m.value" :class="{ on: mkts[i] }">
            <input type="checkbox" class="mkt" :value="m.value" v-model="mkts[i]" @change="onMktChange">{{ m.label }}
          </label>
        </div>
        <label class="chk" :class="{ on: noST }"><input type="checkbox" id="noST" v-model="noST" @change="refilter">剔除 ST / 退市</label>
        <label class="chk" :class="{ on: noSuspend }"><input type="checkbox" id="noSuspend" v-model="noSuspend" @change="refilter">剔除停牌</label>
        <button class="pill" id="goBtn" :disabled="querying" @click="run">{{ querying ? "查询中…" : "一键查询" }}</button>
      </div>
      <div class="row" style="margin-top:16px">
        <div class="field"><span>自定义指标</span>
          <select id="metricAdd" v-model="metricAddSel" style="width:160px" @change="onAddMetric">
            <option value="">+ 添加指标</option>
            <option v-for="m in addOptions" :key="m.k" :value="m.k">{{ m.name }}{{ m.unit ? "（" + m.unit + "）" : "" }}</option>
          </select>
        </div>
      </div>
      <div id="metricsBox">
        <div class="metric-line" v-for="m in metrics" :key="m.k">
          <span class="mName">{{ metricDef(m.k).name }}<span class="mUnit" v-if="metricDef(m.k).unit">（{{ metricDef(m.k).unit }}）</span></span>
          <input type="number" class="mMin" placeholder="最低" step="any" inputmode="decimal" v-model="m.min" @input="onMetricInput"> —
          <input type="number" class="mMax" placeholder="最高" step="any" inputmode="decimal" v-model="m.max" @input="onMetricInput">
          <button class="mDel" title="移除指标" @click="removeMetricByKey(m.k)">×</button>
        </div>
      </div>
      <div id="progressWrap" v-show="progressVisible">
        <div id="progressBar"><i style="width:100%"></i></div>
        <div id="status">
          <span id="statusTxt">{{ statusTxt }}</span>
          <button id="cancelBtn" v-show="querying" @click="cancel">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>
