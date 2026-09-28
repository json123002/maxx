<script setup>
/* ===== 设置中心：顶级现代金融终端偏好与系统设置 Hub =====
   设计理念参考 Codex / Linear / Apple System Settings：
   - 首页即信息聚合看板：分类卡片中各项显示当前生效状态、参数与预览摘要；
   - 渐进式详情披露：点击具体设置项即呼出专属抽屉 (Slide Drawer) 或聚焦弹窗；
   - 支持 URL 参数 ?open=qsource | blacklist | hotkeys | security 快速直达。 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import {
  ApiOutlined,
  StopOutlined,
  ThunderboltOutlined,
  LineChartOutlined,
  SlidersOutlined,
  BgColorsOutlined,
  SafetyCertificateOutlined,
  KeyOutlined,
  LogoutOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  PlusOutlined,
  RightOutlined,
  CloseOutlined,
  GlobalOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  DeleteOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";

import { api } from "../api/client";
import { blackState, removeBlack } from "../stores/blacklist";
import { authState, logout } from "../stores/auth";
import { themeMode, toggleTheme } from "../utils/theme";
import ConfirmModal from "../components/ConfirmModal.vue";
import PwdModal from "../layout/PwdModal.vue";

const route = useRoute();
const router = useRouter();

/* ========================================================
   抽屉与弹窗状态控制
   ======================================================== */
const quoteDrawerOpen = ref(false);
const blackDrawerOpen = ref(false);
const hotkeysModalOpen = ref(false);
const pwdOpen = ref(false);

function openDrawer(type) {
  if (type === "qsource") quoteDrawerOpen.value = true;
  else if (type === "blacklist") blackDrawerOpen.value = true;
  else if (type === "hotkeys") hotkeysModalOpen.value = true;
  else if (type === "security") pwdOpen.value = true;
}

// 监听 URL 快速唤起
watch(
  () => route.query.open || route.query.tab,
  (val) => {
    if (val === "qsource") quoteDrawerOpen.value = true;
    else if (val === "blacklist") blackDrawerOpen.value = true;
    else if (val === "preferences" || val === "hotkeys") hotkeysModalOpen.value = true;
    else if (val === "security") pwdOpen.value = true;
  },
  { immediate: true }
);

// Esc 快捷关闭抽屉与弹窗
function handleGlobalKeydown(e) {
  if (e.key === "Escape") {
    if (quoteDrawerOpen.value) quoteDrawerOpen.value = false;
    else if (blackDrawerOpen.value) blackDrawerOpen.value = false;
    else if (hotkeysModalOpen.value) hotkeysModalOpen.value = false;
  }
}
onMounted(() => window.addEventListener("keydown", handleGlobalKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", handleGlobalKeydown));

/* ========================================================
   模块 1: 行情数据源设置
   ======================================================== */
const PROVIDER_LABEL = { mairui: "麦蕊智数" };
const APPLY_URL = "https://mairui.club/packs";

const rows = ref([]);
const publicList = ref([]);
const loading = ref(false);

const activeSource = computed(() => rows.value.find((r) => r.enabled));
const activeSourceName = computed(() => {
  if (activeSource.value) return activeSource.value.name;
  if (publicList.value && publicList.value.length > 0) return `公共共享源 (${publicList.value[0]})`;
  return "系统默认 (东财快照兜底)";
});

async function load() {
  loading.value = true;
  try {
    const d = await api("/api/quotesettings");
    rows.value = d.rows || [];
    publicList.value = d.public || [];
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "行情源加载失败");
  } finally {
    loading.value = false;
  }
}

const form = reactive({ name: "", provider: "mairui", licence: "" });
const saving = ref(false);

async function add() {
  if (!form.name.trim()) return message.warning("请填写配置标识名称");
  if (!form.licence.trim()) return message.warning("请填写证书编号 Licence");
  saving.value = true;
  try {
    await api("/api/quotesettings", {
      method: "POST",
      body: {
        name: form.name.trim(),
        provider: form.provider,
        licence: form.licence.trim(),
      },
    });
    message.success("已添加" + (rows.value.length ? "" : "并自动启用该行情源"));
    form.name = "";
    form.licence = "";
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  } finally {
    saving.value = false;
  }
}

const reveal = reactive({});
function mask(l) {
  return l && l.length > 10 ? l.slice(0, 4) + "••••••••" + l.slice(-4) : "••••••••";
}

const togglings = reactive({});
async function toggle(r) {
  togglings[r.id] = true;
  try {
    await api("/api/quotesettings/" + r.id, {
      method: "PATCH",
      body: { enabled: !r.enabled },
    });
    if (!r.enabled) message.success("已启用「" + r.name + "」，首页自选行情改走该数据源");
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  } finally {
    togglings[r.id] = false;
  }
}

async function togglePublic(r) {
  try {
    await api("/api/quotesettings/" + r.id, {
      method: "PATCH",
      body: { is_public: !r.is_public },
    });
    if (!r.is_public) {
      message.success("已公开「" + r.name + "」：未配置个人源的用户也可共享加速");
    }
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

const tests = reactive({});
async function test(r) {
  tests[r.id] = { loading: true, ok: null, text: "" };
  try {
    const d = await api("/api/quotesettings/" + r.id + "/test", { method: "POST" });
    tests[r.id] = d.ok
      ? { loading: false, ok: true, text: `通 · ${d.latency_ms}ms · 平安银行 ${d.sample.p} (${d.sample.pc}%)` }
      : { loading: false, ok: false, text: d.error || "测试失败" };
  } catch (err) {
    tests[r.id] = {
      loading: false,
      ok: false,
      text: err.message === "unauthorized" ? "" : (err.message || "测试失败"),
    };
  }
}

const rmState = reactive({ open: false, row: null, loading: false });
async function remove() {
  const r = rmState.row;
  if (!r) return;
  rmState.loading = true;
  try {
    await api("/api/quotesettings/" + r.id, { method: "DELETE" });
    rmState.open = false;
    message.success("已删除「" + r.name + "」");
    load();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "删除失败");
  } finally {
    rmState.loading = false;
  }
}

/* ========================================================
   模块 2: 股票黑名单管理
   ======================================================== */
const blRows = ref([]);
const blLoading = ref(false);
const blCode = ref("");
const blSaving = ref(false);
const blSearchQuery = ref("");

const filteredBlRows = computed(() => {
  const q = blSearchQuery.value.trim().toLowerCase();
  if (!q) return blRows.value;
  return blRows.value.filter(
    (r) => (r.code && r.code.includes(q)) || (r.name && r.name.toLowerCase().includes(q))
  );
});

async function loadBlack() {
  blLoading.value = true;
  try {
    const d = await api("/api/blacklist");
    blRows.value = d.rows || [];
    blackState.codes = new Set(blRows.value.map((r) => r.code));
    blackState.loaded = true;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "黑名单加载失败");
  } finally {
    blLoading.value = false;
  }
}

async function addBl() {
  const code = blCode.value.trim();
  if (!/^\d{6}$/.test(code)) return message.warning("请输入合法的 6 位股票代码");
  blSaving.value = true;
  try {
    await api("/api/blacklist", { method: "POST", body: { code } });
    message.success(`已加入黑名单 (${code})，各类选股策略将自动屏蔽该股`);
    blCode.value = "";
    loadBlack();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "添加失败");
  } finally {
    blSaving.value = false;
  }
}

