<script setup>
/* ===== 设置 · 行情设置 + 黑名单管理 =====
   行情设置：每用户独立的第三方行情接口
   添加自己的行情源（服务商 + 证书编号），启用后首页「我的自选」实时行情
   改走自己的接口；未配置或调用失败时自动回落系统默认数据源（东方财富快照）。
   证书编号保存在后端数据库（quote_source 表，按用户隔离），后端代理请求，
   浏览器不直连第三方——接口地址与证书都不会暴露给其他人。
   黑名单管理：每用户独立（blacklist 表），命中后换手率筛选结果服务端直接剔除。 */
import { onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { api } from "../api/client";
import { blackState, removeBlack } from "../stores/blacklist";
import ConfirmModal from "../components/ConfirmModal.vue";

const PROVIDER_LABEL = { mairui: "麦蕊智数" };
const APPLY_URL = "https://mairui.club/packs";

const rows = ref([]);
const publicList = ref([]);   // 其他人公开的行情源（只展示名称，供未配置自己的源时使用）
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const d = await api("/api/quotesettings");
    rows.value = d.rows || [];
    publicList.value = d.public || [];
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

/* ---------- 新增 ---------- */
const form = reactive({ name: "", provider: "mairui", licence: "" });
const saving = ref(false);

async function add() {
  if (!form.name.trim()) return message.warning("请填写配置名称");
  if (!form.licence.trim()) return message.warning("请填写证书编号");
  saving.value = true;
  try {
    await api("/api/quotesettings", {
      method: "POST",
      body: { name: form.name.trim(), provider: form.provider,
              licence: form.licence.trim() },
    });
    message.success("已添加" + (rows.value.length ? "" : "并自动启用"));
    form.name = "";
    form.licence = "";
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  } finally {
    saving.value = false;
  }
}

/* ---------- 证书编号显示：默认打码，可点眼睛临时查看 ---------- */
const reveal = reactive({});
function mask(l) {
  return l && l.length > 10 ? l.slice(0, 4) + "••••••••" + l.slice(-4) : "••••••••";
}

/* ---------- 启用/停用（同时只启用一个，启用即接管首页实时行情） ---------- */
const togglings = reactive({});
async function toggle(r) {
  togglings[r.id] = true;
  try {
    await api("/api/quotesettings/" + r.id, {
      method: "PATCH", body: { enabled: !r.enabled },
    });
    if (!r.enabled) message.success("已启用「" + r.name + "」，首页自选行情改走该数据源");
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  } finally {
    togglings[r.id] = false;
  }
}

/* ---------- 公开/取消公开（公开后全站可用，但他人只能看到名称） ---------- */
async function togglePublic(r) {
  try {
    await api("/api/quotesettings/" + r.id, {
      method: "PATCH", body: { is_public: !r.is_public },
    });
    if (!r.is_public)
      message.success("已公开「" + r.name + "」：未启用自己行情源的用户也可使用（会消耗你的调用配额）");
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

/* ---------- 连通性测试（后端代理请求平安银行实时行情） ---------- */
const tests = reactive({});
async function test(r) {
  tests[r.id] = { loading: true, ok: null, text: "" };
  try {
    const d = await api("/api/quotesettings/" + r.id + "/test", { method: "POST" });
    tests[r.id] = d.ok
      ? { loading: false, ok: true,
          text: "通 · " + d.latency_ms + "ms · 平安银行 " + d.sample.p + " (" + d.sample.pc + "%)" }
      : { loading: false, ok: false, text: d.error || "测试失败" };
  } catch (err) {
    tests[r.id] = { loading: false, ok: false,
                    text: err.message === "unauthorized" ? "" : (err.message || "测试失败") };
  }
}

/* ---------- 删除（二次确认） ---------- */
const rmState = reactive({ open: false, row: null, loading: false });

async function remove() {
  const r = rmState.row;
  if (!r) return;
  rmState.loading = true;
  try {
    await api("/api/quotesettings/" + r.id, { method: "DELETE" });
    rmState.open = false;
    message.success("已删除「" + r.name + "」");
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "删除失败");
  } finally {
    rmState.loading = false;
  }
}

/* ---------- 黑名单管理(命中后筛选结果不再显示;在筛选行 ⋯ 菜单也可加入) ---------- */
const blRows = ref([]);
const blLoading = ref(false);
const blCode = ref("");
const blSaving = ref(false);

async function loadBlack() {
  blLoading.value = true;
  try {
    const d = await api("/api/blacklist");
    blRows.value = d.rows || [];
    blackState.codes = new Set(blRows.value.map((r) => r.code));
    blackState.loaded = true;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    blLoading.value = false;
  }
}

async function addBl() {
  const code = blCode.value.trim();
  if (!/^\d{6}$/.test(code)) return message.warning("请输入 6 位股票代码");
  blSaving.value = true;
  try {
    await api("/api/blacklist", { method: "POST", body: { code } });
    message.success("已加入黑名单，筛选结果将不再显示该股");
    blCode.value = "";
    loadBlack();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  } finally {
    blSaving.value = false;
  }
}

const blRm = reactive({ open: false, row: null, loading: false });
async function removeBl() {
  const r = blRm.row;
  if (!r) return;
  blRm.loading = true;
  try {
    await removeBlack(r.code);
    blRm.open = false;
    message.success(`已移出黑名单 ${r.name || r.code}，下次查询恢复显示`);
    loadBlack();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  } finally {
    blRm.loading = false;
  }
}

onMounted(() => { load(); loadBlack(); });
</script>

<template>
  <div class="setWrap">
    <!-- ===== 行情设置 ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">行情设置</span>
        <span class="secNote">共 {{ rows.length }} 个数据源 · 启用其一即接管首页自选实时行情</span>
        <button class="ghostBtn" :disabled="loading" @click="load">
          {{ loading ? "刷新中…" : "刷新" }}
        </button>
      </div>

      <p class="hint">
        在这里添加自己的行情接口，决定首页实时展示的行情信息来源；每个人只影响自己的账号。
        未配置或接口失败时自动回落系统默认数据源（东方财富快照）。
        同一时刻只启用一个数据源，启用新的会自动停用旧的。
        <template v-if="form.provider === 'mairui'">
          证书编号在 <a :href="APPLY_URL" target="_blank" rel="noopener">麦蕊智数 · 我的接口</a> 页面查看。
        </template>
      </p>

      <!-- 添加表单 -->
      <div class="addForm">
        <input v-model="form.name" class="fInput fName" maxlength="32"
               placeholder="配置名称，如：我的麦蕊" @keyup.enter="add" />
        <select v-model="form.provider" class="fInput fProv">
          <option value="mairui">麦蕊智数</option>
        </select>
        <input v-model="form.licence" class="fInput fLic" maxlength="64"
               placeholder="证书编号（Licence）" @keyup.enter="add" />
        <button class="addBtn" :disabled="saving" @click="add">
          {{ saving ? "添加中…" : "+ 添加" }}
        </button>
      </div>

      <!-- 配置列表 -->
      <div v-if="rows.length" class="list">
        <div v-for="r in rows" :key="r.id" class="row" :class="{ on: r.enabled }">
          <span class="nm">
            <b>{{ r.name }}</b>
            <i v-if="r.enabled" class="liveDot"></i>
          </span>
          <span class="prov">{{ PROVIDER_LABEL[r.provider] || r.provider }}</span>
          <span class="lic" :class="{ rev: reveal[r.id] }">{{ reveal[r.id] ? r.licence : mask(r.licence) }}</span>
          <button class="eye" :title="reveal[r.id] ? '隐藏' : '显示'"
                  @click="reveal[r.id] = !reveal[r.id]">
            {{ reveal[r.id] ? "隐藏" : "显示" }}
          </button>
          <button class="tog" :class="{ act: r.enabled }" :disabled="togglings[r.id]"
                  @click="toggle(r)">
            {{ togglings[r.id] ? "切换中…" : r.enabled ? "启用中" : "已停用" }}
          </button>
          <button class="tog pub" :class="{ act: r.is_public }" title="公开后全站用户都可使用该数据源（他人仅见名称，证书不外泄）；会消耗你的调用配额"
                  @click="togglePublic(r)">
            {{ r.is_public ? "已公开" : "未公开" }}
          </button>
          <button class="testBtn" :disabled="tests[r.id] && tests[r.id].loading"
                  @click="test(r)">
            {{ tests[r.id] && tests[r.id].loading ? "测试中…" : "测试" }}
          </button>
          <button class="rmBtn" title="删除" @click="rmState.row = r; rmState.open = true">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
          <div v-if="tests[r.id] && tests[r.id].text" class="testLine"
               :class="tests[r.id].ok ? 'ok' : 'bad'">{{ tests[r.id].text }}</div>
        </div>
      </div>

      <div v-else-if="!loading" class="empty">
        还没有行情源配置<br />
        上方填入服务商与证书编号添加；不配置也不影响使用，行情走系统默认数据源
      </div>

      <!-- 其他人公开的行情源：只能看到名称，直接可用 -->
      <div v-if="publicList.length" class="pubNote">
        公共行情源：{{ publicList.join("、") }}
        —— 由其他用户公开共享，未启用自己的行情源时，首页自选实时行情自动使用它们
      </div>
    </section>

    <!-- ===== 黑名单管理 ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">黑名单管理</span>
        <span class="secNote">共 {{ blRows.length }} 只 · 命中后筛选结果不再显示</span>
        <button class="ghostBtn" :disabled="blLoading" @click="loadBlack">
          {{ blLoading ? "刷新中…" : "刷新" }}
        </button>
      </div>

      <p class="hint">
        黑名单只影响你自己的账号：加入后该股不再出现在换手率筛选结果中（服务端直接剔除），
        移除后下次查询恢复显示。也可以在筛选结果行的「⋯」菜单里直接加入黑名单；
        行菜单里的「本次查询不再显示」只是临时隐藏，重新查询即恢复。
      </p>

      <!-- 按代码添加 -->
      <div class="addForm">
        <input v-model="blCode" class="fInput fName" maxlength="6" inputmode="numeric"
               placeholder="6 位股票代码，如：600519" @keyup.enter="addBl" />
        <button class="addBtn" :disabled="blSaving" @click="addBl">
          {{ blSaving ? "加入中…" : "+ 加入黑名单" }}
        </button>
      </div>

      <div v-if="blRows.length" class="list">
        <div v-for="r in blRows" :key="r.code" class="row">
          <span class="nm"><b>{{ r.name || "—" }}</b></span>
          <span class="blCode">{{ r.code }}</span>
          <span class="blTime">加入于 {{ (r.created_at || "").slice(0, 10) }}</span>
          <button class="rmBtn" title="移出黑名单" @click="blRm.row = r; blRm.open = true">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      <div v-else-if="!blLoading" class="empty">
        黑名单为空<br />
        在筛选结果行的「⋯」菜单选择「加入黑名单」，或上方输入代码添加
      </div>
    </section>

    <!-- 删除二次确认 -->
    <ConfirmModal
      :open="rmState.open"
      :title="'删除行情源 ' + (rmState.row ? '「' + rmState.row.name + '」' : '')"
      :desc="rmState.row && rmState.row.enabled
        ? '该数据源正在启用中，删除后首页自选行情回落到系统默认数据源。'
        : '删除后不可恢复。'"
      ok-text="删除"
      :loading="rmState.loading"
      @confirm="remove"
      @close="rmState.open = false"
    />

    <!-- 移出黑名单二次确认 -->
    <ConfirmModal
      :open="blRm.open"
      :title="'移出黑名单 ' + (blRm.row ? (blRm.row.name || '') + ' ' + blRm.row.code : '')"
      desc="移出后该股将重新出现在筛选结果中（下次查询生效）。"
      ok-text="移出"
      :loading="blRm.loading"
      @confirm="removeBl"
      @close="blRm.open = false"
    />
  </div>
</template>

<style scoped>
.setWrap { padding: 12px 0 48px; }

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

.hint { color: var(--dim); font-size: 12.5px; line-height: 1.9; margin: 14px 2px 0; }
.hint a { color: var(--accent); }

/* ===== 添加表单 ===== */
.addForm {
  display: flex; gap: 10px; margin-top: 14px;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 12px; padding: 12px;
}
.fInput {
  border: 1px solid var(--line); border-radius: 8px; background: transparent;
  color: var(--txt); font-size: 13px; font-family: inherit;
  padding: 8px 12px; outline: none; transition: border-color .15s;
}
.fInput:focus { border-color: var(--accent); }
.fName { flex: 1.2; min-width: 120px; }
.fProv { flex: .8; min-width: 100px; cursor: pointer; }
.fProv option { color: #222; }
.fLic { flex: 2; min-width: 160px; font-family: var(--mono); }
.addBtn {
  flex-shrink: 0; border: none; border-radius: 8px; padding: 8px 18px;
  font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer;
  color: var(--btn-txt); background: var(--btn-bg); transition: opacity .15s;
}
.addBtn:hover:not(:disabled) { opacity: .88; }
.addBtn:disabled { opacity: .55; cursor: not-allowed; }

/* ===== 配置列表 ===== */
.row {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  padding: 13px 8px; border-bottom: 1px solid var(--line);
  transition: background .12s;
}
.row:hover { background: var(--hover); }
.row.on .nm b { color: var(--accent); }
.nm { display: flex; align-items: center; gap: 8px; min-width: 140px; }
.nm b { font-size: 13.5px; }
.liveDot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.prov { color: var(--dim); font-size: 12px; min-width: 70px; }
.lic { color: var(--dim); font-family: var(--mono); font-size: 12px; }
.lic.rev { color: var(--txt); }
.eye {
  background: none; border: none; padding: 2px 4px; cursor: pointer;
  color: var(--dim); font-size: 11px; font-family: inherit;
  text-decoration: underline dotted; transition: color .15s;
}
.eye:hover { color: var(--txt); }
.tog {
  margin-left: auto; flex-shrink: 0; cursor: pointer; font-family: inherit;
  background: none; border: 1px solid var(--line); border-radius: 999px;
  padding: 3px 12px; font-size: 12px; color: var(--dim);
  transition: all .15s;
}
.tog:hover:not(:disabled) { border-color: var(--line-strong); color: var(--txt); }
.tog.act { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); font-weight: 600; }
.tog.pub { margin-left: 0; }
.tog:disabled { opacity: .6; cursor: wait; }
.pubNote {
  margin-top: 16px; padding: 10px 14px;
  border: 1px dashed var(--line-strong); border-radius: 10px;
  color: var(--dim); font-size: 12px; line-height: 1.8;
}
.testBtn {
  flex-shrink: 0; cursor: pointer; font-family: inherit;
  background: none; border: 1px solid var(--line-strong); border-radius: 999px;
  padding: 3px 12px; font-size: 12px; color: var(--txt);
  transition: all .15s;
}
.testBtn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.testBtn:disabled { opacity: .6; cursor: wait; }
.rmBtn {
  flex-shrink: 0; width: 26px; height: 26px;
  background: none; border: none; border-radius: 50%; cursor: pointer;
  color: var(--dim); display: inline-flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .15s, color .15s, background .15s;
}
.row:hover .rmBtn { opacity: 1; }
.rmBtn:hover { color: var(--up); background: var(--panel-2); }
@media (hover: none) { .rmBtn { opacity: 1; } }

/* 测试结果：整行下方的细提示行 */
.testLine {
  position: absolute; left: 8px; bottom: -1px; transform: translateY(100%);
  font-size: 11.5px; font-family: var(--mono); padding: 3px 0;
}
.testLine.ok { color: var(--up); }
.testLine.bad { color: var(--down); }

.empty {
  padding: 48px 0; text-align: center; color: var(--dim);
  font-size: 13px; line-height: 2;
}

/* ===== 黑名单行 ===== */
.blCode { color: var(--dim); font-family: var(--mono); font-size: 12px; min-width: 70px; }
.blTime { color: var(--dim); font-size: 12px; }
.blk + .blk { margin-top: 36px; }

@media (max-width: 720px) {
  .addForm { flex-wrap: wrap; }
  .fName, .fProv, .fLic { flex: 1 1 45%; }
  .prov, .lic, .eye { display: none; }
}
</style>
