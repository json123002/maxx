<script setup>
/* ===== 设置中心：行情源 / 黑名单 / 看盘偏好 / 账号安全 =====
   左侧分类导航 + 右侧独立功能面板，规范模块化架构。
   支持 URL 参数 ?tab=xxx 快捷直达对应子面板。 */
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import {
  ApiOutlined,
  StopOutlined,
  ControlOutlined,
  SafetyCertificateOutlined,
  KeyOutlined,
  LogoutOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  PlusOutlined,
} from "@ant-design/icons-vue";

import { api } from "../api/client";
import { blackState, removeBlack } from "../stores/blacklist";
import { authState, logout } from "../stores/auth";
import { themeMode, toggleTheme } from "../utils/theme";
import ConfirmModal from "../components/ConfirmModal.vue";
import PwdModal from "../layout/PwdModal.vue";

const route = useRoute();
const router = useRouter();

const VALID_TABS = ["qsource", "blacklist", "preferences", "security"];
const activeTab = ref(VALID_TABS.includes(route.query.tab) ? route.query.tab : "qsource");

watch(() => route.query.tab, (t) => {
  if (VALID_TABS.includes(t) && t !== activeTab.value) {
    activeTab.value = t;
  }
});

function setTab(t) {
  activeTab.value = t;
  router.replace({ query: { ...route.query, tab: t } });
}

/* ========================================================
   模块 1: 行情数据源设置
   ======================================================== */
const PROVIDER_LABEL = { mairui: "麦蕊智数" };
const APPLY_URL = "https://mairui.club/packs";

const rows = ref([]);
const publicList = ref([]);
const loading = ref(false);

const activeSourceCount = computed(() => rows.value.filter((r) => r.enabled).length);

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
  if (!form.name.trim()) return message.warning("请填写配置名称");
  if (!form.licence.trim()) return message.warning("请填写证书编号");
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
    message.success("已添加" + (rows.value.length ? "" : "并自动启用"));
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
    if (!r.is_public)
      message.success("已公开「" + r.name + "」：未启用自己行情源的用户也可使用");
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
      ? { loading: false, ok: true, text: "通 · " + d.latency_ms + "ms · 平安银行 " + d.sample.p + " (" + d.sample.pc + "%)" }
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
  if (!/^\d{6}$/.test(code)) return message.warning("请输入 6 位股票代码");
  blSaving.value = true;
  try {
    await api("/api/blacklist", { method: "POST", body: { code } });
    message.success("已加入黑名单，换手率筛选结果将不再显示该股");
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
    message.success(`已移出黑名单 ${r.name || r.code}，下次查询恢复显示`);
    loadBlack();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "移除失败");
  } finally {
    blRm.loading = false;
  }
}

/* ========================================================
   模块 4: 账号与安全
   ======================================================== */
