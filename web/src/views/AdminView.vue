<script setup>
/* ===== 用户管理页（管理员及以上可访问）=====
   权限模型（与 backend/app/routes/admin_routes.py 一致）：
   - 种子账号 admin 即 root：全部权限，账号本身不可被管理接口触碰
   - 其他管理员：只能创建/管理普通用户，不能创建管理员、不能动 root 和其他管理员
   - super 角色不存在，root 由后端返回的 user.root 标记
   校验规则：用户名 ^[A-Za-z0-9_@.\-]{2,32}$ · 密码 6-128 位 · 角色 user|admin */
import { onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
// 管理页专属重组件按需引入（不进全局注册,首页主包不带 Table/Select 等）
import {
  Popconfirm as APopconfirm, Radio as ARadio, RadioGroup as ARadioGroup,
  Select as ASelect, SelectOption as ASelectOption, Table as ATable,
} from "ant-design-vue";
import { api } from "../api/client";
import { authState } from "../stores/auth";

const me = authState.user; // 路由守卫已保证登录且为 admin

const isRoot = () => !!me.root;
// 行内操作(启停/重置/删除)是否可用：不动 root、不动自己；非 root 只能管普通用户
const canManage = (u) =>
  !u.root && u.id !== me.id && (isRoot() || u.role === "user");
// 角色下拉是否可改：仅 root 可改他人角色
const canEditRole = (u) => isRoot() && !u.root && u.id !== me.id;

/* ---------- 用户列表 ---------- */
const users = ref([]);
const listLoading = ref(false);

const columns = [
  { title: "用户名", dataIndex: "username", key: "username" },
  { title: "角色", dataIndex: "role", key: "role", width: 140 },
  { title: "状态", dataIndex: "enabled", key: "enabled", width: 110 },
  { title: "创建时间", dataIndex: "created_at", key: "created_at", width: 180 },
  { title: "", key: "ops", width: 210, align: "right" },
];

// 统一错误提示：401/403 由 api client 跳登录，页内不再提示
function showErr(err) {
  if (!err || err.message === "unauthorized") return;
  let msg = err.message || "操作失败";
  if (msg === "[object Object]" || msg.startsWith("[{")) msg = "请求参数校验失败";
  message.error(msg);
}

async function loadUsers() {
  listLoading.value = true;
  try {
    const d = await api("/api/admin/users");
    users.value = d.users;
  } catch (err) {
    showErr(err);
  } finally {
    listLoading.value = false;
  }
}

/* ---------- 新增用户（弹窗） ---------- */
const createFormRef = ref();
const createModal = reactive({ open: false, loading: false });
const createForm = reactive({ username: "", password: "", role: "user" });

const USERNAME_RE = /^[A-Za-z0-9_@.\-]{2,32}$/; // 与后端完全一致
const createRules = {
  username: [
    {
      validator: (_r, v) => {
        const name = (v || "").trim();
        if (!name) return Promise.reject("请输入用户名");
        if (!USERNAME_RE.test(name)) return Promise.reject("仅限字母数字及 _ @ . -，长度 2-32");
        return Promise.resolve();
      },
      trigger: "blur",
    },
  ],
  password: [
    { required: true, message: "请输入初始密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度 6-128 位", trigger: "blur" },
  ],
  role: [{ required: true, message: "请选择角色" }],
};

function openCreate() {
  createForm.username = "";
  createForm.password = "";
  createForm.role = "user";
  createModal.open = true;
}

async function onCreateOk() {
  try {
    await createFormRef.value.validate();
  } catch {
    return; // 校验不过,留在弹窗内标红
  }
  createModal.loading = true;
  try {
    const d = await api("/api/admin/users", {
      method: "POST",
      body: {
        username: createForm.username.trim(),
        password: createForm.password,
        role: createForm.role,
      },
    });
    message.success("已创建用户 " + d.username);
    createModal.open = false;
    loadUsers();
  } catch (err) {
    showErr(err);
  } finally {
    createModal.loading = false;
  }
}

/* ---------- 行内操作：改角色 / 启停 ---------- */
async function onRoleChange(u, role) {
  try {
    await api("/api/admin/users/" + u.id, { method: "PATCH", body: { role } });
    u.role = role;
    message.success("角色已更新");
  } catch (err) {
    showErr(err);
    loadUsers();
  }
}

async function onToggle(u) {
  try {
    await api("/api/admin/users/" + u.id, { method: "PATCH", body: { enabled: !u.enabled } });
    message.success(u.enabled ? "已停用 " + u.username : "已启用 " + u.username);
    loadUsers();
  } catch (err) {
    showErr(err);
  }
}

/* ---------- 行内操作：重置密码 ---------- */
const resetState = reactive({ open: false, user: null, password: "", loading: false });

function openReset(u) {
  resetState.user = u;
  resetState.password = "";
  resetState.open = true;
}

async function onResetOk() {
  const p = resetState.password;
  if (p.length < 6 || p.length > 128) {
    message.error("密码长度 6-128 位");
    return;
  }
  resetState.loading = true;
  try {
    await api("/api/admin/users/" + resetState.user.id, { method: "PATCH", body: { password: p } });
    message.success("已重置 " + resetState.user.username + " 的密码");
    resetState.open = false;
  } catch (err) {
    showErr(err);
  } finally {
    resetState.loading = false;
  }
}

/* ---------- 行内操作：删除 ---------- */
async function onDelete(u) {
  try {
    await api("/api/admin/users/" + u.id, { method: "DELETE" });
    message.success("已删除 " + u.username);
    loadUsers();
  } catch (err) {
    showErr(err);
  }
}

onMounted(loadUsers);
</script>

<template>
  <div class="adminWrap">
    <!-- ===== 用户列表 ===== -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">用户列表</span>
        <span class="secNote">共 {{ users.length }} 个账号 · 注册不开放，账号由管理员创建</span>
        <button class="pill addBtn" @click="openCreate">
          <span class="plus">+</span> 新增用户
        </button>
      </div>
      <a-table
        :columns="columns"
        :data-source="users"
        :loading="listLoading"
        :pagination="false"
        row-key="id"
        size="middle"
        class="userTbl"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'username'">
            <span class="uname">{{ record.username }}</span>
            <span v-if="record.id === me.id" class="meTag">我</span>
          </template>
          <template v-else-if="column.key === 'role'">
            <span v-if="record.root" class="rootRole">超级管理员</span>
            <a-select
              v-else
              :value="record.role"
              size="small"
              class="roleSel"
              :disabled="!canEditRole(record)"
              @change="(val) => onRoleChange(record, val)"
            >
              <a-select-option value="user">普通用户</a-select-option>
              <a-select-option value="admin">管理员</a-select-option>
            </a-select>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <span class="status" :class="{ off: !record.enabled }">
              <i class="dot"></i>{{ record.enabled ? "已授权" : "已停用" }}
            </span>
          </template>
          <template v-else-if="column.key === 'created_at'">
            <span class="dimTxt">{{ (record.created_at || "").replace("T", " ") }}</span>
          </template>
          <template v-else-if="column.key === 'ops'">
            <div class="rowOps">
              <button class="opBtn" :disabled="!canManage(record)" @click="onToggle(record)">
                {{ record.enabled ? "停用" : "启用" }}
              </button>
              <button class="opBtn" :disabled="!canManage(record)" @click="openReset(record)">
                重置密码
              </button>
              <a-popconfirm
                :title="'确定删除用户 ' + record.username + ' ？'"
                ok-text="删除"
                cancel-text="取消"
                @confirm="onDelete(record)"
              >
                <button class="opBtn danger" :disabled="!canManage(record)">删除</button>
              </a-popconfirm>
            </div>
          </template>
        </template>
      </a-table>
    </section>

    <!-- 新增用户弹窗 -->
    <a-modal
      v-model:open="createModal.open"
      title="新增用户"
      ok-text="创建"
      cancel-text="取消"
      :width="420"
      :confirm-loading="createModal.loading"
      @ok="onCreateOk"
    >
      <a-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        layout="vertical"
        class="modalForm"
      >
        <a-form-item label="用户名" name="username">
          <a-input
            v-model:value="createForm.username"
            placeholder="2-32 位字母数字或 _ @ . -"
            autocomplete="off"
          />
        </a-form-item>
        <a-form-item label="初始密码" name="password">
          <a-input-password
            v-model:value="createForm.password"
            placeholder="至少 6 位，用户首次登录后可在「修改密码」中更改"
            autocomplete="new-password"
          />
        </a-form-item>
        <a-form-item label="角色" name="role">
          <a-radio-group v-model:value="createForm.role" class="roleRadio">
            <a-radio value="user">
              <div class="rTitle">普通用户</div>
              <div class="rDesc">可使用筛选等全部行情功能</div>
            </a-radio>
            <a-radio v-if="isRoot()" value="admin">
              <div class="rTitle">管理员</div>
              <div class="rDesc">可创建和管理普通用户</div>
            </a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 重置密码弹窗 -->
    <a-modal
      v-model:open="resetState.open"
      :title="'重置密码 · ' + (resetState.user ? resetState.user.username : '')"
      ok-text="确定"
      cancel-text="取消"
      :confirm-loading="resetState.loading"
      @ok="onResetOk"
    >
      <a-input-password
        v-model:value="resetState.password"
        placeholder="新密码（至少 6 位）"
        autocomplete="new-password"
        @press-enter="onResetOk"
      />
    </a-modal>
  </div>
</template>

<style scoped>
/* ===== 布局:无卡片盒,编辑排印风(与新版工作台一致) ===== */
.adminWrap { padding: 12px 0 48px; }
.blk { margin-top: 30px; }
.blk:first-child { margin-top: 10px; }
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

/* ===== 新增用户按钮(列表头右侧) ===== */
.addBtn { margin-left: auto; display: inline-flex; align-items: center; gap: 5px; }
.addBtn .plus { font-size: 15px; line-height: 1; margin-top: -1px; }

/* ===== 创建按钮:沿用全局 pill ===== */
.pill {
  background: var(--btn-bg); color: var(--btn-txt);
  border: none; border-radius: 999px; padding: 7px 22px;
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: opacity .15s, transform .1s;
}
.pill:hover { opacity: .88; }
.pill:active { transform: scale(.98); }
.pill:disabled { opacity: .55; cursor: not-allowed; }

/* ===== 弹窗表单 ===== */
.modalForm { margin-top: 14px; }
.modalForm :deep(.ant-form-item-label > label) { color: var(--dim); font-size: 12.5px; }
.modalForm :deep(.ant-form-item) { margin-bottom: 16px; }
.roleRadio { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.roleRadio :deep(.ant-radio-wrapper) {
  display: flex; align-items: flex-start; gap: 10px;
  border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 12px; margin-inline-end: 0;
  transition: border-color .15s, background .15s;
}
.roleRadio :deep(.ant-radio-wrapper:hover) { border-color: var(--line-strong); }
.roleRadio :deep(.ant-radio-wrapper-checked) {
  border-color: var(--accent); background: var(--accent-dim);
}
.roleRadio :deep(.ant-radio) { margin-top: 3px; }
.roleRadio :deep(.ant-radio-inner) { background: transparent; border-color: var(--line-strong); }
.roleRadio :deep(.ant-radio-checked .ant-radio-inner) { border-color: var(--accent); }
.roleRadio :deep(.ant-radio-checked .ant-radio-inner::after) { background: var(--accent); }
.roleRadio :deep(span:last-child) { flex: 1; }
.rTitle { font-size: 13.5px; font-weight: 600; color: var(--txt); line-height: 1.4; }
.rDesc { font-size: 12px; color: var(--dim); margin-top: 1px; }

/* ===== 列表细节 ===== */
.uname { font-weight: 600; font-size: 13.5px; }
.meTag {
  margin-left: 8px; font-size: 11px; color: var(--dim);
  border: 1px solid var(--line); border-radius: 999px; padding: 0 7px;
}
.rootRole { font-size: 13px; color: var(--txt); font-weight: 600; letter-spacing: .02em; }
.rootRole::before { content: "◆"; font-size: 9px; color: var(--brand-red); margin-right: 6px; vertical-align: 1.5px; }
.roleSel { width: 104px; }
.status { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--txt); }
.status .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--down); }
.status.off { color: var(--dim); }
.status.off .dot { background: var(--dim); opacity: .5; }
.dimTxt { color: var(--dim); font-size: 12.5px; font-family: var(--mono); }

