/* ===== 自选股状态(轻量 reactive store,与 auth store 同风格)=====
   watchCodes:已加自选的代码集合,供筛选页/自选页共用星标状态。 */
import { reactive } from "vue";
import { api } from "../api/client";
import { getToken } from "../utils/token";

export const watchState = reactive({
  codes: new Set(), // 已加自选的股票代码
  loaded: false,
});

// 拉取自选代码集合(登录后幂等;未登录直接跳过)
export async function loadWatchCodes(force = false) {
  if (!getToken()) return;
  if (watchState.loaded && !force) return;
  try {
    const d = await api("/api/watchlist");
    watchState.codes = new Set(d.rows.map((r) => r.f12));
    watchState.loaded = true;
  } catch (e) {
    // 401/403 由 api client 统一跳登录;其余失败保持现状
  }
}

export const inWatch = (code) => watchState.codes.has(code);

// 星标开关:未加 → POST,已加 → DELETE;失败抛错由调用方提示
export async function toggleWatch(code, added) {
  if (added) {
    await api("/api/watchlist", { method: "POST", body: { code } });
    watchState.codes.add(code);
  } else {
    await api("/api/watchlist/" + code, { method: "DELETE" });
    watchState.codes.delete(code);
  }
}