const pwdOpen = ref(false);

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
  <div class="setPage">
    <!-- 顶部标题 -->
    <header class="setPageHeader">
      <div class="titleMain">
        <h2 class="setTitle">系统设置中心</h2>
        <span class="setTitleDesc">配置行情通道、筛选黑名单规则、终端看盘习惯与账户安全</span>
      </div>
    </header>

    <div class="setContainer">
      <!-- 左侧分类导航菜单 -->
      <aside class="setSidebar">
        <nav class="setNav">
          <button
            class="navItem"
            :class="{ act: activeTab === 'qsource' }"
            @click="setTab('qsource')"
          >
            <ApiOutlined class="navIcon" />
            <div class="navInfo">
              <span class="navName">行情数据源</span>
              <span class="navBrief">第三方 API · 证书配置</span>
            </div>
            <span v-if="activeSourceCount" class="activeDot" title="已启用自定义行情源"></span>
          </button>

          <button
            class="navItem"
            :class="{ act: activeTab === 'blacklist' }"
            @click="setTab('blacklist')"
          >
            <StopOutlined class="navIcon" />
            <div class="navInfo">
              <span class="navName">股票黑名单</span>
              <span class="navBrief">选股全局屏蔽名单</span>
            </div>
            <span class="navCount">{{ blRows.length }}</span>
          </button>

          <button
            class="navItem"
            :class="{ act: activeTab === 'preferences' }"
            @click="setTab('preferences')"
          >
            <ControlOutlined class="navIcon" />
            <div class="navInfo">
              <span class="navName">看盘偏好</span>
              <span class="navBrief">键盘流指南 · 图表容量</span>
            </div>
          </button>

          <button
            class="navItem"
            :class="{ act: activeTab === 'security' }"
            @click="setTab('security')"
          >
            <SafetyCertificateOutlined class="navIcon" />
            <div class="navInfo">
              <span class="navName">账号与安全</span>
              <span class="navBrief">密码修改 · 免责状态</span>
            </div>
          </button>
        </nav>
      </aside>

      <!-- 右侧独立设置面板 -->
      <main class="setContent">
        <!-- ===== 面板 1: 行情数据源 ===== -->
        <section v-if="activeTab === 'qsource'" class="panelBlock">
          <div class="panelHead">
            <div class="headTitles">
              <h3 class="panelTitle">行情数据源配置</h3>
              <p class="panelSub">
                自定义配置第三方高速行情接口（如麦蕊智数）。启用后「我的自选」与首页实时行情优先直连该源，未配置或调用失败自动三级兜底回落至系统快照。
              </p>
            </div>
            <button class="ghostBtn" :disabled="loading" @click="load">
              <ReloadOutlined :spin="loading" /> 刷新
            </button>
          </div>

          <!-- 添加行情源卡片 -->
          <div class="cardBox addSourceCard">
            <div class="cardHead">
              <span class="cardTitle"><PlusOutlined /> 添加新数据源</span>
              <span class="cardTip">
                证书编号在 <a :href="APPLY_URL" target="_blank" rel="noopener">麦蕊智数 · 我的接口</a> 页面查看
              </span>
            </div>
            <div class="addForm">
              <input
                v-model="form.name"
                class="fInput fName"
                maxlength="32"
                placeholder="配置标识（如：我的麦蕊1号）"
                @keyup.enter="add"
              />
              <select v-model="form.provider" class="fInput fProv">
                <option value="mairui">麦蕊智数</option>
              </select>
              <input
                v-model="form.licence"
                class="fInput fLic"
                maxlength="64"
                placeholder="证书编号 Licence（安全防泄露存储）"
                @keyup.enter="add"
              />
              <button class="primaryBtn" :disabled="saving" @click="add">
                {{ saving ? "添加中…" : "+ 添加配置" }}
              </button>
            </div>
          </div>

          <!-- 已配置的行情源列表 -->
          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">已配置的行情源 ({{ rows.length }})</span>
              <span class="cardTip">同一时刻仅启用一个源接管实时行情</span>
            </div>

            <div v-if="rows.length" class="sourceList">
              <div v-for="r in rows" :key="r.id" class="sourceItem" :class="{ on: r.enabled }">
                <div class="srcMain">
                  <div class="srcTop">
                    <b class="srcName">{{ r.name }}</b>
                    <span v-if="r.enabled" class="statusBadge active">
                      <span class="statusDot"></span> 实时生效中
                    </span>
                    <span v-else class="statusBadge inactive">备用闲置</span>
                  </div>
                  <div class="srcMeta">
                    <span class="srcProv">{{ PROVIDER_LABEL[r.provider] || r.provider }}</span>
                    <span class="srcLic" :class="{ rev: reveal[r.id] }">
                      {{ reveal[r.id] ? r.licence : mask(r.licence) }}
                    </span>
                    <button
                      class="linkBtn"
                      :title="reveal[r.id] ? '隐藏证书编号' : '显示证书编号'"
                      @click="reveal[r.id] = !reveal[r.id]"
                    >
                      {{ reveal[r.id] ? "隐藏" : "查看" }}
                    </button>
                  </div>
                  <div v-if="tests[r.id] && tests[r.id].text" class="testNotice" :class="tests[r.id].ok ? 'ok' : 'bad'">
                    {{ tests[r.id].text }}
                  </div>
                </div>

                <div class="srcActions">
                  <button
                    class="ghostBtn sm"
                    :disabled="tests[r.id] && tests[r.id].loading"
                    @click="test(r)"
                  >
                    {{ tests[r.id] && tests[r.id].loading ? "测速中…" : "测连通性" }}
                  </button>

                  <button
                    class="ghostBtn sm pub"
                    :class="{ isPub: r.is_public }"
                    title="公开后全站用户在未配置自身数据源时可共享此源（他人仅见名称，证书绝不外泄）"
                    @click="togglePublic(r)"
                  >
                    {{ r.is_public ? "已全站公开" : "私有仅本人" }}
                  </button>

                  <button
                    class="primaryBtn sm"
                    :class="{ act: r.enabled }"
                    :disabled="togglings[r.id]"
                    @click="toggle(r)"
                  >
                    {{ togglings[r.id] ? "切换中…" : r.enabled ? "停用" : "启用此源" }}
                  </button>

                  <button class="dangerBtn sm" title="删除该配置" @click="rmState.row = r; rmState.open = true">
                    删除
                  </button>
                </div>
              </div>
            </div>

            <div v-else-if="!loading" class="emptyState">
              <ApiOutlined class="emptyIcon" />
              <p>暂未添加任何自定义行情源</p>
              <span>未配置时默认走全市场东方财富快照通道，依然可以正常看盘。</span>
            </div>

            <!-- 公共共享行情源提示 -->
            <div v-if="publicList.length" class="publicNotice">
              <span class="pTag">全站公共源</span>
              <span>当前可用的公共共享行情源：<b>{{ publicList.join("、") }}</b>。若未启用个人源，将自动享受公共源加速。</span>
            </div>
          </div>
        </section>

        <!-- ===== 面板 2: 股票黑名单 ===== -->
        <section v-else-if="activeTab === 'blacklist'" class="panelBlock">
          <div class="panelHead">
            <div class="headTitles">
              <h3 class="panelTitle">股票黑名单管理</h3>
              <p class="panelSub">
                被加入黑名单的标的将在「换手率筛选」与各类策略榜单中被服务端永久过滤剔除，直至手动移出。
              </p>
            </div>
            <button class="ghostBtn" :disabled="blLoading" @click="loadBlack">
              <ReloadOutlined :spin="blLoading" /> 刷新
            </button>
          </div>

          <!-- 添加黑名单输入栏 -->
          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle"><PlusOutlined /> 快速录入黑名单</span>
              <span class="cardTip">亦可在换手率筛选表格每行最右侧「⋯」菜单中直接加入</span>
            </div>
            <div class="blAddForm">
              <input
                v-model="blCode"
                class="fInput fCode"
                maxlength="6"
                inputmode="numeric"
                placeholder="输入 6 位股票代码（如：600519、000001）"
                @keyup.enter="addBl"
              />
              <button class="primaryBtn" :disabled="blSaving" @click="addBl">
                {{ blSaving ? "加入中…" : "+ 确认屏蔽" }}
              </button>
            </div>
          </div>

          <!-- 黑名单列表展示 -->
          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">已屏蔽股票列表 ({{ blRows.length }})</span>
              <span class="cardTip">仅隔离当前账户，不影响其他用户</span>
            </div>

            <div v-if="blRows.length" class="blTableWrap">
              <table class="blTable">
                <thead>
                  <tr>
                    <th>股票代码</th>
                    <th>名称</th>
                    <th>屏蔽加入时间</th>
                    <th class="r">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in blRows" :key="r.code">
                    <td class="blMono">{{ r.code }}</td>
                    <td class="blName"><b>{{ r.name || "—" }}</b></td>
                    <td class="blDate">{{ (r.created_at || "").slice(0, 19).replace("T", " ") }}</td>
                    <td class="r">
                      <button class="ghostBtn sm danger" @click="blRm.row = r; blRm.open = true">
                        移出黑名单
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else-if="!blLoading" class="emptyState">
              <StopOutlined class="emptyIcon" />
              <p>黑名单列表为空</p>
              <span>遇到不想关注的爆雷股或杂毛标的时，可将其加入黑名单避免干扰复盘。</span>
            </div>
          </div>
        </section>

        <!-- ===== 面板 3: 看盘与偏好设置 ===== -->
        <section v-else-if="activeTab === 'preferences'" class="panelBlock">
          <div class="panelHead">
            <div class="headTitles">
              <h3 class="panelTitle">终端看盘与偏好</h3>
              <p class="panelSub">
                设置专属交互习惯，涵盖专业金融终端极速快捷键、全市场选股渲染容量与 K 线图表默认状态。
              </p>
            </div>
          </div>

          <!-- 快捷键指南 -->
          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">⌨️ 金融终端“极速键盘流”快捷键</span>
              <span class="cardTip">在「我的工作台」或「换手率筛选」界面全局生效</span>
            </div>
            <div class="shortcutGrid">
              <div class="scItem">
                <div class="scKeys"><kbd>↑</kbd> 或 <kbd>k</kbd></div>
                <div class="scInfo"><b>上移切换股票</b><span>在列表中选中上一只标的并平滑聚焦</span></div>
              </div>
              <div class="scItem">
                <div class="scKeys"><kbd>↓</kbd> 或 <kbd>j</kbd></div>
                <div class="scInfo"><b>下移切换股票</b><span>在列表中选中下一只标的</span></div>
              </div>
              <div class="scItem">
                <div class="scKeys"><kbd>Space</kbd> 空格</div>
                <div class="scInfo"><b>战法分析秒开</b><span>一键呼出当前股票的六维量化评估弹窗</span></div>
              </div>
              <div class="scItem">
                <div class="scKeys"><kbd>Enter</kbd> 回车</div>
                <div class="scInfo"><b>个股详情新标签</b><span>在新标签页打开该股行情走势与技术图表</span></div>
              </div>
            </div>
          </div>

          <!-- 界面与渲染偏好 -->
          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">🖥️ 渲染与主题偏好</span>
            </div>
            <div class="prefList">
              <div class="prefItem">
                <div class="prefDesc">
                  <b>筛选页表格最大渲染条数</b>
                  <span>已优化突破至 2000 只股票流畅展示，避免大数据量下的页面截断</span>
                </div>
                <span class="prefValTag">2000 条 (已启用)</span>
              </div>

              <div class="prefItem">
                <div class="prefDesc">
                  <b>K 线图副图多指标引擎</b>
                  <span>支持原生 Canvas 无缝切换成交量 VOL、MACD (12,26,9) 与 KDJ (9,3,3)</span>
                </div>
                <span class="prefValTag">VOL / MACD / KDJ</span>
              </div>

              <div class="prefItem">
                <div class="prefDesc">
                  <b>日 K 周期阶段识别算法</b>
                  <span>自动标记横盘整理、突破站稳、触底反弹与均线多头趋势段</span>
                </div>
                <span class="prefValTag">双向回放防未来函数</span>
              </div>

              <div class="prefItem">
                <div class="prefDesc">
                  <b>深浅外观主题</b>
                  <span>跟随系统或自定义切换深色/浅色护眼配色</span>
                </div>
                <button class="ghostBtn sm" @click="toggleTheme">
                  切换为 {{ themeMode === 'dark' ? '浅色模式' : '暗黑模式' }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- ===== 面板 4: 账号与安全 ===== -->
        <section v-else-if="activeTab === 'security'" class="panelBlock">
          <div class="panelHead">
            <div class="headTitles">
              <h3 class="panelTitle">账户凭据与安全</h3>
              <p class="panelSub">查看当前账户角色权限、管理访问凭证与风险声明确认留痕。</p>
            </div>
          </div>

          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">用户信息与身份</span>
            </div>
            <div class="accountGrid">
              <div class="accItem">
                <span class="accLabel">登录用户名</span>
                <span class="accValue"><b>{{ authState.user?.username || "未知" }}</b></span>
              </div>
              <div class="accItem">
                <span class="accLabel">角色权限</span>
                <span class="accValue role">
                  {{ authState.user?.root ? "超级管理员 (Root)" : authState.user?.role === "admin" ? "管理员" : "普通用户" }}
                </span>
              </div>
              <div class="accItem">
                <span class="accLabel">风险声明确认</span>
                <span class="accValue ack">
                  <CheckCircleOutlined style="color:var(--up)" />
                  {{ authState.user?.risk_ack_at ? '已确认 (' + authState.user.risk_ack_at.slice(0, 10) + ')' : '已确认' }}
                </span>
              </div>
            </div>
          </div>

          <div class="cardBox">
            <div class="cardHead">
              <span class="cardTitle">登录口令与安全操作</span>
            </div>
            <div class="secActions">
              <button class="primaryBtn" @click="pwdOpen = true">
                <KeyOutlined /> 修改登录密码
              </button>
              <button class="dangerBtn" @click="handleLogout">
                <LogoutOutlined /> 安全退出登录
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>

    <!-- 删除行情源二次确认 -->
    <ConfirmModal
      :open="rmState.open"
      :title="'删除行情源 ' + (rmState.row ? '「' + rmState.row.name + '」' : '')"
      :desc="rmState.row && rmState.row.enabled
        ? '该数据源正在启用中，删除后首页自选行情将自动回落到系统默认数据源。'
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
      desc="移出后该股票将重新恢复出现在换手率筛选结果中（下次查询生效）。"
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
.setPage {
  padding: 8px 0 48px;
}

/* 顶部标题栏 */
.setPageHeader {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);
}
.setTitle {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: .02em;
  color: var(--txt);
  margin: 0;
}
.setTitleDesc {
  color: var(--dim);
  font-size: 13px;
  margin-top: 4px;
  display: block;
}

