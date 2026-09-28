<script setup>
/* ===== 系统偏好与设置中心 =====
   设计风格参考 Codex / Linear / Raycast 专业终端标准：
   1. 视觉克制高雅：统一微暗中性色阶与极简单色图标，杜绝花里胡哨的多彩大色块；
   2. 即点即响应：图表指标、筛选容量、外观主题均采用分段切换器 (Segmented Control)，即点即生效并持久化；
   3. 居中模态对话框 (Centered Modal)：替代靠右边缘抽屉，视线保持在中央视野，操作更聚焦高效。 */
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
  ReloadOutlined,
  PlusOutlined,
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
   弹窗控制 (全部升级为居中模态框，告别右侧偏斜抽屉)
   ======================================================== */
const quoteModalOpen = ref(false);
const blackModalOpen = ref(false);
const hotkeysModalOpen = ref(false);
const pwdOpen = ref(false);

function openModal(type) {
  if (type === "qsource") quoteModalOpen.value = true;
  else if (type === "blacklist") blackModalOpen.value = true;
  else if (type === "hotkeys") hotkeysModalOpen.value = true;
  else if (type === "security") pwdOpen.value = true;
}

// 监听 URL 快速唤起
watch(
  () => route.query.open || route.query.tab,
  (val) => {
    if (val === "qsource") quoteModalOpen.value = true;
    else if (val === "blacklist") blackModalOpen.value = true;
    else if (val === "preferences" || val === "hotkeys") hotkeysModalOpen.value = true;
    else if (val === "security") pwdOpen.value = true;
  },
  { immediate: true }
);

