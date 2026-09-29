<script setup>
/* ===== 预警中心:规则管理 + 触发记录 =====
   评估在服务端随快照节拍(约 3 分钟)进行;本页只管规则 CRUD 与事件历史。
   浏览器通知权限需用户手势触发,故放在横幅按钮里请求。 */
import { onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { api, track } from "../api/client";
import { fmtN } from "../utils/format";
import StockSearchInput from "../components/StockSearchInput.vue";
import { alertState, requestNotifyPermission, markAllRead } from "../stores/alerts";

const RULE_TYPES = [
  { k: "price_above", name: "价格 ≥", unit: "元" },
  { k: "price_below", name: "价格 ≤", unit: "元" },
  { k: "pct_above", name: "涨幅 ≥", unit: "%" },
  { k: "pct_below", name: "跌幅 ≤", unit: "%" },
  { k: "turnover_above", name: "换手率 ≥", unit: "%" },
  { k: "volratio_above", name: "量比 ≥", unit: "" },
  { k: "limit_up", name: "封涨停", unit: "" },
  { k: "limit_open", name: "涨停开板", unit: "" },
];
const typeName = (k) => (RULE_TYPES.find(t => t.k === k) || {}).name || k;
const noThreshold = (k) => k === "limit_up" || k === "limit_open";

/* ---------- 规则 ---------- */
const rules = ref([]);
const rulesLoading = ref(false);
const showCreate = ref(false);
const creating = ref(false);
const form = ref({ code: "", name: "", rule_type: "price_above", threshold: null, cooldown_min: 60 });

async function loadRules() {
  rulesLoading.value = true;
  try {
    rules.value = (await api("/api/alerts/rules")).rows;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    rulesLoading.value = false;
  }
}

function onPick(s) {
  form.value.code = s.code;
  form.value.name = s.name;
}

async function createRule() {
  const f = form.value;
  if (!f.code) { message.warning("请先搜索选择股票"); return; }
  if (!noThreshold(f.rule_type) && (f.threshold === null || f.threshold === "")) {
    message.warning("请填写阈值"); return;
  }
  creating.value = true;
  try {
    await api("/api/alerts/rules", {
      method: "POST",
      body: {
        code: f.code, rule_type: f.rule_type,
        threshold: noThreshold(f.rule_type) ? null : +f.threshold,
        cooldown_min: +f.cooldown_min || 60,
      },
    });
    message.success(`已创建:${f.name} ${typeName(f.rule_type)}`);
    showCreate.value = false;
    form.value = { code: "", name: "", rule_type: "price_above", threshold: null, cooldown_min: 60 };
    loadRules();
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

async function toggleRule(r) {
  try {
    await api(`/api/alerts/rules/${r.id}`, { method: "PATCH", body: { enabled: !r.enabled } });
    r.enabled = r.enabled ? 0 : 1;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "操作失败");
  }
}

async function removeRule(r) {
  try {
    await api(`/api/alerts/rules/${r.id}`, { method: "DELETE" });
    rules.value = rules.value.filter(x => x.id !== r.id);
    message.success("已删除");
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "删除失败");
  }
}

/* ---------- 触发记录 ---------- */
const events = ref([]);
const evTotal = ref(0);
const evPage = ref(1);
const EV_SIZE = 20;
const evLoading = ref(false);

async function loadEvents(page = 1) {
  evLoading.value = true;
  try {
    const d = await api(`/api/alerts/events/history?page=${page}&size=${EV_SIZE}`);
    events.value = d.rows;
    evTotal.value = d.total;
    evPage.value = page;
  } catch (err) {
    if (err.message !== "unauthorized") message.error(err.message || "加载失败");
  } finally {
    evLoading.value = false;
  }
}

async function readAll() {
  await markAllRead();
  loadEvents(evPage.value);
}

async function enableNotify() {
  const p = await requestNotifyPermission();
  if (p === "granted") message.success("浏览器通知已开启");
  else if (p === "denied") message.warning("通知被浏览器拒绝,可在地址栏站点设置中重新允许");
}

onMounted(() => {
  loadRules();
  loadEvents();
  markAllRead().catch(() => {});   // 进页即清未读角标
  track("alerts_view");
});
</script>

<template>
  <div class="alWrap">
    <!-- 通知权限引导 -->
    <div v-if="alertState.permission === 'default'" class="notifyBanner">
      开启浏览器通知后,预警触发时即使页面在后台也能收到系统弹窗(需保持本站打开)
      <button class="btnPrimary" @click="enableNotify">开启通知</button>
    </div>
    <div v-else-if="alertState.permission === 'denied'" class="notifyBanner dim">
      浏览器通知已被禁用,预警将以站内消息提示;如需系统弹窗请在浏览器站点设置中允许通知
    </div>

    <!-- 规则 -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">预警规则</span>
        <span class="secNote">交易时段随行情快照评估(约 3 分钟一轮) · 上限 50 条</span>
        <span class="barSpacer"></span>
        <button class="btnPrimary" @click="showCreate = !showCreate">
          {{ showCreate ? "收起" : "+ 新建规则" }}
        </button>
      </div>

      <div v-if="showCreate" class="createBox">
        <div class="cRow">
          <label>股票</label>
          <div class="cStock">
            <StockSearchInput @select="onPick" />
            <span v-if="form.code" class="picked">{{ form.name }} {{ form.code }}</span>
          </div>
        </div>
        <div class="cRow">
          <label>条件</label>
          <select v-model="form.rule_type" class="cSel">
            <option v-for="t in RULE_TYPES" :key="t.k" :value="t.k">{{ t.name }}</option>
          </select>
          <template v-if="!noThreshold(form.rule_type)">
            <input v-model="form.threshold" type="number" step="any" class="cNum" placeholder="阈值" />
            <span class="dimTxt">{{ (RULE_TYPES.find(t => t.k === form.rule_type) || {}).unit }}</span>
          </template>
          <span v-else class="dimTxt">触发即提醒,每交易日最多一次</span>
        </div>
        <div class="cRow">
          <label>冷却</label>
          <input v-model="form.cooldown_min" type="number" min="5" max="720" class="cNum" />
          <span class="dimTxt">分钟内不重复提醒(涨跌停类恒为每日一次)</span>
        </div>
        <div class="cRow">
          <label></label>
          <button class="btnPrimary" :disabled="creating" @click="createRule">
            {{ creating ? "创建中…" : "确认创建" }}
          </button>
        </div>
      </div>

      <div class="tblWrap" :class="{ loading: rulesLoading }">
        <table v-if="rules.length">
          <thead>
            <tr>
              <th class="l">股票</th><th class="l">条件</th><th>阈值</th>
              <th>冷却(分)</th><th>已触发</th><th>最近触发</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rules" :key="r.id">
              <td class="l">
                <router-link class="nameLink" :to="'/stock/' + r.code">{{ r.name }}</router-link>
                <span class="dimTxt"> {{ r.code }}</span>
              </td>
              <td class="l">{{ typeName(r.rule_type) }}</td>
              <td>{{ r.threshold == null ? "—" : fmtN(r.threshold) }}</td>
              <td>{{ r.cooldown_min }}</td>
              <td>{{ r.fire_count }}</td>
              <td class="dimTxt">{{ r.last_fired_at || "—" }}</td>
              <td>
                <button class="swBtn" :class="{ on: r.enabled }" @click="toggleRule(r)">
                  {{ r.enabled ? "启用中" : "已停用" }}
                </button>
              </td>
              <td><button class="delBtn" @click="removeRule(r)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">还没有预警规则——点右上角「新建规则」创建第一条</div>
      </div>
    </section>

    <!-- 触发记录 -->
    <section class="blk">
      <div class="secHead">
        <span class="secName">触发记录</span>
        <span class="secNote">共 {{ evTotal }} 条</span>
        <span class="barSpacer"></span>
        <button v-if="alertState.unread" class="ghostBtn" @click="readAll">
          全部已读({{ alertState.unread }})
        </button>
      </div>
      <div class="tblWrap" :class="{ loading: evLoading }">
        <table v-if="events.length">
          <thead>
            <tr><th class="l">时间</th><th class="l">股票</th><th class="l">规则</th><th>价格</th><th class="l">详情</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in events" :key="e.id" :class="{ unread: !e.read }">
              <td class="l dimTxt">{{ e.ts }}</td>
              <td class="l">
                <router-link class="nameLink" :to="'/stock/' + e.code">{{ e.name }}</router-link>
              </td>
              <td class="l">{{ typeName(e.rule_type) }}</td>
              <td>{{ fmtN(e.price) }}</td>
              <td class="l">{{ e.detail }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无触发记录</div>
      </div>
      <div v-if="evTotal > EV_SIZE" class="pager">
        <button class="ghostBtn" :disabled="evPage <= 1" @click="loadEvents(evPage - 1)">上一页</button>
        <span class="dimTxt">{{ evPage }} / {{ Math.ceil(evTotal / EV_SIZE) }}</span>
        <button class="ghostBtn" :disabled="evPage * EV_SIZE >= evTotal" @click="loadEvents(evPage + 1)">下一页</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.alWrap { padding: 12px 0 48px; }
.blk { margin-top: 14px; }
.secHead {
  display: flex; align-items: baseline; gap: 12px;
  padding-bottom: 10px; border-bottom: 1px solid var(--line);
}
.secName { font-size: 15px; font-weight: 650; letter-spacing: .04em; }
.secName::before {
  content: ""; display: inline-block; width: 3px; height: 12px; border-radius: 2px;
  background: var(--brand-red); margin-right: 8px; vertical-align: -1px;
}
.secNote { color: var(--dim); font-size: 12px; }
.barSpacer { flex: 1; }

.notifyBanner {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  background: var(--accent-dim); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px 14px; font-size: 12.5px; color: var(--txt);
}
.notifyBanner.dim { background: var(--panel-2); color: var(--dim); }

.btnPrimary {
  background: var(--btn-bg); color: var(--btn-txt); border: none; border-radius: 8px;
  padding: 6px 14px; font-size: 12.5px; font-family: inherit; cursor: pointer;
}
.btnPrimary:disabled { opacity: .6; cursor: default; }
.ghostBtn {
  background: none; border: 1px solid var(--line); border-radius: 8px;
  color: var(--dim); font-size: 12px; padding: 5px 12px; cursor: pointer; font-family: inherit;
}
.ghostBtn:hover { color: var(--txt); }
.ghostBtn:disabled { opacity: .4; cursor: default; }

.createBox {
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px;
  padding: 12px 14px; margin: 12px 0; max-width: 560px;
}
.cRow { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.cRow label { width: 40px; flex: none; font-size: 12.5px; color: var(--dim); }
.cStock { flex: 1; display: flex; align-items: center; gap: 10px; }
.cStock > div:first-child { flex: 1; }
.picked { font-size: 12.5px; color: var(--accent); font-weight: 600; white-space: nowrap; }
.cSel, .cNum {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  color: var(--txt); font-size: 13px; padding: 6px 10px; font-family: inherit; outline: none;
}
.cNum { width: 110px; }

.tblWrap { overflow-x: auto; margin-top: 10px; }
.tblWrap.loading { opacity: .55; pointer-events: none; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: right; color: var(--dim); font-weight: 500; font-size: 11.5px;
  letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line-strong);
  white-space: nowrap;
}
th.l, td.l { text-align: left; }
td { text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line); font-family: var(--mono); white-space: nowrap; }
tr.unread td { background: var(--accent-dim); }
tr:hover td { background: var(--hover); }
tr.unread:hover td { background: var(--hover); }
.nameLink { color: var(--txt); text-decoration: none; font-weight: 600; }
.nameLink:hover { color: var(--accent); }
.dimTxt { color: var(--dim); font-family: inherit; font-size: 12px; }
.empty { padding: 36px 0; text-align: center; color: var(--dim); font-size: 13px; }

.swBtn {
  border: 1px solid var(--line); background: none; border-radius: 999px;
  color: var(--dim); font-size: 11.5px; padding: 2px 10px; cursor: pointer; font-family: inherit;
}
.swBtn.on { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.delBtn {
  background: none; border: none; color: var(--dim); font-size: 12px;
  cursor: pointer; font-family: inherit;
}
.delBtn:hover { color: var(--down); }
.pager { display: flex; align-items: center; gap: 12px; margin-top: 10px; justify-content: flex-end; }
</style>