/* 整体两栏布局 */
.setContainer {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

@media (max-width: 860px) {
  .setContainer {
    grid-template-columns: 1fr;
  }
}

/* ===== 左侧导航栏 ===== */
.setSidebar {
  position: sticky;
  top: 16px;
}
.setNav {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 8px;
}

@media (max-width: 860px) {
  .setNav {
    flex-direction: row;
    overflow-x: auto;
    border-radius: 8px;
  }
}

.navItem {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: all .15s ease;
  position: relative;
}
.navItem:hover {
  background: var(--hover);
}
.navItem.act {
  background: var(--panel-2);
  border-color: var(--line-strong);
}
.navItem.act .navName {
  color: var(--accent);
  font-weight: 700;
}
.navIcon {
  font-size: 17px;
  color: var(--dim);
  flex-shrink: 0;
}
.navItem.act .navIcon {
  color: var(--accent);
}
.navInfo {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.navName {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--txt);
}
.navBrief {
  font-size: 11px;
  color: var(--dim);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.navCount {
  font-size: 11px;
  font-family: var(--mono);
  background: var(--hover);
  color: var(--dim);
  border-radius: 999px;
  padding: 2px 7px;
  border: 1px solid var(--line);
}
.activeDot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--up);
  box-shadow: 0 0 0 3px rgba(32, 178, 130, 0.2);
}

