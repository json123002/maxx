<script setup>
/* ===== 危险操作二次确认弹窗（删除用户 / 移除自选等共用）=====
   居中卡片 + 背景模糊遮罩,Enter 确认 / Esc 取消,替代 antd Popconfirm。 */
import { onBeforeUnmount, watch } from "vue";

const props = defineProps({
  open: Boolean,
  title: { type: String, default: "确认操作" },
  desc: { type: String, default: "" },
  okText: { type: String, default: "删除" },
  loading: Boolean,
});
const emit = defineEmits(["confirm", "close"]);

function onKey(e) {
  if (!props.open) return;
  if (e.key === "Escape") emit("close");
  if (e.key === "Enter" && !props.loading) emit("confirm");
}
watch(() => props.open, (v) => {
  document[v ? "addEventListener" : "removeEventListener"]("keydown", onKey);
});
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <Transition name="cfm">
      <div v-if="open" class="cfmMask" @click.self="emit('close')">
        <div class="cfmCard" role="alertdialog" :aria-label="title">
          <div class="cfmIcon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3" />
            </svg>
          </div>
          <div class="cfmTitle">{{ title }}</div>
          <div v-if="desc" class="cfmDesc">{{ desc }}</div>
          <div class="cfmOps">
            <button type="button" class="cfmCancel" :disabled="loading" @click="emit('close')">取消</button>
            <button type="button" class="cfmOk" :disabled="loading" @click="emit('confirm')">
              {{ loading ? "处理中…" : okText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cfmMask {
  position: fixed; inset: 0; z-index: 300;
  display: flex; align-items: center; justify-content: center; padding: 20px;
  background: rgba(0, 0, 0, .45);
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
}
.cfmCard {
  width: min(360px, 100%);
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 16px; padding: 24px 22px 18px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, .32);
  text-align: center;
}
.cfmIcon {
  width: 40px; height: 40px; margin: 0 auto 12px;
  display: grid; place-items: center; border-radius: 12px;
  color: var(--up); background: color-mix(in srgb, var(--up) 12%, transparent);
}
.cfmTitle { font-size: 15px; font-weight: 650; color: var(--txt); }
.cfmDesc { margin-top: 8px; font-size: 12.5px; line-height: 1.7; color: var(--dim); }
.cfmOps { display: flex; gap: 10px; margin-top: 20px; }
.cfmCancel, .cfmOk {
  flex: 1; min-height: 38px; border-radius: 999px;
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: opacity .15s, border-color .15s, color .15s;
}
.cfmCancel { background: none; border: 1px solid var(--line); color: var(--dim); }
.cfmCancel:hover:not(:disabled) { color: var(--txt); border-color: var(--line-strong); }
.cfmOk { border: none; background: var(--up); color: #fff; }
.cfmOk:hover:not(:disabled) { opacity: .88; }
.cfmCancel:disabled, .cfmOk:disabled { opacity: .55; cursor: not-allowed; }

/* 进场:遮罩淡入,卡片缩放上浮;出场反向 */
.cfm-enter-active, .cfm-leave-active { transition: opacity .2s ease; }
.cfm-enter-active .cfmCard { transition: transform .24s cubic-bezier(.2, .8, .2, 1), opacity .2s ease; }
.cfm-leave-active .cfmCard { transition: transform .16s ease, opacity .16s ease; }
.cfm-enter-from, .cfm-leave-to { opacity: 0; }
.cfm-enter-from .cfmCard { transform: scale(.94) translateY(10px); opacity: 0; }
.cfm-leave-to .cfmCard { transform: scale(.97) translateY(4px); opacity: 0; }
</style>
