<template>
  <a-layout class="appLayout">
    <!-- 左侧菜单:后续新功能只需在 menus 数组里加一项 -->
    <a-layout-sider v-model:collapsed="collapsed" :trigger="null" collapsible :width="200" breakpoint="lg" class="appSider">
      <div class="siderBrand" @click="$router.push('/home')">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-label="alpha-finder"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8 11 C 6 5, 5 4, 7 7"/>
          <path d="M16 11 C 19 5, 20 4, 18 7"/>
          <path d="M6 11 Q6 9 8 9 L16 9 Q18 9 18 11 L18 19 Q18 21 16 21 L8 21 Q6 21 6 19 Z"/>
        </svg>
        <span v-show="!collapsed" class="siderName">alpha-finder</span>
      </div>
      <a-menu v-model:openKeys="openKeys" :selected-keys="[route.path]" mode="inline" class="siderMenu" @click="onMenu">
        <template v-for="m in menus" :key="m.path || m.key">
          <a-sub-menu v-if="m.children" :key="m.key">
            <template #icon><component :is="m.icon" /></template>
            <template #title>{{ m.title }}</template>
            <a-menu-item v-for="c in m.children" :key="c.path">
              <template #icon><component :is="c.icon" /></template>
              {{ c.title }}
            </a-menu-item>
          </a-sub-menu>
          <a-menu-item v-else :key="m.path">
            <template #icon><component :is="m.icon" /></template>
            {{ m.title }}
          </a-menu-item>
        </template>
      </a-menu>
      <!-- 边缘折叠钮(ChatGPT 式):骑在侧边栏右缘的小圆钮 -->
      <button class="edgeToggle" :title="collapsed ? '展开侧栏' : '收起侧栏'"
              @click="collapsed = !collapsed">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"
             :style="{ transform: collapsed ? 'rotate(180deg)' : 'none' }">
          <path d="M15 18l-6-6 6-6"/>
        </svg>
      </button>
    </a-layout-sider>

    <a-layout class="mainSide">
      <!-- 顶栏:页面标题 + 主题切换 + 用户菜单 -->
      <a-layout-header class="appHeader">
        <span class="hdrTitle">{{ route.meta.title || "" }}</span>
        <span class="hdrNote">{{ hdrNote }}</span>
        <span class="hdrSpacer"></span>
        <a-tooltip :title="themeMode === 'light' ? '切换深色' : '切换浅色'">
          <button class="iconBtn" @click="toggleTheme">
            <MoonIcon v-if="themeMode === 'light'" />
            <SunIcon v-else />
          </button>
        </a-tooltip>
        <a-dropdown placement="bottomRight" :trigger="['click']">
          <span class="userChip">
            <i class="uAvatar">{{ (authState.user?.username || "?").slice(0, 1).toUpperCase() }}</i>
            <span class="uName">{{ authState.user?.username }}</span>
            <DownOutlined class="uCaret" />
          </span>
          <template #overlay>
            <a-menu>
              <a-menu-item key="role" disabled class="roleItem">
                {{ authState.user?.root ? "超级管理员" : authState.user?.role === "admin" ? "管理员" : "普通用户" }}
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item key="pwd" @click="pwdOpen = true">
                <KeyOutlined /> 修改密码
              </a-menu-item>
              <a-menu-item key="logout" @click="onLogout">
                <LogoutOutlined /> 退出登录
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </a-layout-header>

      <a-layout-content class="appContent">
        <router-view />
      </a-layout-content>
    </a-layout>

    <PwdModal :open="pwdOpen" @close="pwdOpen = false" />
  </a-layout>
</template>

<script setup>
import { ref, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  DownOutlined, KeyOutlined, LogoutOutlined,
  DashboardOutlined, FundViewOutlined, TeamOutlined, StarOutlined,
  FileTextOutlined, HistoryOutlined, FireOutlined, SettingOutlined, RadarChartOutlined,
} from "@ant-design/icons-vue";
import { authState, logout } from "../stores/auth";
import { quoteSource, loadQuoteSource, activePersonalSource } from "../stores/quotesource";
import { themeMode, toggleTheme } from "../utils/theme";
import PwdModal from "./PwdModal.vue";

const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const pwdOpen = ref(false);

// 顶栏常驻数据来源说明:全市场数据走默认源;配置/公开了行情源时标注个股实时来源
loadQuoteSource();
const hdrNote = computed(() => {
  const p = activePersonalSource();
  return "数据源:东方财富(全市场)" + (p ? " + " + p + "(个股实时)" : "")
    + " · 仅作客观数据筛选,不构成投资建议";
});

// 菜单配置:新增功能页在这里加一项即可(adminOnly 仅管理员可见,rootOnly 仅隐藏 root 可见)
// 带 children 的为一级分组;子项全被权限过滤掉时整组不显示
const MENUS = [
  { path: "/home", title: "总览", icon: DashboardOutlined },
  { key: "grp-quote", title: "行情筛选", icon: FundViewOutlined, children: [
    { path: "/screener", title: "换手率筛选", icon: FundViewOutlined },
    { path: "/radar", title: "涨停雷达", icon: FireOutlined },
    { path: "/flow", title: "板块资金", icon: RadarChartOutlined },
    { path: "/history", title: "历史榜单", icon: HistoryOutlined },
  ] },
  { path: "/watchlist", title: "我的自选", icon: StarOutlined },
  { path: "/desk", title: "我的工作台", icon: FundViewOutlined },
  { path: "/settings", title: "设置", icon: SettingOutlined },
  { key: "grp-sys", title: "系统管理", icon: SettingOutlined, children: [
    { path: "/admin", title: "用户管理", icon: TeamOutlined, adminOnly: true },
    { path: "/logs", title: "日志", icon: FileTextOutlined, rootOnly: true },
  ] },
];
const visible = (m) =>
  (!m.adminOnly || ["super", "admin"].includes(authState.user?.role)) &&
  (!m.rootOnly || authState.user?.hidden);
