import { reactive, nextTick } from "vue";
import router from "../router";

const STORAGE_KEY = "maxx_nav_tabs_v1";

const COMPONENT_NAME_MAP = {
  "/home": "HomeView",
  "/screener": "ScreenerView",
  "/radar": "RadarView",
  "/sector": "SectorStrengthView",
  "/flow": "CapitalFlowView",
  "/watchlist": "WatchlistView",
  "/desk": "MyDeskView",
  "/history": "HistoryView",
  "/settings": "SettingsView",
  "/admin": "AdminView",
  "/logs": "LogView",
};

function getComponentName(path) {
  if (path.startsWith("/stock/")) return "StockView";
  return COMPONENT_NAME_MAP[path] || "";
}

const DEFAULT_TAB = {
  key: "/home",
  fullPath: "/home",
  path: "/home",
  title: "总览",
  name: "HomeView",
  closable: false,
};

function loadStoredTabs() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        // 保证 /home 始终存在且不可关闭
        const hasHome = parsed.some((t) => t.path === "/home");
        const list = hasHome ? parsed : [DEFAULT_TAB, ...parsed];
        return list.map((t) => ({ ...t, closable: t.path !== "/home" }));
      }
    }
  } catch (e) {}
  return [{ ...DEFAULT_TAB }];
}

export const tabState = reactive({
  tabs: loadStoredTabs(),
  activeKey: "/home",
  cachedViews: ["HomeView", "ScreenerView", "RadarView", "CapitalFlowView"],
});

function syncStorage() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabState.tabs));
  } catch (e) {}
}

function updateCachedViews() {
  const names = new Set(["HomeView"]);
  tabState.tabs.forEach((t) => {
    if (t.name) names.add(t.name);
  });
  tabState.cachedViews = Array.from(names);
}

/**
 * 添加或激活标签页
 * @param {import('vue-router').RouteLocationNormalized} route
 * @returns {{ isNew: boolean }} 返回是否是全新打开的标签（用于防止重复记日志）
 */
export function addTab(route) {
  if (!route || !route.path || route.path === "/login" || route.meta?.public) {
    return { isNew: false };
  }

  const fullPath = route.fullPath;
  const path = route.path;
  const compName = getComponentName(path);

  // 标题判定
  let title = route.meta?.title || "标签页";
  if (path.startsWith("/stock/")) {
    const code = route.params?.code || path.split("/").pop();
    title = `个股 ${code}`;
  }

  const existingIndex = tabState.tabs.findIndex((t) => t.fullPath === fullPath);
  if (existingIndex >= 0) {
    tabState.activeKey = fullPath;
    if (compName && !tabState.cachedViews.includes(compName)) {
      tabState.cachedViews.push(compName);
    }
    return { isNew: false }; // 已存在该标签，切换无需重复产生页面打开日志
  }

  // 新增标签
  const newTab = {
    key: fullPath,
    fullPath,
    path,
    title,
    name: compName,
    closable: path !== "/home",
  };

  tabState.tabs.push(newTab);
  tabState.activeKey = fullPath;
  if (compName && !tabState.cachedViews.includes(compName)) {
    tabState.cachedViews.push(compName);
  }
  syncStorage();
  return { isNew: true };
}

/**
 * 关闭标签页
 */
export function removeTab(key) {
  const index = tabState.tabs.findIndex((t) => t.fullPath === key);
  if (index === -1) return;
  const target = tabState.tabs[index];
  if (!target.closable) return;

  const isActive = tabState.activeKey === key;
  tabState.tabs.splice(index, 1);

  // 若关闭的是当前激活页，自动跳转到相邻页
  if (isActive) {
    const nextTab = tabState.tabs[index] || tabState.tabs[index - 1] || tabState.tabs[0];
    if (nextTab) {
      tabState.activeKey = nextTab.fullPath;
      router.push(nextTab.fullPath);
    }
  }

  // 清理缓存
  updateCachedViews();
  syncStorage();
}

/**
 * 关闭其它标签页
 */
export function closeOthers(key) {
  tabState.tabs = tabState.tabs.filter((t) => !t.closable || t.fullPath === key);
  tabState.activeKey = key;
  router.push(key);
  updateCachedViews();
  syncStorage();
}

/**
 * 关闭右侧标签页
 */
export function closeRight(key) {
  const index = tabState.tabs.findIndex((t) => t.fullPath === key);
  if (index === -1) return;
  const remaining = tabState.tabs.slice(0, index + 1);
  // 保留 home 如果之前有
  tabState.tabs = remaining;
  if (!tabState.tabs.some((t) => t.fullPath === tabState.activeKey)) {
    tabState.activeKey = key;
    router.push(key);
  }
  updateCachedViews();
  syncStorage();
}

/**
 * 关闭所有可关闭标签页，回到总览
 */
export function closeAll() {
  tabState.tabs = tabState.tabs.filter((t) => !t.closable);
  tabState.activeKey = "/home";
  router.push("/home");
  updateCachedViews();
  syncStorage();
}

/**
 * 更新标签页标题（例如个股详情页拉取到股票名称后更新为 "601579 山煤国际"）
 */
export function updateTabTitle(fullPath, newTitle) {
  const tab = tabState.tabs.find((t) => t.fullPath === fullPath);
  if (tab && newTitle && tab.title !== newTitle) {
    tab.title = newTitle;
    syncStorage();
  }
}
