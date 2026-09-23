/* ===== 黑名单状态(轻量 reactive store,与 watchlist store 同风格)=====
   blackCodes:已拉黑的代码集合。黑名单在服务端过滤筛选结果(/api/quote/list),
   前端状态用于行菜单即时隐藏与设置页管理。 */
import { reactive } from "vue";
import { api } from "../api/client";
import { getToken } from "../utils/token";

export const blackState = reactive({
  codes: new Set(), // 已拉黑的股票代码
  loaded: false,
});

// 拉取黑名单代码集合(登录后幂等;未登录直接跳过)
export async function loadBlackCodes(force = false) {
  if (!getToken()) return;
  if (blackState.loaded && !force) return;
  try {
    const d = await api("/api/blacklist");
    blackState.codes = new Set((d.rows || []).map((r) => r.code));
    blackState.loaded = true;
  } catch (e) {
    // 401/403 由 api client 统一跳登录;其余失败保持现状
  }
}

export const inBlack = (code) => blackState.codes.has(code);

// 加入黑名单:成功后才更新本地集合;失败抛错由调用方提示
export async function addBlack(code) {
  await api("/api/blacklist", { method: "POST", body: { code } });
  blackState.codes.add(code);
}

// 移出黑名单(移除后下次查询恢复显示)
export async function removeBlack(code) {
  await api("/api/blacklist/" + code, { method: "DELETE" });
  blackState.codes.delete(code);
}
