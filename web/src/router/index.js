import { createRouter, createWebHashHistory } from "vue-router";
import { getToken, fetchMe, authState } from "../stores/auth";

const routes = [
  { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { public: true } },
  {
    path: "/",
    component: () => import("../layout/MainLayout.vue"),
    children: [
      { path: "", redirect: "/home" },
      { path: "home", name: "home", component: () => import("../views/HomeView.vue"), meta: { title: "工作台" } },
      { path: "screener", name: "screener", component: () => import("../views/ScreenerView.vue"), meta: { title: "换手率筛选" } },
      { path: "admin", name: "admin", component: () => import("../views/AdminView.vue"), meta: { title: "用户管理", admin: true } },
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
    const u = await fetchMe();
    if (!u) return { path: "/login" };
  }
  if (to.meta.admin && authState.user.role !== "admin") return { path: "/" };
  return true;
});

export default router;
