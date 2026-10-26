<script setup>
import { ref } from "vue";
import { Popover, message } from "ant-design-vue";
import { FolderAddOutlined } from "@ant-design/icons-vue";
import { api } from "../api/client";
import { fetchGroups, fetchStocks, addGroup } from "../desk/desk-data";

const props = defineProps({ code: { type: String, required: true } });
const open = ref(false), loading = ref(false), saving = ref(false);
const groups = ref([]), inDesk = ref(false), error = ref("");
const newName = ref("");
let version = 0;

async function load(visible) {
  const current = ++version;
  if (!visible) return;
  loading.value = true;
  error.value = "";
  newName.value = "";
  try {
    const [g, s] = await Promise.all([fetchGroups(), fetchStocks()]);
    if (current !== version) return;
    groups.value = g.groups || [];
    inDesk.value = (s.rows || []).some(r => r.f12 === props.code);
  } catch (e) {
    if (current === version && e.message !== "unauthorized") error.value = e.message || "目录加载失败";
  } finally {
    if (current === version) loading.value = false;
  }
}

async function add(group = null, create = false) {
  if (saving.value || (create && !newName.value.trim())) return;
  saving.value = true;
  let target = group;
  try {
    if (create) {
      target = { ...await addGroup(newName.value.trim()), codes: [] };
      groups.value.push(target);
      newName.value = "";
    }
    await api("/api/desk/stocks", { method: "POST", body: {
      code: props.code, ...(target ? { group_id: target.id } : {}),
    } });
    inDesk.value = true;
    if (target?.codes) target.codes.push(props.code);
    window.dispatchEvent(new CustomEvent("desk-stocks-changed"));
    message.success(target ? `已加入工作台「${target.name}」` : "已加入工作台");
    open.value = false;
  } catch (e) {
    if (e.message !== "unauthorized") message.error(e.message || "加入失败，请重试");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Popover v-model:open="open" trigger="click" placement="bottomRight" @open-change="load">
    <template #content>
      <div class="deskPicker" :aria-busy="loading || saving">
        <div class="pickerTitle">加入我的工作台</div>
        <p class="pickerNote">选择目录保存，同一股票可加入多个分组</p>
        <div v-if="loading" class="pickerState">正在加载目录…</div>
        <div v-else-if="error" class="pickerState">{{ error }} <button @click="load(true)">重试</button></div>
        <template v-else>
          <div class="pickerTargets">
            <button :disabled="saving || inDesk" @click="add()"><span>全部股票</span><small>{{ inDesk ? '已加入' : '不指定分组' }}</small></button>
            <button v-for="g in groups" :key="g.id" :disabled="saving || g.codes.includes(code)" @click="add(g)">
              <span>{{ g.name }}</span><small>{{ g.codes.includes(code) ? '已加入' : `${g.codes.length} 只` }}</small>
            </button>
          </div>
          <div v-if="!groups.length" class="pickerState">暂无目录，可在下方新建</div>
          <form class="pickerCreate" @submit.prevent="add(null, true)">
            <input v-model="newName" aria-label="新目录名称" placeholder="新目录名称" maxlength="16" :disabled="saving">
            <button :disabled="saving || !newName.trim()" type="submit">{{ saving ? '保存中…' : '新建并加入' }}</button>
          </form>
          <router-link class="pickerLink" to="/desk" @click="open = false">前往工作台 →</router-link>
        </template>
      </div>
    </template>
    <button class="deskAddBtn" :class="{ added: inDesk }" :disabled="!code" title="加入工作台" aria-label="加入工作台" :aria-expanded="open">
      <FolderAddOutlined />
    </button>
  </Popover>
</template>

<style scoped>
.deskAddBtn { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; padding: 0; border: 1px solid transparent; border-radius: 7px; color: var(--dim); background: transparent; font-size: 18px; cursor: pointer; }
.deskAddBtn:hover, .deskAddBtn[aria-expanded=true] { color: var(--accent); border-color: var(--line); background: var(--hover); }
.deskAddBtn.added { color: var(--accent); }
.deskAddBtn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.deskPicker { width: min(292px, calc(100vw - 64px)); color: var(--txt); }
.pickerTitle { font-size: 14px; font-weight: 600; }
.pickerNote { margin: 6px 0 12px; color: var(--dim); font-size: 11px; }
.pickerTargets { max-height: 250px; overflow-y: auto; }
.pickerTargets button { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; padding: 10px; background: none; border: 0; border-radius: 6px; text-align: left; color: var(--txt); font: inherit; font-size: 12px; cursor: pointer; }
.pickerTargets button:hover:enabled { background: var(--hover); color: var(--accent); }
.pickerTargets button:disabled { cursor: default; color: var(--dim); }
.pickerTargets small { font-size: 11px; color: var(--dim); white-space: nowrap; }
.pickerTargets span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pickerState { color: var(--dim); font-size: 12px; padding: 12px 0; }
.pickerState button { border: 0; background: none; color: var(--accent); cursor: pointer; }
.pickerCreate { display: flex; gap: 8px; border-top: 1px solid var(--line); padding-top: 12px; margin-top: 8px; }
.pickerCreate input { flex: 1; width: 0; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; color: var(--txt); background: var(--panel-2); font: inherit; font-size: 12px; }
.pickerCreate button { border: 1px solid var(--line); border-radius: 6px; background: var(--panel); color: var(--accent); font: inherit; font-size: 11px; padding: 0 8px; cursor: pointer; }
.pickerCreate button:disabled { opacity: .5; cursor: default; }
.pickerLink { display: block; text-align: right; margin-top: 12px; color: var(--accent); font-size: 11px; }
</style>
