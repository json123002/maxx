<template>
  <a-modal :open="open" title="修改密码" :confirm-loading="loading" @ok="submit" @cancel="close" ok-text="确认修改" cancel-text="取消" :width="360">
    <a-form layout="vertical" style="margin-top: 12px">
      <a-form-item label="原密码">
        <a-input-password v-model:value="oldPwd" placeholder="原密码" autocomplete="current-password" />
      </a-form-item>
      <a-form-item label="新密码(至少 6 位)">
        <a-input-password v-model:value="newPwd" placeholder="新密码(至少 6 位)" autocomplete="new-password" />
      </a-form-item>
      <a-form-item label="确认新密码" :validate-status="err ? 'error' : ''" :help="err" style="margin-bottom: 0">
        <a-input-password v-model:value="newPwd2" placeholder="确认新密码" autocomplete="new-password" @keyup.enter="submit" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, watch } from "vue";
import { message } from "ant-design-vue";
import { apiFetch } from "../api/client";

const props = defineProps({ open: Boolean });
const emit = defineEmits(["close"]);

const oldPwd = ref(""), newPwd = ref(""), newPwd2 = ref("");
const err = ref(""), loading = ref(false);

watch(() => props.open, (v) => {
  if (v) { oldPwd.value = newPwd.value = newPwd2.value = ""; err.value = ""; }
});

function close() { emit("close"); }

async function submit() {
  err.value = "";
  if (newPwd.value.length < 6) { err.value = "新密码至少 6 位"; return; }
  if (newPwd.value !== newPwd2.value) { err.value = "两次输入的新密码不一致"; return; }
  loading.value = true;
  try {
    const r = await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: { old_password: oldPwd.value, new_password: newPwd.value },
    });
    if (!r.ok) { err.value = (await r.json().catch(() => ({}))).detail || "修改失败"; return; }
    close();
    message.success("密码已修改");
  } catch (e) {
    if (e.message !== "unauthorized") err.value = "网络错误,请重试";
  } finally {
    loading.value = false;
  }
}
</script>
