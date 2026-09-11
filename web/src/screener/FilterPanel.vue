<script setup>
/* ===== 筛选面板(移植自旧 index.html #filterPanel,事件行为对齐旧 screener-app.js)===== */
import { computed, inject, nextTick, onMounted, onUnmounted, ref } from "vue";
import { Select } from "ant-design-vue";
import { api } from "../api/client";
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
const { presets, savePreset, applyPreset, deletePreset } = s;

// 「策略」:选择即加载;常态只有 下拉+存策略 两个小控件,
// 点「存策略」才换成 名称输入+✓/×(Enter 保存 Esc 取消),选中策略后可 × 删除
const presetSel = ref("");
const presetName = ref("");
const saving = ref(false);
const nameInput = ref(null);
function onPickPreset() {
  if (presetSel.value) applyPreset(presetSel.value);
}
function startSave() {
  saving.value = true;
  nextTick(() => nameInput.value && nameInput.value.focus());
}
function cancelSave() {
  saving.value = false;
  presetName.value = "";
}
function onSavePreset() {
  if (savePreset(presetName.value)) {
    presetSel.value = presetName.value.trim().slice(0, 16);
    cancelSave();
  }
}
function onNameKey(e) {
  if (e.key === "Escape") cancelSave();
}
function onDelPreset() {
  if (!presetSel.value) return;
  deletePreset(presetSel.value);
  presetSel.value = "";
}

// 「+ 指标」下拉
const metricAddSel = ref("");
const addOptions = computed(() => metricAddOptions(metrics.value));
function onAddMetric() {
  if (metricAddSel.value) addMetricByKey(metricAddSel.value);
  metricAddSel.value = "";
}

// 行业多选(可输入搜索):选项带命中数;全市场口径,与勾选的市场无关
const industryOptions = computed(() =>
  industries.value.map((x) => ({ value: x.name, label: `${x.name} (${x.n})` })));

// 搜索联想:代码/名称/拼音简写 → 下拉点选(复用自选股搜索接口)
const kwDrop = ref([]);
const kwOpen = ref(false);
const kwActive = ref(0);
let sugTimer = null;
function onKw() {
  onKwInput();
  clearTimeout(sugTimer);
  const q = kw.value.trim();
  if (!q) { kwDrop.value = []; kwOpen.value = false; return; }
  sugTimer = setTimeout(async () => {
    try {
      const d = await api("/api/watchlist/search?kw=" + encodeURIComponent(q));
      kwDrop.value = (d.rows || []).slice(0, 8);
      kwActive.value = 0;
      kwOpen.value = true;
    } catch (e) { /* 联想失败不影响输入 */ }
  }, 250);
}
function pickKw(r) {
  kw.value = r.f12;
  kwOpen.value = false;
  refilter();
}
function onKwKey(e) {
  if (!kwOpen.value || !kwDrop.value.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault(); e.stopPropagation();
    kwActive.value = (kwActive.value + 1) % kwDrop.value.length;
  } else if (e.key === "ArrowUp") {
    e.preventDefault(); e.stopPropagation();
    kwActive.value = (kwActive.value - 1 + kwDrop.value.length) % kwDrop.value.length;
  } else if (e.key === "Enter") {
    e.stopPropagation();  // 下拉开着时 Enter 是选中,不触发一键查询
    const r = kwDrop.value[kwActive.value];
    if (r) pickKw(r);
  } else if (e.key === "Escape") {
    kwOpen.value = false;
  }
}

