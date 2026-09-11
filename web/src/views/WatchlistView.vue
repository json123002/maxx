<script setup>
/* ===== 我的自选：搜索添加 + 自选列表(实时快照行情) =====
   交互:顶部搜索框防抖查询 → 下拉结果一键添加;列表行 hover 显示移除。
   数据源:后端 watchlist 关联 latest 快照,与筛选页同一份行情。 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { api } from "../api/client";
import { cls, fmtN, fmtYiT } from "../utils/format";
import { watchState } from "../stores/watchlist";
import AnalysisModal from "../analysis/AnalysisModal.vue";

const router = useRouter();

/* ---------- 点名称进自研个股详情页;「分析」才开战法弹窗 ---------- */
function goStock(code) {
  router.push("/stock/" + code);
}
const anaRef = ref(null);
function openAnalysis(code) {
  anaRef.value && anaRef.value.open(code);
}

/* ---------- 自选列表 ---------- */
const rows = ref([]);
const loading = ref(false);
const fetchedAt = ref("");

async function load() {
  loading.value = true;
  try {
    const d = await api("/api/watchlist");
    rows.value = d.rows;
    watchState.codes = new Set(d.rows.map((r) => r.f12));
    watchState.loaded = true;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function remove(code) {
  try {
    await api("/api/watchlist/" + code, { method: "DELETE" });
    rows.value = rows.value.filter((r) => r.f12 !== code);
    watchState.codes.delete(code);
    message.success("已移除 " + code);
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  }
}

/* ---------- 搜索添加 ---------- */
const kw = ref("");
const results = ref([]);
const searching = ref(false);
const dropOpen = ref(false);
const searchBox = ref(null);
let timer = null;

function onInput() {
  clearTimeout(timer);
  const q = kw.value.trim();
  if (!q) {
    results.value = [];
    dropOpen.value = false;
    return;
  }
  timer = setTimeout(async () => {
    searching.value = true;
    try {
      const d = await api("/api/watchlist/search?kw=" + encodeURIComponent(q));
      results.value = d.rows;
      dropOpen.value = true;
    } catch (err) {
      if (err.message !== "unauthorized") message.error(err.message || "搜索失败");
    } finally {
      searching.value = false;
    }
  }, 250);
}

async function add(r) {
  try {
    await api("/api/watchlist", { method: "POST", body: { code: r.f12 } });
    watchState.codes.add(r.f12);
    message.success("已添加 " + r.f14 + " " + r.f12);
    // 添加完成:清空搜索框并收起下拉,回到干净的输入态
    kw.value = "";
    results.value = [];
    dropOpen.value = false;
    load(); // 列表置顶刷新
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  }
}

// 点击组件外关闭下拉
function onDocClick(e) {
  if (searchBox.value && !searchBox.value.contains(e.target)) dropOpen.value = false;
}

const showDrop = computed(() => dropOpen.value && (results.value.length || searching.value));

onMounted(() => {
  load();
  document.addEventListener("click", onDocClick);
});
onBeforeUnmount(() => {
  clearTimeout(timer);
  document.removeEventListener("click", onDocClick);
});
</script>

<template>
  <div class="watchWrap">
    <!-- ===== 搜索添加 ===== -->
    <div class="searchBox" ref="searchBox">
      <div class="searchInner" :class="{ open: showDrop }">
        <svg class="sIcon" width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
        </svg>
        <input
          v-model="kw"
          class="sInput"
          placeholder="输入代码或名称，添加自选…"
          @input="onInput"
          @focus="results.length && (dropOpen = true)"
        />
        <span v-if="searching" class="sSpin"></span>
      </div>
      <div v-show="showDrop" class="drop">
        <div v-if="!results.length && searching" class="dropEmpty">搜索中…</div>
        <div v-else-if="!results.length" class="dropEmpty">没有找到相关股票</div>
        <button
          v-for="r in results" :key="r.f12" class="dropItem"
          :disabled="r.added" @click="add(r)"
        >
          <span class="dName">{{ r.f14 }}</span>
          <span class="dCode">{{ r.f12 }}</span>
          <span class="dInd">{{ r.f100 || "—" }}</span>
          <span class="dTov">换手 {{ fmtN(r.f8) }}%</span>
          <span class="dAct" :class="{ on: r.added }">{{ r.added ? "已自选" : "+ 自选" }}</span>
        </button>
      </div>
    </div>

    <!-- ===== 自选列表 ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">自选列表</span>
        <span class="secNote">共 {{ rows.length }} 只 · 行情取自最新快照</span>
        <button class="ghostBtn" :disabled="loading" @click="load">
          {{ loading ? "刷新中…" : "刷新" }}
        </button>
      </div>

      <div v-if="rows.length" class="list">
        <div v-for="r in rows" :key="r.f12" class="row">
          <button class="nm" @click="goStock(r.f12)">
            <b>{{ r.f14 }}</b>
            <span class="cd">{{ r.f12 }}</span>
            <span v-if="r.limit_up === 1" class="lmBadge up">涨停</span>
            <span v-else-if="r.limit_down === 1" class="lmBadge down">跌停</span>
          </button>
          <span class="col price">{{ fmtN(r.f2) }}</span>
          <span class="col" :class="cls(r.f3)">
            {{ typeof r.f3 === "number" ? (r.f3 > 0 ? "+" : "") + fmtN(r.f3) + "%" : "—" }}
          </span>
          <span class="col tov"><b>{{ fmtN(r.f8) }}%</b></span>
          <span class="col dim hide-m">{{ r.f100 || "—" }}</span>
          <span class="col dim hide-s">额 {{ fmtYiT(r.f6) }}</span>
          <span class="col dim hide-s">{{ (r.created_at || "").slice(0, 10) }} 加入</span>
          <button class="anaLink" @click="openAnalysis(r.f12)">分析</button>
          <button class="rmBtn" title="移除自选" @click="remove(r.f12)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div v-else-if="!loading" class="empty">
        还没有自选股<br />用上方搜索框，或在「换手率筛选」结果里点 ★ 添加
      </div>
    </section>

    <!-- 内置个股分析弹窗(rows 供板块共振/情绪统计取数) -->
    <AnalysisModal ref="anaRef" :rows="rows" />
  </div>
</template>

<style scoped>
/* ===== 布局:编辑排印风,与工作台/用户管理一致 ===== */
.watchWrap { max-width: var(--page-max, none); margin: 0 auto; padding: 12px 0 48px; }

/* ===== 搜索框:ChatGPT 式大输入框 + 浮层下拉 ===== */
.searchBox { position: relative; margin-top: 10px; z-index: 20; }
.searchInner {
  display: flex; align-items: center; gap: 10px;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 14px; padding: 0 16px; height: 48px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04);
  transition: border-color .15s, box-shadow .15s, border-radius .15s;
}
.searchInner:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.searchInner.open { border-radius: 14px 14px 0 0; }
.sIcon { color: var(--dim); flex-shrink: 0; }
.sInput {
  flex: 1; border: none; outline: none; background: transparent;
  color: var(--txt); font-size: 14px; font-family: inherit;
}
.sInput::placeholder { color: var(--dim); }
.sSpin {
  width: 14px; height: 14px; flex-shrink: 0; border-radius: 50%;
  border: 2px solid var(--line-strong); border-top-color: var(--accent);
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.drop {
  position: absolute; top: 100%; left: 0; right: 0;
  background: var(--panel); border: 1px solid var(--line-strong); border-top: none;
  border-radius: 0 0 14px 14px; overflow: hidden;
  box-shadow: 0 12px 32px rgba(0, 0, 0, .14);
  max-height: 380px; overflow-y: auto;
}
.dropEmpty { padding: 18px; text-align: center; color: var(--dim); font-size: 12.5px; }
.dropItem {
  display: flex; align-items: center; gap: 12px; width: 100%;
  background: none; border: none; border-top: 1px solid var(--line);
  padding: 10px 16px; cursor: pointer; font-family: inherit; font-size: 13px;
  color: var(--txt); text-align: left; transition: background .12s;
}
.dropItem:first-child { border-top: none; }
.dropItem:hover:not(:disabled) { background: var(--hover); }
.dropItem:disabled { cursor: default; opacity: .75; }
.dName { font-weight: 600; }
.dCode { color: var(--dim); font-family: var(--mono); font-size: 12px; }
.dInd { color: var(--dim); font-size: 12px; }
.dTov { margin-left: auto; color: var(--dim); font-size: 12px; font-family: var(--mono); }
.dAct {
  flex-shrink: 0; font-size: 12px; font-weight: 600; color: var(--accent);
  border: 1px solid var(--accent); border-radius: 999px; padding: 2px 10px;
}
.dAct.on { color: var(--dim); border-color: var(--line); font-weight: 400; }

/* ===== 列表 ===== */
.blk { margin-top: 26px; }
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

.row {
  display: flex; align-items: center; gap: 14px;
  padding: 11px 8px; border-bottom: 1px solid var(--line);
  transition: background .12s;
}
.row:hover { background: var(--hover); }
.nm {
  display: flex; align-items: baseline; gap: 8px; min-width: 150px;
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--txt); font-family: inherit; text-align: left;
}
.nm b { font-size: 13.5px; }
.nm:hover b { color: var(--accent); }
.cd { color: var(--dim); font-family: var(--mono); font-size: 11.5px; }
.col { font-size: 13px; font-family: var(--mono); min-width: 64px; text-align: right; }
.col.price { font-weight: 600; }
.col.tov { color: var(--accent); }
.col.dim { color: var(--dim); font-family: inherit; font-size: 12px; }
.up { color: var(--up); }
.down { color: var(--down); }
.anaLink {
  margin-left: auto; flex-shrink: 0; background: none;
  border: 1px solid var(--line-strong); border-radius: 999px;
  color: var(--accent); padding: 2px 11px; font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.anaLink:hover { border-color: var(--accent); background: var(--accent-dim); }
.rmBtn {
  flex-shrink: 0; width: 26px; height: 26px;
  background: none; border: none; border-radius: 50%; cursor: pointer;
  color: var(--dim); display: inline-flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .15s, color .15s, background .15s;
}
.row:hover .rmBtn { opacity: 1; }
.rmBtn:hover { color: var(--up); background: var(--panel-2); }
@media (hover: none) { .rmBtn { opacity: 1; } }

.empty {
  padding: 48px 0; text-align: center; color: var(--dim);
  font-size: 13px; line-height: 2;
}

@media (max-width: 860px) { .hide-m { display: none; } }
@media (max-width: 640px) {
  .hide-s { display: none; }
  .nm { min-width: 0; flex: 1; }
  .col { min-width: 52px; }
}
</style>
