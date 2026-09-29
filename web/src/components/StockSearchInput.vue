<script setup>
/* ===== 股票搜索输入(防抖联想,数据源 /api/watchlist/search)=====
   输入代码/名称/拼音 → 下拉候选;选中 emit("select", {code, name})。 */
import { ref } from "vue";
import { api } from "../api/client";

const emit = defineEmits(["select"]);

const kw = ref("");
const rows = ref([]);
const open = ref(false);
let timer = null;

function onInput() {
  clearTimeout(timer);
  const v = kw.value.trim();
  if (!v) { rows.value = []; open.value = false; return; }
  timer = setTimeout(async () => {
    try {
      const d = await api("/api/watchlist/search?" + new URLSearchParams({ kw: v }));
      rows.value = d.rows.slice(0, 10);
      open.value = true;
    } catch (e) { /* 联想失败静默 */ }
  }, 300);
}

function pick(r) {
  emit("select", { code: r.f12, name: r.f14 });
  kw.value = "";
  rows.value = [];
  open.value = false;
}

function onBlur() {
  setTimeout(() => { open.value = false; }, 150);   // 让点击候选先生效
}
</script>

<template>
  <div class="ssRoot">
    <input v-model="kw" class="ssIn" placeholder="代码 / 名称 / 拼音"
           @input="onInput" @blur="onBlur" @focus="rows.length && (open = true)" />
    <div v-if="open && rows.length" class="ssDrop">
      <div v-for="r in rows" :key="r.f12" class="ssItem" @click="pick(r)">
        <b>{{ r.f14 }}</b><span>{{ r.f12 }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ssRoot { position: relative; }
.ssIn {
  width: 100%; background: var(--panel-2); border: 1px solid var(--line);
  border-radius: 8px; color: var(--txt); font-size: 13px; padding: 7px 10px;
  font-family: inherit; outline: none;
}
.ssIn:focus { border-color: var(--accent); }
.ssDrop {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 20;
  background: var(--panel); border: 1px solid var(--line-strong); border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25); overflow: hidden;
}
.ssItem {
  display: flex; justify-content: space-between; gap: 10px;
  padding: 7px 10px; cursor: pointer; font-size: 13px;
}
.ssItem span { color: var(--dim); font-family: var(--mono); font-size: 12px; }
.ssItem:hover { background: var(--hover); }
</style>
