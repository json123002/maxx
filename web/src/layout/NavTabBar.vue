<template>
  <nav class="navTabBar" aria-label="页面标签导航" @wheel.prevent="onWheel">
    <div ref="tabsContainer" class="tabsScroll">
      <div
        v-for="tab in tabState.tabs"
        :key="tab.key || tab.fullPath"
        class="tabItem"
        :class="{ active: tab.fullPath === tabState.activeKey }"
        :title="tab.title"
        @click="onSelectTab(tab)"
        @mouseup.middle.stop="tab.closable && onRemoveTab(tab.fullPath)"
        @contextmenu.prevent="onContextMenu($event, tab)"
      >
        <span class="tabIcon">
          <component :is="getTabIcon(tab.path)" />
        </span>
        <span class="tabTitle">{{ tab.title }}</span>
        <button
          v-if="tab.closable"
          class="tabClose"
          title="关闭标签"
          @click.stop="onRemoveTab(tab.fullPath)"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>

    <!-- 标签操作下拉菜单 -->
    <div class="tabsActions">
      <a-dropdown placement="bottomRight" :trigger="['click']">
        <button class="actionBtn" title="标签页操作">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="12" cy="12" r="1.5"></circle>
            <circle cx="19" cy="12" r="1.5"></circle>
            <circle cx="5" cy="12" r="1.5"></circle>
          </svg>
        </button>
        <template #overlay>
          <a-menu>
            <a-menu-item key="refresh" @click="onReloadCurrent">
              <ReloadOutlined /> 刷新当前页
            </a-menu-item>
            <a-menu-divider />
            <a-menu-item key="close-others" @click="onCloseOthers">
              <CloseOutlined /> 关闭其他标签
            </a-menu-item>
            <a-menu-item key="close-all" @click="onCloseAll">
              <StopOutlined /> 关闭全部可关标签
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>

    <!-- 右键快捷菜单 -->
    <div
      v-if="contextMenu.visible"
      class="contextMenu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <div class="ctxItem" @click="onContextReload">
        <ReloadOutlined /> 刷新本页
      </div>
      <div v-if="contextMenu.tab?.closable" class="ctxItem" @click="onContextCloseCurrent">
        <CloseOutlined /> 关闭本页
      </div>
      <div class="ctxItem" @click="onContextCloseOthers">
        关闭其他
      </div>
      <div class="ctxItem" @click="onContextCloseAll">
        关闭所有
      </div>
    </div>
  </nav>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  DashboardOutlined,
  FundViewOutlined,
  FireOutlined,
  RadarChartOutlined,
  StarOutlined,
  HistoryOutlined,
  LineChartOutlined,
  SettingOutlined,
  TeamOutlined,
  FileTextOutlined,
  ReloadOutlined,
  CloseOutlined,
  StopOutlined,
  CrownOutlined,
} from "@ant-design/icons-vue";
import { tabState, removeTab, closeOthers, closeAll } from "../stores/tabs";

const router = useRouter();
const tabsContainer = ref(null);

function getTabIcon(path) {
  if (path === "/home") return DashboardOutlined;
  if (path === "/screener") return FundViewOutlined;
  if (path === "/radar") return FireOutlined;
  if (path === "/sector") return CrownOutlined;
  if (path === "/flow") return RadarChartOutlined;
  if (path === "/watchlist") return StarOutlined;
  if (path === "/desk") return FundViewOutlined;
  if (path === "/history") return HistoryOutlined;
  if (path.startsWith("/stock/")) return LineChartOutlined;
  if (path === "/settings") return SettingOutlined;
  if (path === "/admin") return TeamOutlined;
  if (path === "/logs") return FileTextOutlined;
  return FundViewOutlined;
}

function onSelectTab(tab) {
  if (tab.fullPath !== tabState.activeKey) {
    tabState.activeKey = tab.fullPath;
    router.push(tab.fullPath);
  }
}

