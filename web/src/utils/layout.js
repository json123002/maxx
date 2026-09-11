/* ===== 页面布局偏好:铺开(默认) / 居中窄栏 =====
   与 theme.js 同模式:localStorage 记忆 + body 类名驱动 CSS 变量。
   各页面容器用 max-width: var(--page-max) 消费,窄栏模式统一 1180px 居中。 */
import { ref } from "vue";

const KEY = "ts-layout-wide";   // "1"=铺开(默认) "0"=窄栏

export const layoutWide = ref(true);

function apply() {
  document.body.classList.toggle("narrow", !layoutWide.value);
}

export function initLayout() {
  try { layoutWide.value = localStorage.getItem(KEY) !== "0"; } catch (e) {}
  apply();
}

export function toggleLayout() {
  layoutWide.value = !layoutWide.value;
  try { localStorage.setItem(KEY, layoutWide.value ? "1" : "0"); } catch (e) {}
  apply();
}
