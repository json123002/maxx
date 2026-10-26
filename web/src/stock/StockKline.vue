<script setup>
/* ===== 个股多周期K线:5/20/30分钟 + 日K,按代码和周期缓存 ===== */
import { computed, reactive, ref, watch } from "vue";
import { fetchPeriodKline, KLINE_PERIODS } from "../analysis/kline-periods";
import KChart from "./KChart.vue";

const props = defineProps({
  code: { type: String, required: true },
  compact: { type: Boolean, default: true },
  dailyBars: { type: Array, default: null },
  dailyLoading: { type: Boolean, default: false },
  dailySource: { type: String, default: "" },
});

const period = ref("d");
const cache = reactive({});
const keyOf = (code = props.code, p = period.value) => `${code}:${p}`;
const current = computed(() => cache[keyOf()] || null);
const bars = computed(() => current.value?.bars || []);

async function load() {
  const code = props.code, p = period.value, key = keyOf(code, p);
  if (!code || cache[key]?.bars || cache[key]?.loading) return;
  if (p === "d") {
    if (props.dailyLoading) return;
    if (props.dailyBars?.length) {
      cache[key] = { loading: false, bars: props.dailyBars, source: props.dailySource, error: false };
      return;
    }
  }
  cache[key] = { loading: true, bars: null, source: "", error: false };
  try {
    const d = await fetchPeriodKline(code, p);
    cache[key] = { loading: false, bars: d.bars, source: d.source, error: false };
  } catch {
    cache[key] = { loading: false, bars: null, source: "", error: true };
  }
}

function retry() {
  delete cache[keyOf()];
  load();
}

watch(() => [props.code, period.value, props.dailyLoading], load, { immediate: true });
watch(() => props.dailyBars, (bars) => {
  if (period.value === "d" && bars?.length) {
    cache[keyOf()] = { loading: false, bars, source: props.dailySource, error: false };
  }
});
</script>

<template>
  <div class="periodKline">
    <div class="periodBar">
      <div class="periodSeg" aria-label="K线周期">
        <button v-for="p in KLINE_PERIODS" :key="p.key" :class="{ on: period === p.key }"
                :aria-pressed="period === p.key" @click="period = p.key">{{ p.name }}</button>
      </div>
      <span class="periodSource">{{ current?.source || "东方财富行情" }}</span>
      <span class="periodHint">滚轮缩放 · 拖拽平移 · 双击复位</span>
    </div>
    <div class="periodBody">
      <KChart v-if="bars.length || current?.loading" :bars="bars"
              :loading="current?.loading" :compact="compact" />
      <div v-else class="periodEmpty">
        <span>{{ current?.error ? "K 线数据加载失败" : "暂无 K 线数据" }}</span>
        <button @click="retry">重新加载</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.periodKline { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.periodBar {
  flex: none; display: flex; align-items: center; gap: 12px; min-height: 38px;
  padding: 0 4px 9px; overflow-x: auto; scrollbar-width: thin;
}
.periodSeg {
  flex: none; display: inline-flex; gap: 2px; padding: 3px;
  border: 1px solid var(--line); border-radius: 9px; background: var(--panel-2);
}
.periodSeg button {
  min-width: 48px; height: 26px; padding: 0 10px; border: 0; border-radius: 6px;
  background: transparent; color: var(--dim); font-family: inherit; font-size: 11.5px; font-weight: 600; cursor: pointer;
  transition: color .15s, background .15s, box-shadow .15s;
}
.periodSeg button:hover { color: var(--txt); }
.periodSeg button.on { color: var(--txt); background: var(--panel); box-shadow: 0 2px 8px rgba(0,0,0,.16); }
.periodSource { flex: none; color: var(--dim); font-size: 10.5px; }
.periodHint { margin-left: auto; flex: none; color: var(--dim); font-size: 10.5px; }
.periodBody { flex: 1; min-height: 0; }
.periodEmpty {
  height: 100%; min-height: 220px; display: flex; align-items: center; justify-content: center;
  gap: 12px; color: var(--dim); font-size: 12px;
}
.periodEmpty button { border: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
@media (max-width: 720px) {
  .periodHint { display: none; }
  .periodSource { margin-left: auto; }
  .periodSeg button { min-width: 43px; padding: 0 7px; }
}
</style>