// Esc 快捷关闭弹窗
function handleGlobalKeydown(e) {
  if (e.key === "Escape") {
    if (quoteModalOpen.value) quoteModalOpen.value = false;
    else if (blackModalOpen.value) blackModalOpen.value = false;
    else if (hotkeysModalOpen.value) hotkeysModalOpen.value = false;
  }
}
onMounted(() => window.addEventListener("keydown", handleGlobalKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", handleGlobalKeydown));

/* ========================================================
   交互设置项 (分段控制器：即点即改即生效)
   ======================================================== */
// 1. K 线副图默认指标: VOL | MACD | KDJ
const currentSubInd = ref(localStorage.getItem("default_sub_indicator") || "VOL");
function setSubInd(val) {
  currentSubInd.value = val;
  localStorage.setItem("default_sub_indicator", val);
  message.success(`已设置默认副图指标为 ${val}`);
}

// 2. 筛选展示容量上限: 500 | 1000 | 2000
const currentRenderCap = ref(Number(localStorage.getItem("screener_render_cap") || 2000));
function setRenderCap(val) {
  currentRenderCap.value = val;
  localStorage.setItem("screener_render_cap", String(val));
  message.success(`已更新筛选表格渲染上限为 ${val} 只`);
}

// 3. 外观主题快速切换
function switchTheme(target) {
  if (themeMode.value !== target) {
    toggleTheme();
    message.success(`已切换为${target === "dark" ? "深色暗黑" : "清爽明亮"}模式`);
  }
}

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
  if (publicList.value && publicList.value.length > 0) return `全站公共源 (${publicList.value[0]})`;
  return "系统默认快照通道";
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
  <div class="settingsHub">
    <!-- 顶部标题栏 -->
    <header class="hubHeader">
      <div class="headerContent">
        <h1 class="headerTitle">系统偏好与设置</h1>
        <p class="headerSubtitle">
          管理实时行情数据通道、全市场策略黑名单、图表与看盘交互习惯及账户安全凭据。
        </p>
      </div>
      <button class="syncBtn" :disabled="loading || blLoading" @click="load(); loadBlack();">
        <ReloadOutlined :spin="loading || blLoading" />
        <span>刷新配置</span>
      </button>
    </header>

    <!-- 设置分组列表 -->
    <div class="hubSections">
      <!-- 分组 1: 行情数据与接入通道 -->
      <section class="settingsGroup">
        <div class="groupCaption">
          <span class="captionTitle">行情与接口通道</span>
          <span class="captionSub">Market Data & Feeds</span>
        </div>

        <div class="groupCard">
          <!-- 行情源 -->
          <div class="cardRow clickable" @click="openModal('qsource')">
            <div class="rowIcon"><ApiOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>第三方高速行情源 (API Channels)</span>
                <span v-if="activeSource" class="statusTag green">● 正在生效</span>
                <span v-else class="statusTag gray">系统快照兜底</span>
              </div>
              <div class="rowDesc">
                直连麦蕊智数第三方高频行情接口，未配置或异常时三级兜底回落至全市场东财快照。
              </div>
            </div>
            <div class="rowRight">
              <span class="rowStatusText">{{ activeSourceName }}</span>
              <button class="actionBtn" @click.stop="openModal('qsource')">配置数据源 ↗</button>
            </div>
          </div>

          <!-- 公共共享源 -->
          <div class="cardRow clickable" @click="openModal('qsource')">
            <div class="rowIcon"><GlobalOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>公共共享行情池</span>
              </div>
              <div class="rowDesc">
                全站管理员与用户主动共享的行情通道，未配置私有凭证的用户可自动接入加速。
              </div>
            </div>
            <div class="rowRight">
              <span class="rowStatusText">
                {{ publicList.length ? `${publicList.length} 个公共源在线` : "无公共源" }}
              </span>
              <button class="actionBtn" @click.stop="openModal('qsource')">查看共享 ↗</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 2: 选股策略与过滤规则 -->
      <section class="settingsGroup">
        <div class="groupCaption">
          <span class="captionTitle">策略选股与过滤规则</span>
          <span class="captionSub">Screening & Filter Rules</span>
        </div>

        <div class="groupCard">
          <div class="cardRow clickable" @click="openModal('blacklist')">
            <div class="rowIcon"><StopOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>全局股票黑名单 (Stock Blacklist)</span>
                <span v-if="blRows.length" class="statusTag red">{{ blRows.length }} 只屏蔽中</span>
                <span v-else class="statusTag gray">全市场扫描</span>
              </div>
              <div class="rowDesc">
                被屏蔽的目标标的将在换手率筛选、连板天梯及策略榜单中被服务端永久剔除。
              </div>
            </div>
            <div class="rowRight">
              <span class="rowStatusText">
                {{ blRows.length ? `已录入 ${blRows.length} 只标的` : "黑名单为空" }}
              </span>
              <button class="actionBtn" @click.stop="openModal('blacklist')">管理名单 ↗</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 3: 终端交互与图表引擎 -->
      <section class="settingsGroup">
        <div class="groupCaption">
          <span class="captionTitle">终端看盘与图表引擎</span>
          <span class="captionSub">Terminal Preferences</span>
        </div>

        <div class="groupCard">
          <!-- 极速快捷键 -->
          <div class="cardRow clickable" @click="openModal('hotkeys')">
            <div class="rowIcon"><ThunderboltOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>金融终端“极速键盘流”操作指南</span>
              </div>
              <div class="rowDesc">
                在工作台与筛选器表格中支持纯键盘盲操：↑ / ↓ 切股、Space 瞬间诊断、Enter 独立大图。
              </div>
            </div>
            <div class="rowRight">
              <button class="actionBtn" @click.stop="openModal('hotkeys')">快捷键指南 ↗</button>
            </div>
          </div>

          <!-- K 线副图默认指标切换 (即点即改) -->
          <div class="cardRow">
            <div class="rowIcon"><LineChartOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>K 线副图默认指标</span>
              </div>
              <div class="rowDesc">
                设定个股详情与技术分时副图的默认量化技术指标，点击下方按钮即时切换。
              </div>
            </div>
            <div class="rowRight">
              <div class="segGroup">
                <button
                  class="segBtn"
                  :class="{ active: currentSubInd === 'VOL' }"
                  @click="setSubInd('VOL')"
                >
                  VOL (成交量)
                </button>
                <button
                  class="segBtn"
                  :class="{ active: currentSubInd === 'MACD' }"
                  @click="setSubInd('MACD')"
                >
                  MACD 趋势
                </button>
                <button
                  class="segBtn"
                  :class="{ active: currentSubInd === 'KDJ' }"
                  @click="setSubInd('KDJ')"
                >
                  KDJ 摆动
                </button>
              </div>
            </div>
          </div>

          <!-- 筛选容量 (即点即改) -->
          <div class="cardRow">
            <div class="rowIcon"><SlidersOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>全市场筛选渲染容量上限</span>
              </div>
              <div class="rowDesc">
                设定换手率选股桌面表格的最大展示行数，大数据量扫盘时建议选用 2000 只。
              </div>
            </div>
            <div class="rowRight">
              <div class="segGroup">
                <button
                  class="segBtn"
                  :class="{ active: currentRenderCap === 500 }"
                  @click="setRenderCap(500)"
                >
                  500 只
                </button>
                <button
                  class="segBtn"
                  :class="{ active: currentRenderCap === 1000 }"
                  @click="setRenderCap(1000)"
                >
                  1000 只
                </button>
                <button
                  class="segBtn"
                  :class="{ active: currentRenderCap === 2000 }"
                  @click="setRenderCap(2000)"
                >
                  2000 只 (全量)
                </button>
              </div>
            </div>
          </div>

          <!-- 主题切换 (即点即改) -->
          <div class="cardRow">
            <div class="rowIcon"><BgColorsOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>界面外观与护眼主题</span>
              </div>
              <div class="rowDesc">
                根据看盘光线环境一键切换暗黑交易模式或高对比度浅色明亮模式。
              </div>
            </div>
            <div class="rowRight">
              <div class="segGroup">
                <button
                  class="segBtn"
                  :class="{ active: themeMode === 'light' }"
                  @click="switchTheme('light')"
                >
                  ☀️ 浅色明亮
                </button>
                <button
                  class="segBtn"
                  :class="{ active: themeMode === 'dark' }"
                  @click="switchTheme('dark')"
                >
                  🌙 深色终端
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 分组 4: 账户凭据与安全 -->
      <section class="settingsGroup">
        <div class="groupCaption">
          <span class="captionTitle">账户凭据与安全</span>
          <span class="captionSub">Account & Credentials</span>
        </div>

        <div class="groupCard">
          <!-- 账号与角色身份 -->
          <div class="cardRow">
            <div class="rowIcon"><SafetyCertificateOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>登录身份凭据</span>
              </div>
              <div class="rowDesc">
                当前登录账户：<b class="usernameHighlight">{{ authState.user?.username || "当前用户" }}</b>
              </div>
            </div>
            <div class="rowRight">
              <span class="roleTag">{{ roleText }}</span>
            </div>
          </div>

          <!-- 密码与会话操作 -->
          <div class="cardRow">
            <div class="rowIcon"><KeyOutlined /></div>
            <div class="rowBody">
              <div class="rowTitle">
                <span>登录凭证与安全退出</span>
              </div>
              <div class="rowDesc">
                修改登录密码或安全销毁当前终端会话令牌退出。
              </div>
            </div>
            <div class="rowRight">
              <button class="actionBtn" @click="pwdOpen = true">修改密码</button>
              <button class="actionBtn danger" @click="handleLogout">
                <LogoutOutlined /> 退出登录
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ========================================================
         居中弹窗 1: 行情数据源管理模态框 (Centered Modal)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="dialog">
        <div v-if="quoteModalOpen" class="modalBackdrop" @click.self="quoteModalOpen = false">
          <div class="modalBox" role="dialog" aria-modal="true" aria-label="行情数据源配置">
            <div class="modalTop">
              <div class="modalTitleBox">
                <h3 class="modalHeading">第三方行情数据源配置</h3>
                <p class="modalSubheading">配置麦蕊智数等高速接口。同一时刻仅启用一个源接管实时行情。</p>
              </div>
              <button class="closeIconBtn" @click="quoteModalOpen = false" aria-label="关闭">
                <CloseOutlined />
              </button>
            </div>

            <div class="modalScrollBody">
              <!-- 添加新行情源 -->
              <div class="formSection">
                <div class="sectionTop">
                  <span class="sectionHeading"><PlusOutlined /> 添加新数据源</span>
                  <a :href="APPLY_URL" target="_blank" rel="noopener" class="linkText">
                    前往麦蕊智数申请 Licence ↗
                  </a>
                </div>

                <div class="inputRowGrid">
                  <div class="inputField">
                    <label>配置名称</label>
                    <input
                      v-model="form.name"
                      class="textInput"
                      maxlength="32"
                      placeholder="例：麦蕊主通道"
                      @keyup.enter="add"
                    />
                  </div>
                  <div class="inputField">
                    <label>供应商平台</label>
                    <select v-model="form.provider" class="textInput select">
                      <option value="mairui">麦蕊智数 (Mairui)</option>
                    </select>
                  </div>
                  <div class="inputField full">
                    <label>证书编号 Licence</label>
                    <input
                      v-model="form.licence"
                      class="textInput mono"
                      maxlength="64"
                      placeholder="请输入 Licence 密匙"
                      @keyup.enter="add"
                    />
                  </div>
                </div>

                <div class="formSubmitRow">
                  <span class="safeNote">证书由服务端安全隔离存储，避免泄露</span>
                  <button class="confirmBtn" :disabled="saving" @click="add">
                    {{ saving ? "正在提交…" : "+ 确认添加" }}
                  </button>
                </div>
              </div>

              <!-- 已配置数据源列表 -->
              <div class="listSection">
                <div class="sectionTop">
                  <span class="sectionHeading">已配置数据源 ({{ rows.length }})</span>
                  <button class="subtleBtn xs" :disabled="loading" @click="load">
                    <ReloadOutlined :spin="loading" /> 刷新状态
                  </button>
                </div>

                <div v-if="rows.length" class="cardItemList">
                  <div
                    v-for="r in rows"
                    :key="r.id"
                    class="sourceItemCard"
                    :class="{ activeCard: r.enabled }"
                  >
                    <div class="sourceCardHeader">
                      <div class="cardNameRow">
                        <span class="sourceName">{{ r.name }}</span>
                        <span v-if="r.enabled" class="statusTag green">● 实时接管中</span>
                        <span v-else class="statusTag gray">备用通道</span>
                      </div>
                      <div class="cardLicMeta">
                        <span class="provTag">{{ PROVIDER_LABEL[r.provider] || r.provider }}</span>
                        <span class="monoLic">{{ reveal[r.id] ? r.licence : mask(r.licence) }}</span>
                        <button
                          class="eyeBtn"
                          :title="reveal[r.id] ? '隐藏密匙' : '查看完整密匙'"
                          @click="reveal[r.id] = !reveal[r.id]"
                        >
                          <EyeInvisibleOutlined v-if="reveal[r.id]" />
                          <EyeOutlined v-else />
                        </button>
                      </div>
                    </div>

                    <!-- 测速结果 -->
                    <div
                      v-if="tests[r.id] && tests[r.id].text"
                      class="speedReport"
                      :class="tests[r.id].ok ? 'ok' : 'err'"
                    >
                      {{ tests[r.id].text }}
                    </div>

                    <!-- 底部操作按钮 -->
                    <div class="sourceCardOps">
                      <div class="opsLeft">
                        <button
                          class="subtleBtn xs"
                          :disabled="tests[r.id] && tests[r.id].loading"
                          @click="test(r)"
                        >
                          {{ tests[r.id] && tests[r.id].loading ? "测速中…" : "连通性测试" }}
                        </button>
                        <button
                          class="subtleBtn xs"
                          :class="{ isPublic: r.is_public }"
                          title="公开后全站用户在未配置自身源时自动共享（他人不可见密匙）"
                          @click="togglePublic(r)"
                        >
                          {{ r.is_public ? "全站已公开" : "私有模式" }}
                        </button>
                      </div>
                      <div class="opsRight">
                        <button
                          class="confirmBtn xs"
                          :class="{ disableBtn: r.enabled }"
                          :disabled="togglings[r.id]"
                          @click="toggle(r)"
                        >
                          {{ togglings[r.id] ? "切换中…" : r.enabled ? "停用" : "启用此源" }}
                        </button>
                        <button
                          class="dangerBtn xs"
                          title="删除此配置"
                          @click="rmState.row = r; rmState.open = true"
                        >
                          <DeleteOutlined />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="!loading" class="emptyModalState">
                  <ApiOutlined class="emptyIcon" />
                  <p>暂无自定义行情数据源</p>
                  <span>系统默认直连全市场东财快照兜底通道，各类行情查询正常运作。</span>
                </div>

                <!-- 公共共享源说明 -->
                <div v-if="publicList.length" class="noticeBox">
                  <GlobalOutlined />
                  <span>当前全站可用公共共享源：<b>{{ publicList.join("、") }}</b>，未配置个人源时自动享受加速。</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ========================================================
         居中弹窗 2: 股票黑名单管理模态框 (Centered Modal)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="dialog">
        <div v-if="blackModalOpen" class="modalBackdrop" @click.self="blackModalOpen = false">
          <div class="modalBox" role="dialog" aria-modal="true" aria-label="股票黑名单管理">
            <div class="modalTop">
              <div class="modalTitleBox">
                <h3 class="modalHeading">股票黑名单管理</h3>
                <p class="modalSubheading">屏蔽不感兴趣或风险标的，选股器与策略榜单自动全局剔除。</p>
              </div>
              <button class="closeIconBtn" @click="blackModalOpen = false" aria-label="关闭">
                <CloseOutlined />
              </button>
            </div>

            <div class="modalScrollBody">
              <!-- 录入新代码 -->
              <div class="formSection">
                <div class="sectionTop">
                  <span class="sectionHeading"><PlusOutlined /> 录入新屏蔽代码</span>
                  <span class="fieldTip">亦可在换手率筛选表格最右侧一键加入</span>
                </div>
                <div class="quickAddBar">
                  <input
                    v-model="blCode"
                    class="textInput mono"
                    maxlength="6"
                    inputmode="numeric"
                    placeholder="输入 6 位股票代码 (如 600519、000001)"
                    @keyup.enter="addBl"
                  />
                  <button class="confirmBtn" :disabled="blSaving" @click="addBl">
                    {{ blSaving ? "录入中…" : "+ 确认屏蔽" }}
                  </button>
                </div>
              </div>

              <!-- 搜索与列表 -->
              <div class="listSection">
                <div class="sectionTop">
                  <span class="sectionHeading">已屏蔽标的 ({{ blRows.length }})</span>
                  <div class="searchWrap" v-if="blRows.length > 5">
                    <SearchOutlined class="searchIcon" />
                    <input
                      v-model="blSearchQuery"
                      class="searchInput"
                      placeholder="搜索代码或名称…"
                    />
                  </div>
                </div>

                <div v-if="filteredBlRows.length" class="tableWrapper">
                  <table class="dataTable">
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
                        <td class="codeCell"><span class="codePill">{{ r.code }}</span></td>
                        <td class="nameCell">{{ r.name || "—" }}</td>
                        <td class="dateCell">{{ (r.created_at || "").slice(0, 10) }}</td>
                        <td class="alignRight">
                          <button
                            class="dangerBtn xs"
                            @click="blRm.row = r; blRm.open = true"
                          >
                            移出
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div v-else-if="!blLoading" class="emptyModalState">
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
         居中弹窗 3: 键盘流快捷键指南 (Centered Modal)
         ======================================================== -->
    <Teleport to="body">
      <Transition name="dialog">
        <div v-if="hotkeysModalOpen" class="modalBackdrop" @click.self="hotkeysModalOpen = false">
          <div class="modalBox smBox" role="dialog" aria-modal="true" aria-label="键盘流指南">
            <div class="modalTop">
              <div class="modalTitleBox">
                <h3 class="modalHeading">金融终端“极速键盘流”指南</h3>
                <p class="modalSubheading">专为机构操盘与极速复盘打造的全键盘盲操体系</p>
              </div>
              <button class="closeIconBtn" @click="hotkeysModalOpen = false">
                <CloseOutlined />
              </button>
            </div>

            <div class="keyCardsGrid">
              <div class="keyCard">
                <div class="keyBadge"><kbd>↑</kbd> 或 <kbd>k</kbd></div>
                <div class="keyIntro">
                  <b>上一只股票</b>
                  <span>高亮选中列表中上一行标的，自动平滑聚焦</span>
                </div>
              </div>

              <div class="keyCard">
                <div class="keyBadge"><kbd>↓</kbd> 或 <kbd>j</kbd></div>
                <div class="keyIntro">
                  <b>下一只股票</b>
                  <span>顺次切换至下一行标的，极速翻页扫盘</span>
                </div>
              </div>

              <div class="keyCard specialCard">
                <div class="keyBadge"><kbd class="spaceKbd">Space 空格键</kbd></div>
                <div class="keyIntro">
                  <b>瞬间呼出战法分析</b>
                  <span>零延迟打开当前聚焦个股的六维量化评估弹窗</span>
                </div>
              </div>

              <div class="keyCard">
                <div class="keyBadge"><kbd>Enter 回车</kbd></div>
                <div class="keyIntro">
                  <b>打开个股走势大图</b>
                  <span>在新标签页打开该股票的完整行情与多指标分时</span>
                </div>
              </div>
            </div>

            <div class="keyModalNote">
              💡 提示：在<b>「我的工作台」</b>与<b>「换手率筛选」</b>界面点击任意行即可开启键盘流巡航。
            </div>

            <div class="modalBottom">
              <button class="confirmBtn" @click="hotkeysModalOpen = false">我知道了</button>
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
/* 页面整体布局 (Codex / Linear / Raycast 沉静风格) */
.settingsHub {
  max-width: 900px;
  margin: 0 auto;
  padding: 16px 0 64px;
}

/* 顶部标题区 */
.hubHeader {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}
.headerTitle {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--txt);
  margin: 0;
}
.headerSubtitle {
  font-size: 13px;
  color: var(--dim);
  margin: 6px 0 0;
  line-height: 1.5;
}
.syncBtn {
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
.syncBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
  background: var(--hover);
}

/* 分组区块 */
.hubSections {
  display: flex;
  flex-direction: column;
  gap: 26px;
}
.settingsGroup {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.groupCaption {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-left: 2px;
}
.captionTitle {
  font-size: 13px;
  font-weight: 700;
  color: var(--txt);
  letter-spacing: 0.02em;
}
.captionSub {
  font-size: 11px;
  color: var(--dim);
  font-family: var(--mono);
}

/* 分组白板卡片容器 */
.groupCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
}

/* 统一设置卡片行 */
.cardRow {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 15px 18px;
  border-bottom: 1px solid var(--line);
  transition: background-color 0.15s ease;
}
.cardRow:last-child {
  border-bottom: none;
}
.cardRow.clickable {
  cursor: pointer;
}
.cardRow.clickable:hover {
  background: var(--hover);
}

/* 单色极简图标 (告别多彩大色块，保持视觉专业统一) */
.rowIcon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  display: grid;
  place-items: center;
  color: var(--dim);
  font-size: 15px;
  flex-shrink: 0;
}
.cardRow.clickable:hover .rowIcon {
  color: var(--txt);
  border-color: var(--line-strong);
}

