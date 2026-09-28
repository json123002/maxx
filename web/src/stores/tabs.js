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

function normalizePath(p) {
  if (!p || p === "/" || p === "") return "/home";
  return p;
}

function loadStoredTabs() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        // 严格去重：剔除任何重复的 /home 或 / 标签，确保总览唯一且置顶
        const unique = [];
        const seen = new Set();
        for (const t of parsed) {
          const normPath = normalizePath(t.path);
          const normKey = normPath === "/home" ? "/home" : (t.fullPath || normPath);
          if (!seen.has(normKey)) {
            seen.add(normKey);
            unique.push({
              ...t,
              key: normKey,
              path: normPath,
              fullPath: normKey,
              title: normPath === "/home" ? "总览" : (t.title || "标签页"),
              closable: normPath !== "/home",
            });
          }
        }
        if (!seen.has("/home")) {
          unique.unshift({ ...DEFAULT_TAB });
        }
        return unique;
      }
    }
  } catch (e) {}
  return [{ ...DEFAULT_TAB }];
}

export const tabState = reactive({
  tabs: loadStoredTabs(),
  activeKey: "/home",
  cachedViews: ["HomeView", "ScreenerView", "RadarView", "SectorStrengthView", "CapitalFlowView"],
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

  const path = normalizePath(route.path);
  const fullPath = path === "/home" ? "/home" : route.fullPath;
  const compName = getComponentName(path);

  // 标题判定
  let title = path === "/home" ? "总览" : (route.meta?.title || "标签页");
  if (path.startsWith("/stock/")) {
    const code = route.params?.code || path.split("/").pop();
    title = `个股 ${code}`;
  }

  // 严格按规范化后的路径查重（确保 /home 永远唯一）
  const existingIndex = tabState.tabs.findIndex((t) => {
    if (path === "/home") return t.path === "/home" || t.fullPath === "/home" || t.path === "/";
    return t.fullPath === fullPath;
  });

  if (existingIndex >= 0) {
    tabState.activeKey = tabState.tabs[existingIndex].fullPath;
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
  const normKey = normalizePath(key);
  const index = tabState.tabs.findIndex((t) => t.fullPath === normKey || t.path === normKey || t.fullPath === key);
  if (index === -1) return;
  const remaining = tabState.tabs.slice(0, index + 1);
  tabState.tabs = remaining;
  if (!tabState.tabs.some((t) => t.fullPath === tabState.activeKey)) {
    const fallback = tabState.tabs[index] || tabState.tabs[0];
    tabState.activeKey = fallback.fullPath;
    router.push(fallback.fullPath);
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