// 回车直接查询(旧版为 document 级 keydown);策略命名输入中除外(Enter 是保存)
function onKeydown(e) {
  if (e.key === "Enter" && !querying.value && !saving.value) run();
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
          <Select v-model:value="industry" mode="multiple" show-search allow-clear
                  :options="industryOptions" option-filter-prop="label"
                  placeholder="全部行业" :max-tag-count="1"
                  style="width:150px" :disabled="!industryReady"
                  :title="industryReady ? '' : '行业列表加载中…'"
                  @change="refilter" />
        </div>
        <div class="field kwField"><span>搜索</span>
          <input type="text" id="kw" v-model="kw" placeholder="代码 / 名称"
                 enterkeyhint="search" style="width:140px"
                 @input="onKw" @keydown="onKwKey" @blur="kwOpen = false">
          <div v-show="kwOpen && kwDrop.length" class="kwDrop">
            <button v-for="(r, i) in kwDrop" :key="r.f12"
                    :class="{ act: i === kwActive }"
                    @mouseenter="kwActive = i" @mousedown.prevent="pickKw(r)">
              <b>{{ r.f14 }}</b>
              <span class="kdCode">{{ r.f12 }}</span>
              <span v-if="r.pinyin" class="kdPy">{{ r.pinyin }}</span>
              <span class="kdInd">{{ r.f100 || "" }}</span>
            </button>
          </div>
        </div>
        <div class="spacer"></div>
        <select class="auxSel" id="metricAdd" v-model="metricAddSel"
                title="添加自定义指标区间过滤" @change="onAddMetric">
          <option value="">+ 指标</option>
          <option v-for="m in addOptions" :key="m.k" :value="m.k">{{ m.name }}{{ m.unit ? "（" + m.unit + "）" : "" }}</option>
        </select>
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
        <div class="spacer"></div>
        <div class="presetBox">
          <template v-if="!saving">
            <select v-model="presetSel" title="选择已存策略,即选即用" @change="onPickPreset">
              <option value="">策略…</option>
              <option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
            <button v-show="presetSel" class="iconX" title="删除该策略" @click="onDelPreset">×</button>
            <button class="miniBtn" title="把当前筛选条件存为策略" @click="startSave">存策略</button>
          </template>
          <template v-else>
            <input ref="nameInput" type="text" v-model="presetName" placeholder="策略名"
                   maxlength="16" @keyup.enter="onSavePreset" @keydown="onNameKey">
            <button class="miniBtn on" @click="onSavePreset">✓</button>
            <button class="iconX" title="取消" @click="cancelSave">×</button>
          </template>
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

<style scoped>
/* 两行布局:右侧辅助控件(指标/策略)缩小一号,不与主条件抢视觉 */
.spacer { flex: 1; }
.auxSel {
  width: 104px; cursor: pointer;
  font-size: 12px !important; padding: 5px 8px !important;
  color: var(--dim);
}
.presetBox { display: flex; align-items: center; gap: 6px; }
.presetBox select, .presetBox input {
  font-size: 12px !important; padding: 5px 8px !important;
}
.presetBox select { width: 104px; cursor: pointer; }
.presetBox input { width: 92px; }
.miniBtn {
  background: none; border: 1px solid var(--line); border-radius: 999px;
  color: var(--dim); padding: 4px 11px; font-size: 12px; font-family: inherit;
  cursor: pointer; white-space: nowrap; transition: all .15s;
}
.miniBtn:hover { color: var(--txt); border-color: var(--line-strong); }
.miniBtn.on { color: var(--accent); border-color: var(--accent); }
.iconX {
  background: none; border: 1px solid var(--line); border-radius: 50%;
  width: 22px; height: 22px; color: var(--dim); font-size: 12px;
  cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
  transition: all .15s; flex-shrink: 0;
}
.iconX:hover { color: var(--up); border-color: var(--up); }
@media (max-width: 768px) {
  .spacer { display: none; }
  .auxSel, .presetBox { width: 100%; }
  .presetBox select, .presetBox input { flex: 1; }
}

/* ===== 搜索联想下拉(与自选股搜索同款) ===== */
.kwField { position: relative; }
.kwDrop {
  position: absolute; top: calc(100% + 4px); left: 38px; min-width: 260px; z-index: 40;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 10px; overflow: hidden;
  box-shadow: 0 12px 32px rgba(0, 0, 0, .14);
}
.kwDrop button {
  display: flex; align-items: baseline; gap: 8px; width: 100%;
  background: none; border: none; border-top: 1px solid var(--line);
  padding: 8px 12px; cursor: pointer; font-family: inherit; font-size: 12.5px;
  color: var(--txt); text-align: left;
}
.kwDrop button:first-child { border-top: none; }
.kwDrop button:hover, .kwDrop button.act { background: var(--hover); }
.kdCode { color: var(--dim); font-family: var(--mono); font-size: 11.5px; }
.kdPy {
  color: var(--dim); font-family: var(--mono); font-size: 10.5px;
  border: 1px solid var(--line); border-radius: 4px; padding: 0 4px;
}
.kdInd { margin-left: auto; color: var(--dim); font-size: 11.5px; }
</style>
