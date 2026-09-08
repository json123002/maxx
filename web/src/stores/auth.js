/* ===== 会话令牌 + 当前用户(轻量 reactive store,不引 pinia)===== */
import { reactive } from "vue";
import { apiFetch } from "../api/client";
import { getToken, setToken, removeToken } from "../utils/token";

export { getToken, setToken };

export const authState = reactive({
  user: null, // { id, username, role }
});

export function clearToken() {
  removeToken();
  authState.user = null;
}

// 服务端校验令牌并取回用户对象;失败返回 null
export async function fetchMe() {
  if (!getToken()) return null;
  try {
    const r = await apiFetch("/api/auth/me");
    authState.user = (await r.json()).user;
    return authState.user;
  } catch (e) {
    return null;
  }
}

export async function logout() {
  try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
  clearToken();
}
