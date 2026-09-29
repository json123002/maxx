/* ===== 预警中心状态与轮询(watchlist.js 风格模块单例)=====
   轮询挂在 MainLayout(而非 AlertsView),保证切标签页(keep-alive 休眠)时预警照收;
   事件到达 → antd toast + 浏览器 Notification(已授权时)。 */
import { reactive } from "vue";
import { message } from "ant-design-vue";
import { api } from "../api/client";

const POLL_MS = 30000;

export const alertState = reactive({
  unread: 0,
  maxSeenId: 0,
  started: false,
  permission: typeof Notification !== "undefined" ? Notification.permission : "denied",
});

let timer = null;

async function poll() {
  if (document.hidden) return;
  try {
    const d = await api("/api/alerts/events?since_id=" + alertState.maxSeenId);
    alertState.maxSeenId = d.max_id;
    alertState.unread = d.unread;
    if (d.events.length) onEvents(d.events);
  } catch (e) {
    /* 预警轮询失败静默,下轮再试(与 track 同一哲学) */
  }
}

function onEvents(list) {
  for (const ev of list) {
    const title = `${ev.name || ""} ${ev.code}`.trim();
    const body = ev.detail || "";
    if (alertState.permission === "granted") {
      try {
        new Notification(title, { body });
        continue;
      } catch (e) { /* 部分浏览器构造失败,落回站内 toast */ }
    }
    message.warning(`${title} ${body}`);
  }
}

export function startAlertPolling() {
  if (alertState.started) return;
  alertState.started = true;
  poll();
  timer = setInterval(poll, POLL_MS);
}

export function stopAlertPolling() {
  if (timer) clearInterval(timer);
  timer = null;
  alertState.started = false;
}

export async function requestNotifyPermission() {
  if (typeof Notification === "undefined") return "denied";
  const p = await Notification.requestPermission();
  alertState.permission = p;
  return p;
}

export async function markAllRead() {
  await api("/api/alerts/events/read", { method: "POST", body: { ids: [] } });
  alertState.unread = 0;
}