const blRm = reactive({ open: false, row: null, loading: false });
async function removeBl() {
  const r = blRm.row;
  if (!r) return;
  blRm.loading = true;
  try {
    await removeBlack(r.code);
    blRm.open = false;
    message.success(`已移出黑名单 ${r.name || r.code}，下次查询恢复展示`);
    loadBlack();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  } finally {
    blRm.loading = false;
  }
}

/* ========================================================
   模块 3: 账号与安全
   ======================================================== */
const roleText = computed(() => {
  if (authState.user?.root) return "超级管理员 (Root)";
  if (authState.user?.role === "admin") return "系统管理员";
  return "普通量化用户";
});

function handleLogout() {
  logout();
  router.push("/login");
  message.success("已安全退出登录");
}

onMounted(() => {
  load();
  loadBlack();
});
</script>

<template>
  <div class="setHub">
    <!-- 顶部标题与快速概览 -->
    <header class="setHubHeader">
      <div class="headerLeft">
        <h1 class="hubTitle">系统偏好与设置</h1>
        <p class="hubSub">
          集中管理行情数据通道、全市场黑名单策略、金融终端看盘交互与账户凭据安全。
        </p>
      </div>
      <div class="headerRight">
        <button class="refreshBtn" :disabled="loading || blLoading" @click="load(); loadBlack();">
          <ReloadOutlined :spin="loading || blLoading" />
          <span>同步配置</span>
        </button>
      </div>
    </header>

    <!-- 设置分类卡片列表 (Codex / Apple Settings 模式) -->
    <div class="hubBody">
      <!-- 分组 1: 行情数据与接口通道 -->
      <section class="groupSection">
        <div class="groupTitle">
          <span>行情数据与接入通道</span>
          <span class="groupTag">Data Feeds & APIs</span>
        </div>

        <div class="settingCard">
          <!-- 行情数据源设置行 -->
          <div class="settingRow clickable" @click="openDrawer('qsource')">
            <div class="rowIconBox quoteIcon">
              <ApiOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>第三方高速行情源 (API Channels)</span>
                <span v-if="activeSource" class="statusPill online">
                  <span class="pulsingDot"></span> 生效中
                </span>
                <span v-else class="statusPill standby">系统快照兜底</span>
              </div>
              <div class="rowDesc">
                直连麦蕊智数等第三方毫秒级盘口。异常或未配置时自动三级兜底回落至全市场东财快照。
              </div>
            </div>
            <div class="rowMeta">
              <span class="metaValue">{{ activeSourceName }}</span>
              <span v-if="rows.length" class="metaCountBadge">{{ rows.length }} 个已配置</span>
              <button class="entryBtn" title="打开行情源管理">
                <span>管理</span>
                <RightOutlined class="arrowIcon" />
              </button>
            </div>
          </div>

          <!-- 全站公共共享行情池 -->
          <div class="settingRow clickable" @click="openDrawer('qsource')">
            <div class="rowIconBox globalIcon">
              <GlobalOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>公共共享行情池</span>
              </div>
              <div class="rowDesc">
                全站管理员与用户主动共享的行情通道，未配置私有凭证的用户可自动接入加速。
              </div>
            </div>
            <div class="rowMeta">
              <span class="metaValue">
                {{ publicList.length ? `${publicList.length} 个公共源在线` : "未启用公共源" }}
              </span>
              <RightOutlined class="arrowIcon" />
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 2: 选股策略与过滤规则 -->
      <section class="groupSection">
        <div class="groupTitle">
          <span>策略选股与过滤规则</span>
          <span class="groupTag">Screening & Filter Rules</span>
        </div>

        <div class="settingCard">
          <!-- 股票黑名单行 -->
          <div class="settingRow clickable" @click="openDrawer('blacklist')">
            <div class="rowIconBox blacklistIcon">
              <StopOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>全局股票黑名单 (Stock Blacklist)</span>
                <span v-if="blRows.length" class="statusPill warning">{{ blRows.length }} 只屏蔽中</span>
                <span v-else class="statusPill clean">全市场扫描</span>
              </div>
              <div class="rowDesc">
                被屏蔽的目标标的将在换手率筛选、连板天梯及策略榜单中被服务端永久剔除。
              </div>
            </div>
            <div class="rowMeta">
              <span class="metaValue">{{ blRows.length ? `已录入 ${blRows.length} 只标的` : "黑名单为空" }}</span>
              <button class="entryBtn" title="打开黑名单管理">
                <span>管理名单</span>
                <RightOutlined class="arrowIcon" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 3: 终端交互与图表偏好 -->
      <section class="groupSection">
        <div class="groupTitle">
          <span>终端交互与图表引擎</span>
          <span class="groupTag">Terminal & Charting Engine</span>
        </div>

        <div class="settingCard">
          <!-- 快捷键指南行 -->
          <div class="settingRow clickable" @click="openDrawer('hotkeys')">
            <div class="rowIconBox hotkeyIcon">
              <ThunderboltOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>金融终端“极速键盘流”操作</span>
                <span class="statusPill active">已全局启用</span>
              </div>
              <div class="rowDesc">
                在工作台与筛选器表格中支持纯键盘盲操：↑ / ↓ 切股、Space 瞬间诊断、Enter 独立大图。
              </div>
            </div>
            <div class="rowMeta">
              <div class="keyPreview">
                <kbd>↑</kbd><kbd>↓</kbd><kbd>Space</kbd><kbd>Enter</kbd>
              </div>
              <button class="entryBtn">
                <span>快捷键表</span>
                <RightOutlined class="arrowIcon" />
              </button>
            </div>
          </div>

          <!-- K 线副图指标引擎 -->
          <div class="settingRow">
            <div class="rowIconBox chartIcon">
              <LineChartOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>K 线副图多指标引擎</span>
              </div>
              <div class="rowDesc">
                原生 Canvas 高性能实时计算 VOL 成交量、MACD (12,26,9) 与 KDJ (9,3,3) 指标序列。
              </div>
            </div>
            <div class="rowMeta">
              <span class="featureBadge">VOL / MACD / KDJ</span>
            </div>
          </div>

          <!-- 筛选容量 -->
          <div class="settingRow">
            <div class="rowIconBox sliderIcon">
              <SlidersOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>全市场筛选渲染容量</span>
              </div>
              <div class="rowDesc">
                单次筛选渲染上限已优化突破至 2000 只标的，杜绝截断与页面掉帧。
              </div>
            </div>
            <div class="rowMeta">
              <span class="featureBadge mono">2000 只 (流畅渲染)</span>
            </div>
          </div>

          <!-- 主题切换 -->
          <div class="settingRow">
            <div class="rowIconBox themeIcon">
              <BgColorsOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>界面外观与护眼主题</span>
              </div>
              <div class="rowDesc">
                当前模式：{{ themeMode === "dark" ? "深色暗黑终端 (Dark)" : "清爽明亮模式 (Light)" }}
              </div>
            </div>
            <div class="rowMeta">
              <button class="themeToggleBtn" @click="toggleTheme">
                {{ themeMode === "dark" ? "切换为浅色" : "切换为暗黑" }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 4: 账户凭据与安全 -->
      <section class="groupSection">
        <div class="groupTitle">
          <span>账户凭据与安全</span>
          <span class="groupTag">Account & Security</span>
        </div>

        <div class="settingCard">
          <!-- 账号与角色身份 -->
          <div class="settingRow">
            <div class="rowIconBox accountIcon">
              <SafetyCertificateOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>登录身份凭据</span>
              </div>
              <div class="rowDesc">
                已验证用户：<b class="userHighlight">{{ authState.user?.username || "当前用户" }}</b>
              </div>
            </div>
            <div class="rowMeta">
              <span class="roleBadge">{{ roleText }}</span>
            </div>
          </div>

          <!-- 风险声明确认留痕 -->
          <div class="settingRow">
            <div class="rowIconBox ackIcon">
              <CheckCircleOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>量化复盘风险免责留痕</span>
              </div>
              <div class="rowDesc">
                已留痕签署用户量化交易与回测分析风险揭示书。
              </div>
            </div>
            <div class="rowMeta">
              <span class="statusPill online">已签署留痕</span>
            </div>
          </div>

          <!-- 密码与操作 -->
          <div class="settingRow">
            <div class="rowIconBox keyIcon">
              <KeyOutlined />
            </div>
            <div class="rowMain">
              <div class="rowTitle">
                <span>登录凭证与安全操作</span>
              </div>
              <div class="rowDesc">
                定期修改密码，保障个人自选池与策略配置的安全。
              </div>
            </div>
            <div class="rowMeta actionsWrap">
              <button class="ghostBtn sm" @click="pwdOpen = true">
                <KeyOutlined /> 修改密码
              </button>
              <button class="dangerGhostBtn sm" @click="handleLogout">
                <LogoutOutlined /> 退出登录
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ========================================================
         抽屉 1: 行情数据源管理抽屉 (Slide-over Drawer)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="quoteDrawerOpen" class="drawerOverlay" @click.self="quoteDrawerOpen = false">
          <div class="drawerContainer" role="dialog" aria-modal="true" aria-label="行情数据源配置">
            <div class="drawerHeader">
              <div class="dhLeft">
                <div class="dhIcon quoteIcon"><ApiOutlined /></div>
                <div>
                  <h2 class="dhTitle">第三方行情源配置</h2>
                  <p class="dhSub">配置并管理高速行情接口，同一时刻仅启用一个源接管自选行情</p>
                </div>
              </div>
              <button class="drawerCloseBtn" @click="quoteDrawerOpen = false" aria-label="关闭">
                <CloseOutlined />
              </button>
            </div>

            <div class="drawerBody">
              <!-- 添加新行情源卡片 -->
              <div class="drawerBlock addBox">
                <div class="blockHead">
                  <span class="blockTitle"><PlusOutlined /> 添加新数据源</span>
                  <a :href="APPLY_URL" target="_blank" rel="noopener" class="helpLink">
                    申请麦蕊智数 Licence ↗
                  </a>
                </div>
                <div class="addGrid">
                  <div class="field">
                    <label>配置标识名称</label>
                    <input
                      v-model="form.name"
                      class="fInput"
                      maxlength="32"
                      placeholder="例：麦蕊主通道"
                      @keyup.enter="add"
                    />
                  </div>
                  <div class="field">
                    <label>供应商平台</label>
                    <select v-model="form.provider" class="fInput fSelect">
                      <option value="mairui">麦蕊智数 (Mairui)</option>
                    </select>
                  </div>
                  <div class="field full">
                    <label>证书编号 Licence</label>
                    <input
                      v-model="form.licence"
                      class="fInput mono"
                      maxlength="64"
                      placeholder="请输入 Licence 密匙"
                      @keyup.enter="add"
                    />
                  </div>
                </div>
                <div class="addFooter">
                  <span class="secNote">证书由服务端安全隔离存储，避免泄露</span>
                  <button class="primaryBtn" :disabled="saving" @click="add">
                    {{ saving ? "正在提交…" : "+ 确认添加" }}
                  </button>
                </div>
              </div>

              <!-- 已配置数据源列表 -->
              <div class="drawerBlock">
                <div class="blockHead">
                  <span class="blockTitle">已配置数据源 ({{ rows.length }})</span>
                  <button class="ghostBtn xs" :disabled="loading" @click="load">
                    <ReloadOutlined :spin="loading" /> 刷新状态
                  </button>
                </div>

                <div v-if="rows.length" class="sourceCardList">
                  <div
                    v-for="r in rows"
                    :key="r.id"
                    class="sourceCardItem"
                    :class="{ isActive: r.enabled }"
                  >
                    <div class="sciTop">
                      <div class="sciTitleRow">
                        <span class="sciName">{{ r.name }}</span>
                        <span v-if="r.enabled" class="statusPill online">
                          <span class="pulsingDot"></span> 实时接管中
                        </span>
                        <span v-else class="statusPill standby">备用通道</span>
                      </div>
                      <div class="sciMeta">
                        <span class="provBadge">{{ PROVIDER_LABEL[r.provider] || r.provider }}</span>
                        <span class="licCode">{{ reveal[r.id] ? r.licence : mask(r.licence) }}</span>
                        <button
                          class="licEyeBtn"
                          :title="reveal[r.id] ? '隐藏密匙' : '查看完整密匙'"
                          @click="reveal[r.id] = !reveal[r.id]"
                        >
                          <EyeInvisibleOutlined v-if="reveal[r.id]" />
                          <EyeOutlined v-else />
                        </button>
                      </div>
                    </div>

                    <!-- 测速结果通知 -->
                    <div
                      v-if="tests[r.id] && tests[r.id].text"
                      class="sciSpeedNote"
                      :class="tests[r.id].ok ? 'ok' : 'err'"
                    >
                      {{ tests[r.id].text }}
                    </div>

                    <!-- 卡片操作按钮行 -->
                    <div class="sciActions">
                      <div class="sciActionsLeft">
                        <button
                          class="ghostBtn xs"
                          :disabled="tests[r.id] && tests[r.id].loading"
                          @click="test(r)"
                        >
                          {{ tests[r.id] && tests[r.id].loading ? "测速中…" : "连通性测试" }}
                        </button>
                        <button
                          class="ghostBtn xs"
                          :class="{ isPub: r.is_public }"
                          title="公开后全站用户在未配置自身源时自动共享（他人不可见密匙）"
                          @click="togglePublic(r)"
                        >
                          {{ r.is_public ? "全站已公开" : "私有模式" }}
                        </button>
                      </div>
                      <div class="sciActionsRight">
                        <button
                          class="primaryBtn xs"
                          :class="{ isOff: r.enabled }"
                          :disabled="togglings[r.id]"
                          @click="toggle(r)"
                        >
                          {{ togglings[r.id] ? "切换中…" : r.enabled ? "停用" : "启用此源" }}
                        </button>
                        <button
                          class="dangerGhostBtn xs"
                          title="删除此配置"
                          @click="rmState.row = r; rmState.open = true"
                        >
                          <DeleteOutlined />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="!loading" class="emptyDrawerState">
                  <ApiOutlined class="emptyIcon" />
                  <p>暂无自定义行情数据源</p>
                  <span>未配置时系统默认直连全市场东财快照兜底通道，各类行情查询正常运作。</span>
                </div>

                <!-- 公共源提示 -->
                <div v-if="publicList.length" class="publicBanner">
                  <GlobalOutlined />
                  <span>当前全站共享公共源：<b>{{ publicList.join("、") }}</b>，未配置个人源时自动享受加速。</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ========================================================
         抽屉 2: 股票黑名单管理抽屉 (Slide-over Drawer)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="blackDrawerOpen" class="drawerOverlay" @click.self="blackDrawerOpen = false">
          <div class="drawerContainer" role="dialog" aria-modal="true" aria-label="股票黑名单管理">
            <div class="drawerHeader">
              <div class="dhLeft">
                <div class="dhIcon blacklistIcon"><StopOutlined /></div>
                <div>
                  <h2 class="dhTitle">股票黑名单管理</h2>
                  <p class="dhSub">屏蔽不感兴趣或风险标的，选股器与策略榜单自动全局剔除</p>
                </div>
              </div>
              <button class="drawerCloseBtn" @click="blackDrawerOpen = false" aria-label="关闭">
                <CloseOutlined />
              </button>
            </div>

            <div class="drawerBody">
              <!-- 快速录入栏 -->
              <div class="drawerBlock addBox">
                <div class="blockHead">
                  <span class="blockTitle"><PlusOutlined /> 录入新屏蔽代码</span>
                  <span class="fieldTip">亦可在换手率筛选表格最右侧一键加入</span>
                </div>
                <div class="blAddRow">
                  <input
                    v-model="blCode"
                    class="fInput mono"
                    maxlength="6"
                    inputmode="numeric"
                    placeholder="输入 6 位股票代码 (如 600519、000001)"
                    @keyup.enter="addBl"
                  />
                  <button class="primaryBtn" :disabled="blSaving" @click="addBl">
                    {{ blSaving ? "录入中…" : "+ 确认屏蔽" }}
                  </button>
                </div>
              </div>

              <!-- 搜索与列表 -->
              <div class="drawerBlock">
                <div class="blockHead">
                  <span class="blockTitle">已屏蔽标的 ({{ blRows.length }})</span>
                  <div class="blSearchWrap" v-if="blRows.length > 5">
                    <SearchOutlined class="searchIcon" />
                    <input
                      v-model="blSearchQuery"
                      class="fSearchInput"
                      placeholder="搜索代码或名称…"
                    />
                  </div>
                </div>

                <div v-if="filteredBlRows.length" class="blTableWrap">
                  <table class="blTable">
                    <thead>
                      <tr>
                        <th>代码</th>
                        <th>股票名称</th>
                        <th>加入时间</th>
                        <th class="alignRight">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in filteredBlRows" :key="r.code">
                        <td class="codeCell"><span class="codeBadge">{{ r.code }}</span></td>
                        <td class="nameCell">{{ r.name || "—" }}</td>
                        <td class="dateCell">{{ (r.created_at || "").slice(0, 10) }}</td>
                        <td class="alignRight">
                          <button
                            class="dangerGhostBtn xs"
                            @click="blRm.row = r; blRm.open = true"
                          >
                            移出
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div v-else-if="!blLoading" class="emptyDrawerState">
                  <StopOutlined class="emptyIcon" />
                  <p>{{ blSearchQuery ? "未找到匹配的黑名单标的" : "黑名单列表为空" }}</p>
                  <span>加入黑名单后，全市场选股器扫描时将永久忽略该标的。</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ========================================================
         弹窗 1: 键盘流快捷键指南弹窗 (Modern Dialog Modal)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="hotkeysModalOpen" class="modalOverlay" @click.self="hotkeysModalOpen = false">
          <div class="modalContainer hotkeyModalBox" role="dialog" aria-modal="true" aria-label="键盘流指南">
            <div class="modalHeader">
              <div class="dhLeft">
                <div class="dhIcon hotkeyIcon"><ThunderboltOutlined /></div>
                <div>
                  <h3 class="modalTitle">金融终端“极速键盘流”指南</h3>
                  <p class="dhSub">专为机构操盘与极速复盘打造的全键盘盲操体系</p>
                </div>
              </div>
              <button class="drawerCloseBtn" @click="hotkeysModalOpen = false">
                <CloseOutlined />
              </button>
            </div>

            <div class="hotkeyGrid">
              <div class="hotkeyCard">
                <div class="keyCapWrap">
                  <kbd>↑</kbd> 或 <kbd>k</kbd>
                </div>
                <div class="keyDetail">
                  <b>上一只股票</b>
                  <span>高亮选中列表中上一行标的，自动平滑聚焦</span>
                </div>
              </div>

              <div class="hotkeyCard">
                <div class="keyCapWrap">
                  <kbd>↓</kbd> 或 <kbd>j</kbd>
                </div>
                <div class="keyDetail">
                  <b>下一只股票</b>
                  <span>顺次切换至下一行标的，极速翻页扫盘</span>
                </div>
              </div>

              <div class="hotkeyCard highlightCard">
                <div class="keyCapWrap">
                  <kbd class="spaceKey">Space 空格键</kbd>
                </div>
                <div class="keyDetail">
                  <b>瞬间呼出战法分析</b>
                  <span>零延迟打开当前聚焦个股的六维量化评估弹窗</span>
                </div>
              </div>

              <div class="hotkeyCard">
                <div class="keyCapWrap">
                  <kbd>Enter 回车</kbd>
                </div>
                <div class="keyDetail">
                  <b>打开个股走势大图</b>
                  <span>在新标签页打开该股票的完整行情与多指标分时</span>
                </div>
              </div>
            </div>

            <div class="modalTip">
              💡 提示：在<b>「我的工作台」</b>与<b>「换手率筛选」</b>界面点击任意行即可开启键盘流巡航。
            </div>

            <div class="modalFooter">
              <button class="primaryBtn" @click="hotkeysModalOpen = false">我知道了</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 删除行情源二次确认 -->
    <ConfirmModal
      :open="rmState.open"
      :title="'删除行情源 ' + (rmState.row ? '「' + rmState.row.name + '」' : '')"
      :desc="rmState.row && rmState.row.enabled
        ? '该数据源正在启用中，删除后首页行情将自动回落到系统默认数据源。'
        : '删除后不可恢复。'"
      ok-text="确认删除"
      :loading="rmState.loading"
      @confirm="remove"
      @close="rmState.open = false"
    />

    <!-- 移出黑名单二次确认 -->
    <ConfirmModal
      :open="blRm.open"
      :title="'移出黑名单 ' + (blRm.row ? (blRm.row.name || '') + ' ' + blRm.row.code : '')"
      desc="移出后该股票将在换手率筛选结果中恢复正常展示。"
      ok-text="确认移出"
      :loading="blRm.loading"
      @confirm="removeBl"
      @close="blRm.open = false"
    />

    <!-- 修改密码弹窗 -->
    <PwdModal :open="pwdOpen" @close="pwdOpen = false" />
  </div>
</template>

<style scoped>
.setHub {
  max-width: 960px;
  margin: 0 auto;
  padding: 12px 0 64px;
}

/* 顶部标题区 */
.setHubHeader {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 28px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}
.hubTitle {
  font-size: 22px;
  font-weight: 750;
  letter-spacing: -0.01em;
  color: var(--txt);
  margin: 0;
}
.hubSub {
  font-size: 13px;
  color: var(--dim);
  margin: 6px 0 0;
  line-height: 1.5;
}
.refreshBtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--dim);
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}
.refreshBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
  background: var(--hover);
}