/* ===== 右侧面板通用 ===== */
.setContent {
  min-width: 0;
}
.panelBlock {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.panelHead {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.panelTitle {
  font-size: 16px;
  font-weight: 700;
  color: var(--txt);
  margin: 0;
}
.panelSub {
  font-size: 12.5px;
  color: var(--dim);
  margin: 4px 0 0;
  line-height: 1.6;
}

/* 卡片容器 */
.cardBox {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px 20px;
}
.cardHead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.cardTitle {
  font-size: 14px;
  font-weight: 650;
  color: var(--txt);
}
.cardTip {
  font-size: 12px;
  color: var(--dim);
}
.cardTip a {
  color: var(--accent);
}

/* 通用输入与按钮 */
.fInput {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--txt);
  font-size: 13px;
  font-family: inherit;
  padding: 9px 12px;
  outline: none;
  transition: border-color .15s;
}
.fInput:focus {
  border-color: var(--accent);
}
.primaryBtn {
  border: none;
  border-radius: 8px;
  padding: 9px 18px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  color: var(--btn-txt);
  background: var(--btn-bg);
  transition: opacity .15s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.primaryBtn:hover:not(:disabled) {
  opacity: .88;
}
.primaryBtn:disabled {
  opacity: .5;
  cursor: not-allowed;
}
.primaryBtn.sm {
  padding: 4px 12px;
  font-size: 12px;
}
.primaryBtn.sm.act {
  background: var(--line-strong);
  color: var(--dim);
}

.ghostBtn {
  background: none;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 5px 14px;
  font-size: 12px;
  font-family: inherit;
  color: var(--dim);
  cursor: pointer;
  transition: all .15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ghostBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
}
.ghostBtn.sm {
  padding: 4px 10px;
}
.ghostBtn.sm.danger:hover {
  color: var(--down);
  border-color: var(--down);
}
.dangerBtn {
  background: rgba(235, 77, 75, 0.1);
  border: 1px solid rgba(235, 77, 75, 0.3);
  color: var(--down);
  border-radius: 8px;
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dangerBtn:hover {
  background: rgba(235, 77, 75, 0.2);
}
.dangerBtn.sm {
  padding: 4px 10px;
  font-size: 12px;
}

/* 行情源表单 */
.addForm {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.fName { flex: 1.2; min-width: 140px; }
.fProv { flex: 0.8; min-width: 110px; cursor: pointer; }
.fLic { flex: 2; min-width: 200px; font-family: var(--mono); }

/* 行情源列表卡片 */
.sourceList {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sourceItem {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  transition: border-color .15s;
}
.sourceItem.on {
  border-color: var(--accent);
}
.srcMain {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}
.srcTop {
  display: flex;
  align-items: center;
  gap: 10px;
}
.srcName {
  font-size: 14px;
  color: var(--txt);
}
.statusBadge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.statusBadge.active {
  background: rgba(32, 178, 130, 0.12);
  color: var(--up);
  border: 1px solid rgba(32, 178, 130, 0.3);
  font-weight: 600;
}
.statusBadge.inactive {
  background: var(--hover);
  color: var(--dim);
}
.statusDot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--up);
}
.srcMeta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--dim);
}
.srcLic {
  font-family: var(--mono);
}
.linkBtn {
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  text-decoration: underline;
}
.srcActions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.testNotice {
  font-size: 11.5px;
  font-family: var(--mono);
  margin-top: 4px;
}
.testNotice.ok { color: var(--up); }
.testNotice.bad { color: var(--down); }
.publicNotice {
  margin-top: 14px;
  padding: 10px 14px;
  background: var(--panel-2);
  border: 1px dashed var(--line-strong);
  border-radius: 8px;
  font-size: 12px;
  color: var(--dim);
  display: flex;
  align-items: center;
  gap: 8px;
}
.pTag {
  background: var(--line);
  color: var(--txt);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

/* 黑名单表单与表格 */
.blAddForm {
  display: flex;
  gap: 10px;
}
.fCode {
  flex: 1;
  max-width: 320px;
  font-family: var(--mono);
}
.blTableWrap {
  overflow-x: auto;
}
.blTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.blTable th {
  text-align: left;
  padding: 10px 12px;
  color: var(--dim);
  font-weight: 500;
  border-bottom: 1px solid var(--line-strong);
  font-size: 12px;
}
.blTable td {
  padding: 12px;
  border-bottom: 1px solid var(--line);
  color: var(--txt);
}
.blTable th.r, .blTable td.r {
  text-align: right;
}
.blMono {
  font-family: var(--mono);
  color: var(--accent);
  font-weight: 600;
}
.blDate {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--dim);
}

/* 看盘偏好卡片 */
.shortcutGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.scItem {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.scKeys kbd {
  background: var(--panel);
  border: 1px solid var(--line-strong);
  box-shadow: 0 1px 1px rgba(0,0,0,0.15);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  font-family: var(--mono);
  color: var(--txt);
}
.scInfo b {
  display: block;
  font-size: 13px;
  color: var(--txt);
  margin-bottom: 2px;
}
.scInfo span {
  font-size: 11.5px;
  color: var(--dim);
  line-height: 1.4;
}

.prefList {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.prefItem {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}
.prefItem:last-child {
  border-bottom: none;
}
.prefDesc b {
  display: block;
  font-size: 13.5px;
  color: var(--txt);
}
.prefDesc span {
  font-size: 12px;
  color: var(--dim);
}
.prefValTag {
  font-size: 12px;
  font-family: var(--mono);
  background: var(--panel-2);
  border: 1px solid var(--line);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--dim);
}

/* 账号与安全卡片 */
.accountGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}
.accItem {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.accLabel {
  font-size: 12px;
  color: var(--dim);
}
.accValue {
  font-size: 14px;
  color: var(--txt);
}
.accValue.role {
  color: var(--accent);
  font-weight: 600;
}
.accValue.ack {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.secActions {
  display: flex;
  gap: 12px;
}

/* 空状态 */
.emptyState {
  padding: 36px 0;
  text-align: center;
  color: var(--dim);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.emptyIcon {
  font-size: 28px;
  opacity: .5;
  margin-bottom: 4px;
}
.emptyState p {
  font-size: 14px;
  font-weight: 600;
  color: var(--txt);
  margin: 0;
}
.emptyState span {
  font-size: 12px;
}
</style>
