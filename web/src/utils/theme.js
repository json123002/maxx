/* ===== 明暗主题:localStorage 记忆 + 按时段自动(手动覆盖优先)===== */
import { ref } from "vue";

const THEME_KEY = "ts-theme";
const MANUAL_KEY = "ts-theme-manual";

// 响应式当前主题(供 antd ConfigProvider 等联动)
export const themeMode = ref("dark");

export function getTheme() {
  return document.documentElement.dataset.theme || "dark";
}

export function setTheme(theme, manual) {
  document.documentElement.dataset.theme = theme;
  themeMode.value = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
    if (manual) localStorage.setItem(MANUAL_KEY, "1");
  } catch (e) {}
}

export function toggleTheme() {
  setTheme(getTheme() === "light" ? "dark" : "light", true);
}

export function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch (e) {}
  if (stored) {
    document.documentElement.dataset.theme = stored;
  } else {
    const h = new Date().getHours();
    document.documentElement.dataset.theme = (h >= 18 || h < 8) ? "dark" : "light";
  }
  themeMode.value = document.documentElement.dataset.theme;
  // 未手动覆盖时,每 5 分钟按时段自动切换
  setInterval(() => {
    try { if (localStorage.getItem(MANUAL_KEY)) return; } catch (e) {}
    const h = new Date().getHours();
    const want = (h >= 18 || h < 8) ? "dark" : "light";
    if (want !== getTheme()) setTheme(want);
  }, 5 * 60 * 1000);
}