/* 分组区块 */
.hubBody {
  display: flex;
  flex-direction: column;
  gap: 28px;
}
.groupSection {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.groupTitle {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--txt);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-left: 2px;
}
.groupTag {
  font-size: 11px;
  font-weight: 500;
  color: var(--dim);
  font-family: var(--mono);
  text-transform: none;
}

/* 顶级设置卡片 (Codex / iOS 风格的分组容器) */
.settingCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* 每一行设置项 */
.settingRow {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  transition: background-color 0.15s ease, border-color 0.15s ease;
  position: relative;
}
.settingRow:last-child {
  border-bottom: none;
}
.settingRow.clickable {
  cursor: pointer;
}
.settingRow.clickable:hover {
  background: var(--hover);
}
.settingRow.clickable:hover .arrowIcon {
  transform: translateX(3px);
  color: var(--accent);
}

/* 图标容器 (苹果/Codex 扁平微发光色块) */
.rowIconBox {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 18px;
  flex-shrink: 0;
}
.quoteIcon {
  background: rgba(14, 165, 233, 0.12);
  color: #0ea5e9;
}
.globalIcon {
  background: rgba(168, 85, 247, 0.12);
  color: #a855f7;
}
.blacklistIcon {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}
.hotkeyIcon {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}
.chartIcon {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}
.sliderIcon {
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}
.themeIcon {
  background: rgba(236, 72, 153, 0.12);
  color: #ec4899;
}
.accountIcon {
  background: rgba(20, 184, 166, 0.12);
  color: #14b8a6;
}
.ackIcon {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}
.keyIcon {
  background: rgba(234, 88, 12, 0.12);
  color: #ea580c;
}