const menus = computed(() =>
  MENUS.map((m) => m.children ? { ...m, children: m.children.filter(visible) } : m)
    .filter((m) => (m.children ? m.children.length : visible(m)))
);

// 当前路由所在分组自动展开(保留用户手动开合的其它分组)
const openKeys = ref([]);
function syncOpen(path) {
  const g = MENUS.find((m) => m.children?.some((c) => c.path === path));
  if (g && !openKeys.value.includes(g.key)) openKeys.value = [...openKeys.value, g.key];
}
syncOpen(route.path);
watch(() => route.path, syncOpen);

function onMenu({ key }) { router.push(key); }

async function onLogout() {
  await logout();
  router.replace("/login");
}
</script>

<!-- 太阳/月亮图标(内联,保持与旧版一致的线框风格) -->
<script>
const SunIcon = {
  render() {
    return h("svg", { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" }, [
      h("circle", { cx: 12, cy: 12, r: 4 }),
      h("path", { d: "M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" }),
    ]);
  },
};
const MoonIcon = {
  render() {
    return h("svg", { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" }, [
      h("path", { d: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" }),
    ]);
  },
};
export default { components: { SunIcon, MoonIcon } };
</script>

<style scoped>
.appLayout { min-height: 100vh; }

/* ===== 侧边栏 ===== */
.appSider {
  background: var(--panel) !important;
  border-right: 1px solid var(--line);
}
.siderBrand {
  height: 60px; display: flex; align-items: center; justify-content: center; gap: 10px;
  color: var(--brand-red); cursor: pointer; overflow: hidden; white-space: nowrap;
  border-bottom: 1px solid var(--line);
}
.siderName { font-size: 16px; font-weight: 600; color: var(--txt); letter-spacing: .01em; }
.siderMenu {
  background: transparent !important;
  border-inline-end: none !important;
  padding-top: 8px;
}

/* ===== 顶栏 ===== */
.appHeader {
  height: 60px; line-height: 60px; padding: 0 20px;
  background: var(--panel) !important;
  border-bottom: 1px solid var(--line);
  display: flex; align-items: center; gap: 14px;
}
.hdrTitle { font-size: 15px; font-weight: 600; }
.hdrNote { color: var(--dim); font-size: 12px; }
.hdrSpacer { flex: 1; }
@media (max-width: 900px) { .hdrNote { display: none; } }

.iconBtn {
  background: none; border: 1px solid var(--line); border-radius: 999px;
  width: 32px; height: 32px; cursor: pointer; color: var(--dim);
  display: inline-flex; align-items: center; justify-content: center;
  transition: color .15s, border-color .15s;
}
.iconBtn:hover { color: var(--txt); border-color: var(--line-strong); }

.userChip {
  display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
  color: var(--txt); font-size: 13px; padding: 4px 10px 4px 4px;
  border-radius: 999px; transition: background .15s;
}
.userChip:hover { background: var(--hover); }
.uAvatar {
  font-style: normal; width: 26px; height: 26px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; font-family: var(--mono);
  color: var(--btn-txt); background: var(--btn-bg);
}
.uCaret { font-size: 10px; color: var(--dim); }
.roleItem { font-size: 12px !important; cursor: default !important; }
@media (max-width: 640px) { .uName, .uCaret { display: none; } }

/* ===== 侧栏边缘折叠钮:骑在右缘的 22px 小圆钮 ===== */
.edgeToggle {
  position: absolute; right: -11px; top: 74px; z-index: 30;
  width: 22px; height: 22px; border-radius: 50%;
  background: var(--panel); border: 1px solid var(--line-strong);
  color: var(--dim); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .18s, color .15s, border-color .15s, box-shadow .15s;
}
.edgeToggle svg { transition: transform .2s; display: block; }
.appSider:hover .edgeToggle, .edgeToggle:focus-visible { opacity: 1; }
.edgeToggle:hover { color: var(--txt); border-color: var(--dim); box-shadow: 0 2px 8px rgba(0, 0, 0, .12); }
/* 触屏无 hover:常驻显示 */
@media (hover: none) { .edgeToggle { opacity: 1; } }

/* ===== 内容区:桌面固定一屏(筛选页表格内部滚动),子页可自行滚动 ===== */
.mainSide { min-width: 0; }
.appContent {
  display: flex; flex-direction: column;
  height: calc(100vh - 60px);
  overflow: auto;
  padding: 16px 24px 20px;
}
@media (max-width: 768px) {
  .appContent { height: auto; min-height: calc(100vh - 60px); padding: 12px 12px calc(24px + env(safe-area-inset-bottom)); }
}
</style>