function onRemoveTab(fullPath) {
  removeTab(fullPath);
}

function onCloseOthers() {
  closeOthers(tabState.activeKey);
}

function onCloseAll() {
  closeAll();
}

function onReloadCurrent() {
  const current = tabState.activeKey;
  router.replace({ path: "/redirect", query: { to: current } }).catch(() => {
    // 若无重定向路由，原位刷新路由
    router.go(0);
  });
}

// 滚轮横向滚动标签栏
function onWheel(e) {
  if (!tabsContainer.value) return;
  tabsContainer.value.scrollLeft += e.deltaY;
}

// 自动滚动到激活标签
function scrollToActive() {
  nextTick(() => {
    if (!tabsContainer.value) return;
    const activeEl = tabsContainer.value.querySelector(".tabItem.active");
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  });
}

watch(() => tabState.activeKey, scrollToActive);

/* ========================================================
   右键菜单控制
   ======================================================== */
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  tab: null,
});

function onContextMenu(e, tab) {
  contextMenu.visible = true;
  contextMenu.x = Math.min(e.clientX, window.innerWidth - 140);
  contextMenu.y = e.clientY + 5;
  contextMenu.tab = tab;
}

function closeContextMenu() {
  contextMenu.visible = false;
  contextMenu.tab = null;
}

function onContextReload() {
  if (contextMenu.tab) {
    if (contextMenu.tab.fullPath !== tabState.activeKey) {
      router.push(contextMenu.tab.fullPath);
    }
    router.go(0);
  }
  closeContextMenu();
}

function onContextCloseCurrent() {
  if (contextMenu.tab?.closable) {
    removeTab(contextMenu.tab.fullPath);
  }
  closeContextMenu();
}

function onContextCloseOthers() {
  if (contextMenu.tab) {
    closeOthers(contextMenu.tab.fullPath);
  }
  closeContextMenu();
}

function onContextCloseAll() {
  closeAll();
  closeContextMenu();
}

onMounted(() => {
  window.addEventListener("click", closeContextMenu);
  scrollToActive();
});
onBeforeUnmount(() => {
  window.removeEventListener("click", closeContextMenu);
});
</script>

<style scoped>
.navTabBar {
  display: flex;
  align-items: center;
  height: 38px;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  user-select: none;
  position: relative;
  z-index: 10;
  padding: 0 8px;
}

.tabsScroll {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE 10+ */
  padding: 0 4px;
}
.tabsScroll::-webkit-scrollbar {
  display: none; /* Chrome, Safari */
}

/* 单个标签项 */
.tabItem {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--dim);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
  flex: none;
  max-width: 180px;
}

.tabItem:hover {
  background: var(--hover);
  color: var(--txt);
}

.tabItem.active {
  background: var(--bg);
  color: var(--txt);
  font-weight: 550;
  border-color: var(--line-strong);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.tabIcon {
  display: inline-flex;
  font-size: 13px;
  opacity: 0.85;
}
.tabItem.active .tabIcon {
  color: var(--accent);
  opacity: 1;
}

.tabTitle {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0.01em;
}

/* 关闭按钮 */
.tabClose {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 2px;
  margin-right: -4px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--dim);
  cursor: pointer;
  opacity: 0.7;
  transition: all 0.12s;
}

.tabClose:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  opacity: 1;
}

/* 标签栏操作 */
.tabsActions {
  flex: none;
  padding-left: 6px;
  margin-left: 4px;
  border-left: 1px solid var(--line);
}

.actionBtn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s;
}
.actionBtn:hover {
  background: var(--hover);
  color: var(--txt);
  border-color: var(--line);
}

/* 右键悬浮菜单 */
.contextMenu {
  position: fixed;
  z-index: 1000;
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 4px;
  min-width: 120px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.ctxItem {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--txt);
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.12s;
}
.ctxItem:hover {
  background: var(--hover);
  color: var(--accent);
}
</style>