/* 行内操作:文字按钮,hover 才显色 */
.rowOps { display: flex; gap: 2px; justify-content: flex-end; }
.opBtn {
  background: none; border: none; border-radius: 6px; cursor: pointer;
  color: var(--dim); font-size: 12.5px; font-family: inherit; padding: 4px 10px;
  transition: color .15s, background .15s;
}
.opBtn:hover:not(:disabled) { color: var(--txt); background: var(--hover); }
.opBtn.danger:hover:not(:disabled) { color: var(--up); }
.opBtn:disabled { opacity: .32; cursor: not-allowed; }

/* ===== antd 主题适配(明暗双主题走令牌) ===== */
:deep(.ant-input),
:deep(.ant-input-password),
:deep(.ant-select .ant-select-selector) {
  background: var(--panel-2) !important;
  border-color: var(--line) !important;
  color: var(--txt) !important;
  border-radius: 8px !important;
}
:deep(.ant-input::placeholder) { color: var(--dim); }
:deep(.ant-input-password .ant-input) { background: transparent !important; }
:deep(.ant-input-suffix), :deep(.ant-select-arrow) { color: var(--dim); }
:deep(.ant-select-selection-item) { color: var(--txt); }
:deep(.ant-form-item-explain-error) { font-size: 12px; }

:deep(.ant-table) { background: transparent; color: var(--txt); }
:deep(.ant-table-thead > tr > th) {
  background: transparent; color: var(--dim);
  font-size: 11.5px; font-weight: 500; letter-spacing: .08em;
  border-bottom: 1px solid var(--line-strong);
  padding: 10px 12px;
}
:deep(.ant-table-thead > tr > th::before) { display: none; }
:deep(.ant-table-tbody > tr > td) { border-bottom: 1px solid var(--line); padding: 11px 12px; }
:deep(.ant-table-tbody > tr:hover > td) { background: var(--hover) !important; }
:deep(.ant-table-placeholder) { background: transparent; }
:deep(.ant-empty-description) { color: var(--dim); }

:deep(.ant-modal-content), :deep(.ant-modal-header) { background: var(--panel); }
:deep(.ant-modal-title) { background: transparent; color: var(--txt); }
:deep(.ant-modal-close) { color: var(--dim); }

@media (max-width: 720px) {
  .secHead { flex-wrap: wrap; }
  .addBtn { margin-left: 0; }
}
</style>
