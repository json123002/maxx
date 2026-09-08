/* ===== API client:Bearer 令牌 + 401/403 回登录页(移植自旧 auth.js apiFetch)===== */
import { getToken, removeToken } from "../utils/token";
import router from "../router";

export async function apiFetch(url, opts = {}) {
  opts.headers = Object.assign({}, opts.headers, { Authorization: "Bearer " + getToken() });
  if (opts.body && typeof opts.body === "object") {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(url, opts);
  if (r.status === 401 || r.status === 403) {
    removeToken();
    router.replace("/login");
    throw new Error("unauthorized");
  }
  return r;
}

// 便捷封装:解析 json,非 2xx 抛 detail
export async function api(url, opts) {
  const r = await apiFetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || "HTTP " + r.status);
  return d;
}