/* 主信息文案 */
.rowMain {
  flex: 1;
  min-width: 0;
}
.rowTitle {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14.5px;
  font-weight: 650;
  color: var(--txt);
}
.rowDesc {
  font-size: 12.5px;
  color: var(--dim);
  margin-top: 4px;
  line-height: 1.45;
}

/* 右侧状态与操作 */
.rowMeta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.metaValue {
  font-size: 12.5px;
  color: var(--dim);
  font-family: var(--mono);
}
.metaCountBadge {
  font-size: 11.5px;
  font-family: var(--mono);
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--dim);
  padding: 2px 8px;
  border-radius: 999px;
}
.entryBtn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.settingRow.clickable:hover .entryBtn {
  border-color: var(--accent);
  color: var(--accent);
}
.arrowIcon {
  font-size: 12px;
  color: var(--dim);
  transition: transform 0.15s ease, color 0.15s ease;
}

/* 状态药丸胶囊 */
.statusPill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
}
.statusPill.online {
  background: rgba(34, 197, 94, 0.12);
  color: var(--up);
  border: 1px solid rgba(34, 197, 94, 0.25);
}
.statusPill.active {
  background: rgba(14, 165, 233, 0.12);
  color: var(--accent);
  border: 1px solid rgba(14, 165, 233, 0.25);
}
.statusPill.standby {
  background: var(--hover);
  color: var(--dim);
  border: 1px solid var(--line);
}
.statusPill.warning {
  background: rgba(239, 68, 68, 0.12);
  color: var(--down);
  border: 1px solid rgba(239, 68, 68, 0.25);
}
.statusPill.clean {
  background: var(--hover);
  color: var(--dim);
  border: 1px solid var(--line);
}
.pulsingDot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--up);
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
}

