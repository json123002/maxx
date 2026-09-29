/* ===== 顶部行情走马灯偏好与状态 (Home Ticker Store) =====
   支持用户在「设置」中自由勾选频道、调整滚动速度与悬停交互。 */
import { reactive, watch } from "vue";

export const TICKER_STORAGE_KEY = "home_ticker_prefs_v1";

export const TICKER_CHANNELS = [
  { key: "indices", label: "大盘核心指数", desc: "上证/深成/创业板指/科创50及两市总成交额", default: true, badge: "指数", color: "indigo" },
  { key: "hot", label: "全市场热度榜", desc: "换手率与成交额复合活跃热股", default: true, badge: "热度", color: "amber" },
  { key: "ladder", label: "连板天梯龙头", desc: "全市场最高连板梯队（连板王/接力先锋）", default: true, badge: "龙头", color: "rose" },
  { key: "l2_orders", label: "盘口大单异动", desc: "全市场特大挂买/封板/异动事件流", default: true, badge: "异动", color: "cyan" },
  { key: "watchlist", label: "我的重点自选", desc: "自选股与星标池标的实时涨跌", default: true, badge: "自选", color: "emerald" },
  { key: "aphorisms", label: "投资哲学箴言", desc: "经典交易纪律与大师箴言穿插轮播", default: false, badge: "箴言", color: "violet" },
];

export const TICKER_SPEEDS = [
  { key: "slow", label: "平缓 (65s)", duration: 65 },
  { key: "normal", label: "标准 (42s)", duration: 42 },
  { key: "fast", label: "紧凑 (26s)", duration: 26 },
];

export const tickerState = reactive({
  enabled: true,
  speed: "slow",
  hoverPause: true,
  channels: {
    indices: true,
    hot: true,
    ladder: true,
    l2_orders: true,
    watchlist: true,
    aphorisms: false,
  },
  loaded: false,
});

export function loadTickerPrefs() {
  try {
    const raw = localStorage.getItem(TICKER_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.enabled === "boolean") tickerState.enabled = parsed.enabled;
      if (parsed.speed && ["slow", "normal", "fast"].includes(parsed.speed)) tickerState.speed = parsed.speed;
      if (typeof parsed.hoverPause === "boolean") tickerState.hoverPause = parsed.hoverPause;
      if (parsed.channels && typeof parsed.channels === "object") {
        Object.assign(tickerState.channels, parsed.channels);
      }
    }
  } catch (e) {
    console.warn("Failed to load ticker prefs:", e);
  }
  tickerState.loaded = true;
}

export function saveTickerPrefs() {
  try {
    localStorage.setItem(
      TICKER_STORAGE_KEY,
      JSON.stringify({
        enabled: tickerState.enabled,
        speed: tickerState.speed,
        hoverPause: tickerState.hoverPause,
        channels: { ...tickerState.channels },
      })
    );
  } catch (e) {
    console.warn("Failed to save ticker prefs:", e);
  }
}

// 自动加载初始配置
loadTickerPrefs();
