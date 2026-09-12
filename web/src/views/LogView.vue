<script setup>
/* ===== 操作日志页（仅隐藏 root 可见）=====
   菜单/路由守卫/后端 404 三重隐藏。数据源 /api/logs：时间倒序，
   支持按用户、动作、关键词过滤，服务端分页。 */
import { onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
// 本页专属重组件按需引入（同 AdminView,不进全局注册）
import {
  Select as ASelect, SelectOption as ASelectOption, Table as ATable,
  Modal as AModal,
} from "ant-design-vue";
import { api } from "../api/client";

const ACTION_LABELS = {
  login: "登录", logout: "登出", login_fail: "登录失败",
  page_view: "打开页面",
  screener_run: "条件筛选", stock_view: "查看个股", analysis_view: "战法分析",
  f10_view: "查看F10", desk_view: "打开工作台", radar_view: "打开涨停雷达",
  history_view: "打开历史榜单", flow_view: "打开板块资金",
  watchlist_add: "加自选", watchlist_del: "删自选",
  admin_create_user: "新建用户", admin_update_user: "修改用户",
  admin_delete_user: "删除用户",
};
const actionLabel = (a) => ACTION_LABELS[a] || a;

const columns = [
  { title: "时间", dataIndex: "ts", key: "ts", width: 170 },
  { title: "用户", dataIndex: "username", key: "username", width: 110 },
  { title: "动作", dataIndex: "action", key: "action", width: 110 },
  { title: "详情", dataIndex: "detail", key: "detail" },
  { title: "IP / 归属地", dataIndex: "ip", key: "ip", width: 190 },
];

const rows = ref([]);
const actions = ref([]);
const total = ref(0);
const loading = ref(false);
const filters = reactive({ username: "", action: "", kw: "" });
const page = ref(1);
const PAGE_SIZE = 20;

async function load() {
  loading.value = true;
  try {
    const qs = new URLSearchParams();
    if (filters.username.trim()) qs.set("username", filters.username.trim());
    if (filters.action) qs.set("action", filters.action);
    if (filters.kw.trim()) qs.set("kw", filters.kw.trim());
    qs.set("page", page.value);
    qs.set("size", PAGE_SIZE);
    const d = await api("/api/logs?" + qs);
    rows.value = d.rows;
    total.value = d.total;
    actions.value = d.actions;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function onSearch() { page.value = 1; load(); }
function onPage(p) { page.value = p; load(); }

// 详情弹窗：展示完整记录（替代原展开行）
const detailRec = ref(null);
function showDetail(rec) { detailRec.value = rec; }

onMounted(load);
</script>

<template>
  <div class="logWrap">
    <section class="blk">
      <div class="secHead">
        <span class="secName">操作日志</span>
        <span class="secNote">共 {{ total }} 条 · 登录 / 页面打开 / 筛选 / 自选 / 个股 / 用户管理操作</span>
      </div>

      <!-- 过滤条件 -->
      <div class="filters">
        <a-input
          v-model:value="filters.username"
          placeholder="用户名"
          class="fItem fUser"
          allow-clear
          @press-enter="onSearch"
        />
        <a-select
          v-model:value="filters.action"
          placeholder="动作"
          class="fItem fAction"
          allow-clear
          @change="onSearch"
        >
          <a-select-option v-for="a in actions" :key="a" :value="a">
            {{ actionLabel(a) }}
          </a-select-option>
        </a-select>
        <a-input
          v-model:value="filters.kw"
          placeholder="关键词（详情/用户名）"
          class="fItem fKw"
          allow-clear
          @press-enter="onSearch"
        />
        <button class="pill" @click="onSearch">查询</button>
      </div>

      <a-table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="{
          current: page, pageSize: PAGE_SIZE, total,
          showSizeChanger: false, hideOnSinglePage: true,
        }"
        row-key="id"
        size="middle"
        class="logTbl"
        @change="(p) => onPage(p.current)"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'ts'">
            <span class="dimTxt">{{ (record.ts || "").replace("T", " ") }}</span>
          </template>
          <template v-else-if="column.key === 'username'">
            <span class="uname">{{ record.username || "—" }}</span>
          </template>
          <template v-else-if="column.key === 'action'">
            <span class="actTag">{{ actionLabel(record.action) }}</span>
          </template>
          <template v-else-if="column.key === 'detail'">
            <span class="detailTxt">{{ record.detail || "—" }}</span>
          </template>
          <template v-else-if="column.key === 'ip'">
            <div class="ipCell">
              <span class="dimTxt">{{ record.ip || "—" }}</span>
              <span class="regionTxt">{{ record.region || "—" }}</span>
              <button class="detailBtn" @click="showDetail(record)">详情</button>
            </div>
          </template>
        </template>
      </a-table>

      <!-- 详情弹窗：完整审计细节 -->
      <a-modal
        :open="!!detailRec"
        title="记录详情"
        :footer="null"
        width="640px"
        class="logModal"
        @cancel="detailRec = null"
      >
        <div v-if="detailRec" class="expGrid">
          <span class="expK">记录 ID</span><span class="expV">#{{ detailRec.id }}</span>
          <span class="expK">时间</span>
          <span class="expV">{{ (detailRec.ts || "").replace("T", " ") }}</span>
          <span class="expK">用户</span>
          <span class="expV">{{ detailRec.username || "—" }}
            <span class="dimTxt">(uid {{ detailRec.user_id ?? "—" }})</span></span>
          <span class="expK">动作</span>
          <span class="expV">{{ actionLabel(detailRec.action) }}
            <span class="dimTxt">{{ detailRec.action }}</span></span>
          <span class="expK">详情</span>
          <span class="expV detailFull">{{ detailRec.detail || "—" }}</span>
          <span class="expK">IP</span>
          <span class="expV">{{ detailRec.ip || "—" }}</span>
          <span class="expK">归属地</span>
          <span class="expV">{{ detailRec.region || "—" }}</span>
          <span class="expK">终端</span>
          <span class="expV detailFull">{{ detailRec.ua || "—（旧记录未采集）" }}</span>
        </div>
      </a-modal>
    </section>
  </div>
</template>

<style scoped>
/* ===== 与 AdminView 一致的排印风 ===== */
.logWrap { padding: 12px 0 48px; }
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

/* ===== 过滤条 ===== */
.filters { display: flex; gap: 10px; margin: 16px 0 4px; flex-wrap: wrap; }
.fUser { width: 140px; }
.fAction { width: 130px; }
.fKw { width: 220px; }
.pill {
  background: var(--btn-bg); color: var(--btn-txt);
  border: none; border-radius: 999px; padding: 7px 22px;
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: opacity .15s, transform .1s;
}
.pill:hover { opacity: .88; }
.pill:active { transform: scale(.98); }

/* ===== 列表细节 ===== */
.uname { font-weight: 600; font-size: 13px; }
.actTag {
  font-size: 12px; border: 1px solid var(--line); border-radius: 999px;
  padding: 1px 9px; color: var(--txt); white-space: nowrap;
}
.dimTxt { color: var(--dim); font-size: 12.5px; font-family: var(--mono); }
.detailTxt {
  font-size: 12.5px; color: var(--txt); font-family: var(--mono);
  word-break: break-all;
}
.ipCell { display: flex; flex-direction: column; gap: 1px; }
.regionTxt { font-size: 11px; color: var(--dim); }
.detailBtn {
  align-self: flex-start; background: none; border: none; padding: 0;
  margin-top: 2px; font-size: 11px; font-family: inherit;
  color: var(--accent); cursor: pointer; opacity: .85;
}
.detailBtn:hover { opacity: 1; text-decoration: underline; }

/* ===== 详情弹窗：审计细节网格 ===== */
.expGrid {
  display: grid; grid-template-columns: 72px 1fr; gap: 8px 14px;
  padding: 6px 2px; font-size: 12.5px;
}
.expK { color: var(--dim); white-space: nowrap; }
.expV { color: var(--txt); font-family: var(--mono); word-break: break-all; }
.detailFull { line-height: 1.7; }
:deep(.ant-modal-content), :deep(.ant-modal-header) { background: var(--panel); }
:deep(.ant-modal-title) { background: transparent; color: var(--txt); }
:deep(.ant-modal-close) { color: var(--dim); }

/* ===== antd 主题适配(明暗双主题走令牌) ===== */
:deep(.ant-input),
:deep(.ant-select .ant-select-selector) {
  background: var(--panel-2) !important;
  border-color: var(--line) !important;
  color: var(--txt) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
/* allow-clear 会让 a-input 多包一层 affix-wrapper(可见的框),内层输入框透明 */
:deep(.ant-input-affix-wrapper) {
  background: var(--panel-2) !important;
  border-color: var(--line) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
:deep(.ant-input-affix-wrapper .ant-input) { background: transparent !important; }
/* 聚焦态:accent 细光环,不用 antd 默认蓝色光晕 */
:deep(.ant-input-affix-wrapper-focused),
:deep(.ant-input:focus),
:deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-dim) !important;
}
:deep(.ant-input::placeholder) { color: var(--dim); }
:deep(.ant-select-arrow), :deep(.ant-input-clear-icon) { color: var(--dim); }
:deep(.ant-select-selection-item) { color: var(--txt); }
:deep(.ant-select-selection-placeholder) { color: var(--dim); }

:deep(.ant-table) { background: transparent; color: var(--txt); }
:deep(.ant-table-thead > tr > th) {
  background: transparent; color: var(--dim);
  font-size: 11.5px; font-weight: 500; letter-spacing: .08em;
  border-bottom: 1px solid var(--line-strong);
  padding: 10px 12px;
}
:deep(.ant-table-thead > tr > th::before) { display: none; }
:deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--line); padding: 10px 12px; }
:deep(.ant-table-tbody > tr:hover > td) { background: var(--hover) !important; }
:deep(.ant-table-placeholder) { background: transparent; }
:deep(.ant-empty-description) { color: var(--dim); }
:deep(.ant-pagination .ant-pagination-item),
:deep(.ant-pagination .ant-pagination-prev),
:deep(.ant-pagination .ant-pagination-next) { color: var(--txt); }
:deep(.ant-pagination .ant-pagination-item a) { color: var(--txt); }
:deep(.ant-pagination .ant-pagination-item-active) {
  background: transparent; border-color: var(--accent);
}
:deep(.ant-pagination .ant-pagination-item-active a) { color: var(--accent); }

@media (max-width: 720px) {
  .fUser, .fAction, .fKw { width: 100%; }
}
</style>