/* 特性与角色标签 */
.featureBadge {
  font-size: 11.5px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 3px 9px;
  border-radius: 6px;
  font-weight: 500;
}
.featureBadge.mono {
  font-family: var(--mono);
}
.roleBadge {
  font-size: 12px;
  font-weight: 650;
  color: var(--accent);
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(14, 165, 233, 0.25);
  padding: 3px 10px;
  border-radius: 6px;
}
.userHighlight {
  color: var(--txt);
}

/* 快捷键微预览 */
.keyPreview {
  display: flex;
  gap: 4px;
}
.keyPreview kbd, .keyCapWrap kbd {
  background: var(--panel-2);
  border: 1px solid var(--line-strong);
  box-shadow: 0 1px 1px rgba(0,0,0,0.1);
  color: var(--txt);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  font-family: var(--mono);
}

/* 按钮风格 */
.themeToggleBtn {
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.themeToggleBtn:hover {
  border-color: var(--line-strong);
  background: var(--hover);
}

.actionsWrap {
  gap: 8px;
}
.ghostBtn {
  background: none;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ghostBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
}
.ghostBtn.sm { padding: 4px 10px; }
.ghostBtn.xs { padding: 3px 8px; font-size: 11.5px; }
.ghostBtn.isPub {
  color: var(--accent);
  border-color: rgba(14, 165, 233, 0.4);
  background: rgba(14, 165, 233, 0.08);
}

.dangerGhostBtn {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  color: var(--down);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dangerGhostBtn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.18);
}
.dangerGhostBtn.sm { padding: 4px 10px; }
.dangerGhostBtn.xs { padding: 3px 8px; font-size: 11.5px; }

