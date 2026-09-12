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

/* 行为埋点上报:fire-and-forget,失败静默(动作白名单见后端 log_routes)。
   同 action+detail 60 秒内去重——刷新/来回切页不重复记;
   状态存 sessionStorage,整页刷新(F5 后 JS 状态清零)依然生效。 */
const TRACK_GAP = 60_000;
const TRACK_KEY = "track-dedup";

function _throttled(key) {
  try {
    const m = JSON.parse(sessionStorage.getItem(TRACK_KEY) || "{}");
    const now = Date.now();
    if (now - (m[key] || 0) < TRACK_GAP) return true;
    m[key] = now;
    for (const k in m) if (now - m[k] >= TRACK_GAP) delete m[k];
    sessionStorage.setItem(TRACK_KEY, JSON.stringify(m));
  } catch { /* storage 不可用则不去重,直接放行 */ }
  return false;
}

export function track(action, detail = "") {
  detail = String(detail).slice(0, 300);
  if (_throttled(action + "|" + detail)) return;
  apiFetch("/api/track", {
    method: "POST",
    body: { action, detail },
  }).catch(() => {});
}