/* 主信息文案 */
.rowBody {
  flex: 1;
  min-width: 0;
}
.rowTitle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--txt);
}
.rowDesc {
  font-size: 12px;
  color: var(--dim);
  margin-top: 3px;
  line-height: 1.45;
}

/* 右侧交互区 */
.rowRight {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.rowStatusText {
  font-size: 12px;
  color: var(--dim);
  font-family: var(--mono);
}

/* 分段切换控制器 (Segmented Control，即点即响应) */
.segGroup {
  display: inline-flex;
  background: var(--panel-2);
  border: 1px solid var(--line);
  padding: 3px;
  border-radius: 8px;
  gap: 2px;
}
.segBtn {
  background: transparent;
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.segBtn:hover:not(.active) {
  color: var(--txt);
}
.segBtn.active {
  background: var(--panel);
  color: var(--txt);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

/* 统一轻量操作按钮 */
.actionBtn {
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.actionBtn:hover {
  border-color: var(--line-strong);
  background: var(--hover);
}
.actionBtn.danger {
  color: var(--down);
  border-color: rgba(239, 68, 68, 0.25);
  background: rgba(239, 68, 68, 0.06);
}
.actionBtn.danger:hover {
  background: rgba(239, 68, 68, 0.14);
}

/* 状态标签 */
.statusTag {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
}
.statusTag.green {
  background: rgba(34, 197, 94, 0.12);
  color: var(--up);
  border: 1px solid rgba(34, 197, 94, 0.25);
}
.statusTag.red {
  background: rgba(239, 68, 68, 0.12);
  color: var(--down);
  border: 1px solid rgba(239, 68, 68, 0.25);
}
.statusTag.gray {
  background: var(--hover);
  color: var(--dim);
  border: 1px solid var(--line);
}
.roleTag {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(14, 165, 233, 0.22);
  padding: 3px 8px;
  border-radius: 6px;
}
.usernameHighlight {
  color: var(--txt);
}

/* ========================================================
   居中模态对话框 (Centered Dialog Modal)
   ======================================================== */
.modalBackdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.52);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modalBox {
  width: min(640px, 94vw);
  max-height: 86vh;
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modalBox.smBox {
  width: min(540px, 94vw);
}

/* 弹窗顶部 */
.modalTop {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
}
.modalHeading {
  font-size: 16px;
  font-weight: 700;
  color: var(--txt);
  margin: 0;
}
.modalSubheading {
  font-size: 12px;
  color: var(--dim);
  margin: 4px 0 0;
}
.closeIconBtn {
  background: transparent;
  border: none;
  color: var(--dim);
  font-size: 15px;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: all 0.15s;
}
.closeIconBtn:hover {
  color: var(--txt);
  background: var(--hover);
}

/* 弹窗滚动体 */
.modalScrollBody {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px 28px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* 弹窗内部区块 */
.formSection, .listSection {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 15px 16px;
}
.sectionTop {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sectionHeading {
  font-size: 13px;
  font-weight: 700;
  color: var(--txt);
}
.linkText {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
}
.linkText:hover { text-decoration: underline; }
.fieldTip {
  font-size: 11.5px;
  color: var(--dim);
}

/* 输入框规范 */
.textInput {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--txt);
  font-size: 12.5px;
  font-family: inherit;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.textInput:focus { border-color: var(--accent); }
.textInput.mono { font-family: var(--mono); }
.textInput.select { cursor: pointer; }

.inputRowGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.inputField {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.inputField label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--dim);
}
.inputField.full { grid-column: 1 / -1; }

.formSubmitRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}
.safeNote {
  font-size: 11.5px;
  color: var(--dim);
}

/* 按钮风格 */
.confirmBtn {
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
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
.confirmBtn:hover:not(:disabled) { opacity: 0.88; }
.confirmBtn:disabled { opacity: 0.5; cursor: not-allowed; }
.confirmBtn.xs { padding: 3px 8px; font-size: 11.5px; }
.confirmBtn.xs.disableBtn {
  background: var(--panel-2);
  color: var(--dim);
  border: 1px solid var(--line);
}

.subtleBtn {
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--dim);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.subtleBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
}
.subtleBtn.xs { padding: 3px 8px; font-size: 11.5px; }
.subtleBtn.isPublic {
  color: var(--accent);
  border-color: rgba(14, 165, 233, 0.4);
  background: rgba(14, 165, 233, 0.08);
}

.dangerBtn {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  color: var(--down);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.dangerBtn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.18);
}
.dangerBtn.xs { padding: 3px 8px; font-size: 11.5px; }

/* 行情源卡片 */
.cardItemList {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sourceItemCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
}
.sourceItemCard.activeCard {
  border-color: var(--accent);
}
.sourceCardHeader {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cardNameRow {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sourceName {
  font-size: 13.5px;
  font-weight: 650;
  color: var(--txt);
}
.cardLicMeta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--dim);
}
.provTag {
  background: var(--hover);
  padding: 1px 5px;
  border-radius: 4px;
}
.monoLic { font-family: var(--mono); }
.eyeBtn {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--dim);
  cursor: pointer;
}
.eyeBtn:hover { color: var(--txt); }

.speedReport {
  margin-top: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  font-family: var(--mono);
}
.speedReport.ok {
  background: rgba(34, 197, 94, 0.08);
  color: var(--up);
  border: 1px solid rgba(34, 197, 94, 0.2);
}
.speedReport.err {
  background: rgba(239, 68, 68, 0.08);
  color: var(--down);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.sourceCardOps {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}
.opsLeft, .opsRight {
  display: flex;
  align-items: center;
  gap: 6px;
}

.noticeBox {
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
.quickAddBar {
  display: flex;
  gap: 8px;
}
.searchWrap {
  position: relative;
  display: flex;
  align-items: center;
}
.searchIcon {
  position: absolute;
  left: 8px;
  color: var(--dim);
  font-size: 11.5px;
}
.searchInput {
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--txt);
  padding: 3px 8px 3px 24px;
  border-radius: 6px;
  font-size: 11.5px;
  outline: none;
}
.searchInput:focus { border-color: var(--accent); }

.tableWrapper {
  overflow-x: auto;
  margin-top: 6px;
}
.dataTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.dataTable th {
  text-align: left;
  padding: 7px 8px;
  color: var(--dim);
  font-weight: 600;
  border-bottom: 1px solid var(--line-strong);
}
.dataTable td {
  padding: 9px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--txt);
}
.alignRight { text-align: right; }
.codePill {
  font-family: var(--mono);
  font-weight: 700;
  color: var(--accent);
  background: rgba(14, 165, 233, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
}
.dateCell {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
}

/* 快捷键弹窗内容 */
.keyCardsGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 18px 22px;
}
.keyCard {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.keyCard.specialCard {
  border-color: rgba(245, 158, 11, 0.3);
  background: rgba(245, 158, 11, 0.04);
}
.keyBadge kbd {
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 12px;
  font-family: var(--mono);
  color: var(--txt);
}
.spaceKbd { font-weight: 600; }
.keyIntro b {
  display: block;
  font-size: 13px;
  color: var(--txt);
}
.keyIntro span {
  font-size: 11.5px;
  color: var(--dim);
}
.keyModalNote {
  margin: 0 22px 14px;
  padding: 8px 12px;
  background: var(--panel-2);
  border-radius: 6px;
  font-size: 11.5px;
  color: var(--dim);
  border: 1px solid var(--line);
}
.modalBottom {
  padding: 12px 22px 16px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--line);
}

.emptyModalState {
  text-align: center;
  padding: 28px 12px;
  color: var(--dim);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.emptyModalState .emptyIcon {
  font-size: 24px;
  opacity: 0.45;
}
.emptyModalState p {
  font-size: 13px;
  font-weight: 600;
  color: var(--txt);
  margin: 0;
}
.emptyModalState span {
  font-size: 11.5px;
}

/* ========================================================
   居中模态框动画 (Dialog Scale-Fade)
   ======================================================== */
.dialog-enter-active, .dialog-leave-active {
  transition: opacity 0.2s ease;
}
.dialog-enter-active .modalBox {
  transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease;
}
.dialog-leave-active .modalBox {
  transition: transform 0.16s ease, opacity 0.16s ease;
}
.dialog-enter-from, .dialog-leave-to {
  opacity: 0;
}
.dialog-enter-from .modalBox {
  transform: scale(0.96) translateY(8px);
}
.dialog-leave-to .modalBox {
  transform: scale(0.98) translateY(4px);
}

@media (max-width: 640px) {
  .hubHeader {
    flex-direction: column;
    align-items: stretch;
  }
  .cardRow {
    flex-wrap: wrap;
    gap: 10px;
  }
  .rowRight {
    width: 100%;
    justify-content: space-between;
  }
  .keyCardsGrid {
    grid-template-columns: 1fr;
  }
  .inputRowGrid {
    grid-template-columns: 1fr;
  }
}
</style>