.primaryBtn {
  border: none;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  color: var(--btn-txt);
  background: var(--btn-bg);
  transition: opacity 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.primaryBtn:hover:not(:disabled) { opacity: 0.88; }
.primaryBtn:disabled { opacity: 0.5; cursor: not-allowed; }
.primaryBtn.xs { padding: 3px 10px; font-size: 11.5px; }
.primaryBtn.xs.isOff {
  background: var(--panel-2);
  color: var(--dim);
  border: 1px solid var(--line);
}

/* ========================================================
   右侧滑出抽屉 (Slide-over Drawer)
   ======================================================== */
.drawerOverlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}
.drawerContainer {
  width: min(620px, 100vw);
  height: 100vh;
  background: var(--panel);
  border-left: 1px solid var(--line-strong);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.25);
}
.drawerHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}
.dhLeft {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dhIcon {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 18px;
}
.dhTitle {
  font-size: 16px;
  font-weight: 700;
  color: var(--txt);
  margin: 0;
}
.dhSub {
  font-size: 12px;
  color: var(--dim);
  margin: 3px 0 0;
}
.drawerCloseBtn {
  background: none;
  border: none;
  font-size: 15px;
  color: var(--dim);
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  transition: all 0.15s;
}
.drawerCloseBtn:hover {
  background: var(--hover);
  color: var(--txt);
}
.drawerBody {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 48px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 抽屉内区块 */
.drawerBlock {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px 18px;
}
.blockHead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.blockTitle {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--txt);
}
.helpLink {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
}
.helpLink:hover { text-decoration: underline; }
.fieldTip {
  font-size: 11.5px;
  color: var(--dim);
}

/* 表单组件 */
.fInput {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--txt);
  font-size: 13px;
  font-family: inherit;
  padding: 8px 12px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.fInput:focus { border-color: var(--accent); }
.fInput.mono { font-family: var(--mono); }
.fSelect { cursor: pointer; }

.addGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--dim);
}
.field.full { grid-column: 1 / -1; }
.addFooter {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
.secNote {
  font-size: 11.5px;
  color: var(--dim);
}

/* 行情源配置卡片列表 */
.sourceCardList {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sourceCardItem {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px 16px;
  transition: border-color 0.15s;
}
.sourceCardItem.isActive {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.sciTop {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sciTitleRow {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sciName {
  font-size: 14px;
  font-weight: 700;
  color: var(--txt);
}
.sciMeta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--dim);
}
.provBadge {
  background: var(--hover);
  padding: 1px 6px;
  border-radius: 4px;
}
.licCode { font-family: var(--mono); }
.licEyeBtn {
  background: none;
  border: none;
  padding: 0;
  color: var(--dim);
  cursor: pointer;
}
.licEyeBtn:hover { color: var(--txt); }
.sciSpeedNote {
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-family: var(--mono);
}
.sciSpeedNote.ok {
  background: rgba(34, 197, 94, 0.08);
  color: var(--up);
  border: 1px solid rgba(34, 197, 94, 0.2);
}
.sciSpeedNote.err {
  background: rgba(239, 68, 68, 0.08);
  color: var(--down);
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.sciActions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.sciActionsLeft, .sciActionsRight {
  display: flex;
  align-items: center;
  gap: 8px;
}

.publicBanner {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--panel);
  border: 1px dashed var(--line-strong);
  border-radius: 6px;
  font-size: 12px;
  color: var(--dim);
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 黑名单快速录入与表格 */
.blAddRow {
  display: flex;
  gap: 10px;
}
.blSearchWrap {
  position: relative;
  display: flex;
  align-items: center;
}
.searchIcon {
  position: absolute;
  left: 8px;
  color: var(--dim);
  font-size: 12px;
}
.fSearchInput {
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 4px 8px 4px 26px;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
}
.fSearchInput:focus { border-color: var(--accent); }

.blTableWrap {
  overflow-x: auto;
  margin-top: 8px;
}
.blTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.blTable th {
  text-align: left;
  padding: 8px 10px;
  color: var(--dim);
  font-weight: 600;
  border-bottom: 1px solid var(--line-strong);
}
.blTable td {
  padding: 10px;
  border-bottom: 1px solid var(--line);
  color: var(--txt);
}
.alignRight { text-align: right; }
.codeBadge {
  font-family: var(--mono);
  font-weight: 700;
  color: var(--accent);
  background: rgba(14, 165, 233, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}
.dateCell {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--dim);
}

.emptyDrawerState {
  text-align: center;
  padding: 32px 16px;
  color: var(--dim);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.emptyDrawerState .emptyIcon {
  font-size: 26px;
  opacity: 0.45;
  margin-bottom: 2px;
}
.emptyDrawerState p {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--txt);
  margin: 0;
}
.emptyDrawerState span {
  font-size: 12px;
  line-height: 1.4;
}

/* ========================================================
   弹窗通用样式 (Keyboard Modal 等)
   ======================================================== */
.modalOverlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modalContainer {
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  max-width: 540px;
  width: 100%;
  overflow: hidden;
}
.modalHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
}
.modalTitle {
  font-size: 16px;
  font-weight: 700;
  color: var(--txt);
  margin: 0;
}

.hotkeyGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 20px 22px;
}
.hotkeyCard {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hotkeyCard.highlightCard {
  border-color: rgba(245, 158, 11, 0.35);
  background: rgba(245, 158, 11, 0.05);
}
.keyCapWrap {
  display: flex;
  align-items: center;
  gap: 6px;
}
.keyCapWrap kbd {
  font-size: 13px;
  padding: 3px 10px;
}
.spaceKey {
  font-weight: 600;
}
.keyDetail b {
  display: block;
  font-size: 13.5px;
  color: var(--txt);
  margin-bottom: 3px;
}
.keyDetail span {
  font-size: 11.5px;
  color: var(--dim);
  line-height: 1.45;
}
.modalTip {
  margin: 0 22px 16px;
  padding: 10px 14px;
  background: var(--panel-2);
  border-radius: 8px;
  font-size: 12px;
  color: var(--dim);
  border: 1px solid var(--line);
}
.modalFooter {
  padding: 14px 22px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--line);
}

/* ========================================================
   动画效果
   ======================================================== */
.drawer-enter-active, .drawer-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-enter-active .drawerContainer {
  transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
}
.drawer-leave-active .drawerContainer {
  transition: transform 0.2s cubic-bezier(0.4, 0, 1, 1);
}
.drawer-enter-from, .drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .drawerContainer {
  transform: translateX(100%);
}
.drawer-leave-to .drawerContainer {
  transform: translateX(100%);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-active .modalContainer {
  transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease;
}
.fade-leave-active .modalContainer {
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
.fade-enter-from .modalContainer {
  transform: scale(0.96) translateY(8px);
}
.fade-leave-to .modalContainer {
  transform: scale(0.98) translateY(4px);
}

@media (max-width: 640px) {
  .setHubHeader {
    flex-direction: column;
    align-items: stretch;
  }
  .settingRow {
    flex-wrap: wrap;
    gap: 12px;
  }
  .rowMeta {
    width: 100%;
    justify-content: space-between;
  }
  .hotkeyGrid {
    grid-template-columns: 1fr;
  }
  .addGrid {
    grid-template-columns: 1fr;
  }
}
</style>
