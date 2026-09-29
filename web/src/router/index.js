import { createRouter, createWebHashHistory } from "vue-router";
import { getToken, fetchMe, authState } from "../stores/auth";
import { track } from "../api/client";

const routes = [
  { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { public: true } },
  {
    path: "/",
    component: () => import("../layout/MainLayout.vue"),
    children: [
      { path: "", redirect: "/home" },
      { path: "home", name: "home", component: () => import("../views/HomeView.vue"), meta: { title: "总览" } },
      { path: "screener", name: "screener", component: () => import("../views/ScreenerView.vue"), meta: { title: "换手率筛选" } },
      { path: "admin", name: "admin", component: () => import("../views/AdminView.vue"), meta: { title: "用户管理", admin: true } },
      { path: "watchlist", name: "watchlist", component: () => import("../views/WatchlistView.vue"), meta: { title: "我的自选" } },
      { path: "desk", name: "desk", component: () => import("../views/MyDeskView.vue"), meta: { title: "我的工作台", pageTrack: false } },
      { path: "history", name: "history", component: () => import("../views/HistoryView.vue"), meta: { title: "历史榜单", pageTrack: false } },
      { path: "radar", name: "radar", component: () => import("../views/RadarView.vue"), meta: { title: "涨停雷达", pageTrack: false } },
      { path: "sector", name: "sector", component: () => import("../views/SectorStrengthView.vue"), meta: { title: "板块强度", pageTrack: false } },
      { path: "flow", name: "flow", component: () => import("../views/CapitalFlowView.vue"), meta: { title: "板块资金", pageTrack: false } },
      { path: "neural", name: "neural", component: () => import("../views/NeuralLabView.vue"), meta: { title: "神经网络实验室", pageTrack: false } },
      { path: "stock/:code", name: "stock", component: () => import("../views/StockView.vue"), meta: { title: "个股详情", pageTrack: false } },
      { path: "settings", name: "settings", component: () => import("../views/SettingsView.vue"), meta: { title: "设置" } },
      // 操作日志:仅隐藏 root 可见(菜单隐藏 + 路由守卫 + 后端 404 三道)
      { path: "logs", name: "logs", component: () => import("../views/LogView.vue"), meta: { title: "操作日志", root: true } },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach(async (to) => {
  if (to.meta.public) {
    // 已登录访问登录页 → 直接进主页
    if (getToken()) return { path: "/" };
    return true;
  }
  if (!getToken()) return { path: "/login" };
  if (!authState.user) {
    await fetchMe();
    // 仅当 token 已被清除(401,apiFetch 内 removeToken)才回登录页;
    // 后端不可达等网络失败时放行——页面会显示加载失败,
    // 否则 /login 守卫看到 token 又弹回 /,两个守卫互相重定向形成请求死循环
    if (!authState.user && !getToken()) return { path: "/login" };
  }
  if (to.meta.admin && authState.user?.role !== "admin") return { path: "/" };
  if (to.meta.root && !authState.user?.hidden) return { path: "/" };
  return true;
});

import { addTab } from "../stores/tabs";

// 页面打开埋点：仅登录后访问非公开页时上报（fire-and-forget，失败静默）。
// 结合多标签页：仅在全新打开标签页或首次载入时上报；在已打开的标签间切换属纯前端视图呈现，
// 不重复触发上报，严格保证操作日志精确、真实、不被滥刷。
// 带 pageTrack:false 的页面(工作台/雷达/资金流/历史/个股)有各自的 *_view
// 专属埋点且附带详情,跳过通用 page_view 避免一次打开记两条。
let isInitial = true;
router.afterEach((to) => {
  const { isNew } = addTab(to);
  if ((isNew || isInitial) && !to.meta.public && to.meta.pageTrack !== false && getToken()) {
    track("page_view", to.meta.title || to.path);
  }
  isInitial = false;
});

export default router;
