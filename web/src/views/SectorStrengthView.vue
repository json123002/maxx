<template>
  <div class="sectorWrap">
    <!-- ===== 刊头与宏观攻防看板 ===== -->
    <section class="blk">
      <div class="secHead">
        <div>
          <span class="secName">板块强度矩阵</span>
          <span class="secEn">Sector Momentum</span>
        </div>
        <span v-if="fetchedAt" class="secMeta">
          <i class="liveDot"></i> 快照时间 {{ fetchedAt }} · {{ source || "东方财富" }}
        </span>
        <button class="ghostBtn" :disabled="loading" @click="load">
          {{ loading ? "计算中…" : "刷新" }}
        </button>
      </div>

      <!-- 宏观攻防与赚钱效应卡片 -->
      <div class="sectorMetrics">
        <div class="metricCard">
          <span class="mLabel">领涨冠军行业</span>
          <span class="mVal up">
            {{ summary.top_sector || "—" }}
            <small>{{ summary.top_gain > 0 ? "+" : "" }}{{ summary.top_gain }}%</small>
          </span>
        </div>

        <div class="metricCard">
          <span class="mLabel">行业涨跌广度</span>
          <div class="mNums">
            <span class="up"><b>{{ summary.up_sectors }}</b> 涨</span>
            <span class="down"><b>{{ summary.down_sectors }}</b> 跌</span>
            <span class="flat"><b>{{ summary.flat_sectors }}</b> 平</span>
          </div>
          <div class="mBar">
            <i class="up" :style="{ width: breadthPct + '%' }"></i>
            <i class="down" :style="{ width: (100 - breadthPct) + '%' }"></i>
          </div>
        </div>

        <div class="metricCard">
          <span class="mLabel">行业总覆盖数</span>
          <span class="mVal">{{ summary.total_sectors }} <small>个申万二级行业</small></span>
        </div>

        <div class="metricCard">
          <span class="mLabel">全行业涨停溢出</span>
          <span class="mVal up">{{ totalLimitUps }} <small>家非ST涨停</small></span>
        </div>
      </div>
    </section>

    <!-- ===== 行业板块强度排行榜 ===== -->
    <section class="blk listBlk">
      <div class="tableToolbar">
        <!-- 快速搜索 -->
        <div class="searchBox">
          <SearchOutlined class="searchIcon" />
          <input
            v-model="kw"
            type="text"
            placeholder="搜索行业名称…"
            class="searchInput"
          />
          <button v-if="kw" class="clearBtn" @click="kw = ''">×</button>
        </div>

        <!-- 排序方式 -->
        <div class="sortTabs">
          <button
            class="sortTab"
            :class="{ act: sortBy === 'avg_chg' }"
            @click="sortBy = 'avg_chg'"
          >
            涨跌幅 {{ sortBy === 'avg_chg' ? '↓' : '' }}
          </button>
          <button
            class="sortTab"
            :class="{ act: sortBy === 'limit_up_cnt' }"
            @click="sortBy = 'limit_up_cnt'"
          >
            涨停家数 {{ sortBy === 'limit_up_cnt' ? '↓' : '' }}
          </button>
          <button
            class="sortTab"
            :class="{ act: sortBy === 'amt_yi' }"
            @click="sortBy = 'amt_yi'"
          >
            成交总额 {{ sortBy === 'amt_yi' ? '↓' : '' }}
          </button>
          <button
            class="sortTab"
            :class="{ act: sortBy === 'avg_tov' }"
            @click="sortBy = 'avg_tov'"
          >
            平均换手 {{ sortBy === 'avg_tov' ? '↓' : '' }}
          </button>
        </div>
      </div>

      <!-- 强度列表 -->
      <div class="tableBox">
        <table class="matrixTable">
          <thead>
            <tr>
              <th style="width: 48px;">#</th>
              <th style="width: 130px;">行业板块</th>
              <th style="width: 100px; text-align: right;">平均涨跌</th>
              <th style="width: 170px;">涨跌分布 (涨 / 跌 / 平)</th>
              <th style="width: 90px; text-align: center;">涨停家数</th>
              <th style="width: 180px;">领涨标杆龙头</th>
              <th style="width: 110px; text-align: right;">成交总额</th>
              <th style="width: 90px; text-align: right;">平均换手</th>
              <th style="width: 110px; text-align: center;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in displayRows" :key="row.industry" class="matrixRow">
              <td class="idxCol">{{ idx + 1 }}</td>
              <td class="nameCol">
                <span class="industryName">{{ row.industry }}</span>
                <span class="stockCount">{{ row.total }} 只</span>
              </td>
              <td class="chgCol" :class="cls(row.avg_chg)">
                <b>{{ row.avg_chg > 0 ? "+" : "" }}{{ fmtN(row.avg_chg) }}%</b>
              </td>
              <td class="breadthCol">
                <div class="bRatio">
                  <span class="up">{{ row.up_cnt }}</span>
                  <span class="sep">/</span>
                  <span class="down">{{ row.down_cnt }}</span>
                  <span class="sep">/</span>
                  <span class="flat">{{ row.flat_cnt }}</span>
                </div>
                <div class="miniBar">
                  <i class="up" :style="{ width: ((row.up_cnt / Math.max(1, row.total)) * 100) + '%' }"></i>
                  <i class="down" :style="{ width: ((row.down_cnt / Math.max(1, row.total)) * 100) + '%' }"></i>
                </div>
              </td>
              <td class="limitCol" style="text-align: center;">
                <span v-if="row.limit_up_cnt > 0" class="limitBadge">
                  {{ row.limit_up_cnt }} 涨停
                </span>
                <span v-else class="dimZero">—</span>
              </td>
              <td class="topStockCol">
                <router-link
                  v-if="row.top_code"
                  :to="'/stock/' + row.top_code"
                  class="topStockLink"
                  :title="'查看 ' + row.top_name + ' 个股行情'"
                >
                  <span class="tsName">{{ row.top_name }}</span>
                  <span class="tsCode">{{ row.top_code }}</span>
                  <b class="tsChg" :class="cls(row.top_chg)">
                    {{ row.top_chg > 0 ? "+" : "" }}{{ fmtN(row.top_chg) }}%
                  </b>
                </router-link>
                <span v-else class="dimZero">—</span>
              </td>
              <td class="numCol amtCol">{{ fmtN(row.amt_yi, 1) }} 亿</td>
              <td class="numCol">{{ fmtN(row.avg_tov, 2) }}%</td>
              <td class="actionCol">
                <router-link
                  :to="'/screener?industry=' + encodeURIComponent(row.industry)"
                  class="screenerLink"
                >
                  进入筛选 →
                </router-link>
              </td>
            </tr>
            <tr v-if="displayRows.length === 0">
              <td colspan="9" class="emptyRow">
                {{ loading ? "数据加载计算中…" : "未找到匹配的行业板块" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ===== 底线免责声明 ===== -->
    <footer class="disclaimer">
      <span>
        免责声明：板块强度数据由全市场快照实时客观聚合计算，仅为形态与热度统计，不构成任何投资建议或股票推荐。
        市场有风险，投资决策需完全独立自担。
      </span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import { SearchOutlined } from "@ant-design/icons-vue";
import { api, track } from "../api/client";
import { cls, fmtN } from "../utils/format";

const loading = ref(false);
const rows = ref([]);
const summary = ref({
  total_sectors: 0,
  up_sectors: 0,
  down_sectors: 0,
  flat_sectors: 0,
  top_sector: "",
  top_gain: 0,
});
const fetchedAt = ref("");
const source = ref("");
const kw = ref("");
const sortBy = ref("avg_chg"); // avg_chg | limit_up_cnt | amt_yi | avg_tov

const breadthPct = computed(() => {
  const tot = summary.value.total_sectors || 1;
  return Math.round((summary.value.up_sectors / tot) * 100);
});

const totalLimitUps = computed(() => {
  return rows.value.reduce((acc, r) => acc + (r.limit_up_cnt || 0), 0);
});

const displayRows = computed(() => {
  let list = rows.value;
  if (kw.value.trim()) {
    const k = kw.value.trim().toLowerCase();
    list = list.filter((r) => r.industry?.toLowerCase().includes(k));
  }

  const s = sortBy.value;
  return [...list].sort((a, b) => {
    return (b[s] ?? -Infinity) - (a[s] ?? -Infinity);
  });
});

async function load() {
  loading.value = true;
  try {
    const d = await api("/api/quote/sector-strength");
    rows.value = d.rows || [];
    summary.value = d.summary || {};
    fetchedAt.value = d.fetched_at || "";
    source.value = d.source || "";
    track("sector_view", `全市场 ${rows.value.length} 个行业 · 领涨: ${d.summary?.top_sector || "无"}`);
  } catch (err) {
    if (err.message !== "unauthorized") {
      message.error(err.message || "板块强度数据加载失败");
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.sectorWrap {
  width: 100%;
  padding: 4px 0 20px;
}

/* 区块通用头部 */
.blk {
  margin-top: 14px;
}
.secHead {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.secName {
  font-size: 16px;
  font-weight: 650;
  letter-spacing: 0.04em;
}
.secName::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: var(--brand-red);
  margin-right: 8px;
  vertical-align: -1px;
}
.secEn {
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--dim);
  font-family: var(--mono);
}
.secMeta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--dim);
  font-family: var(--mono);
  margin-left: 12px;
}
.liveDot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.ghostBtn {
  margin-left: auto;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--line);
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s;
}
.ghostBtn:hover:not(:disabled) {
  color: var(--txt);
  border-color: var(--line-strong);
}

/* 顶部概览看板卡片 */
.sectorMetrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-top: 16px;
}
.metricCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mLabel {
  font-size: 12px;
  color: var(--dim);
}
.mVal {
  font-family: var(--mono);
  font-size: 20px;
  font-weight: 600;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.mVal small {
  font-size: 12px;
  font-weight: 400;
  color: var(--dim);
}
.mVal.up { color: var(--up); }
.mVal.down { color: var(--down); }

.mNums {
  display: flex;
  gap: 10px;
  font-size: 12px;
  font-family: var(--mono);
}
.mNums b { font-size: 14px; font-weight: 600; }
.mNums .up { color: var(--up); }
.mNums .down { color: var(--down); }
.mNums .flat { color: var(--dim); }
.mBar {
  display: flex;
  height: 5px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--panel-2);
  margin-top: 4px;
}
.mBar i { display: block; height: 100%; transition: width 0.3s; }
.mBar i.up { background: var(--up); }
.mBar i.down { background: var(--down); }

/* 工具条与排序 */
.listBlk {
  margin-top: 24px;
}
.tableToolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.searchBox {
  position: relative;
  width: 240px;
}
.searchIcon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim);
  font-size: 13px;
}
.searchInput {
  width: 100%;
  height: 32px;
  padding: 0 28px 0 30px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--txt);
  font-size: 12.5px;
  outline: none;
  transition: border-color 0.15s;
}
.searchInput:focus {
  border-color: var(--accent);
}
.clearBtn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--dim);
  cursor: pointer;
  font-size: 14px;
}

.sortTabs {
  display: flex;
  gap: 4px;
  background: var(--panel);
  padding: 3px;
  border-radius: 7px;
  border: 1px solid var(--line);
}
.sortTab {
  padding: 4px 10px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--dim);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.sortTab:hover {
  color: var(--txt);
}
.sortTab.act {
  background: var(--bg);
  color: var(--txt);
  font-weight: 550;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* 强度表格 */
.tableBox {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}
.matrixTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.matrixTable th {
  padding: 10px 12px;
  background: var(--panel);
  color: var(--dim);
  font-weight: 500;
  text-align: left;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
}
.matrixRow {
  border-bottom: 1px solid var(--line);
  transition: background 0.12s;
}
.matrixRow:hover {
  background: var(--hover);
}
.matrixRow td {
  padding: 10px 12px;
  vertical-align: middle;
}

.idxCol {
  font-family: var(--mono);
  color: var(--dim);
  font-size: 11.5px;
}
.nameCol {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.industryName {
  font-weight: 600;
  color: var(--txt);
}
.stockCount {
  font-size: 11px;
  color: var(--dim);
  font-family: var(--mono);
}

.chgCol {
  font-family: var(--mono);
  font-size: 13px;
  text-align: right;
}
.chgCol.up { color: var(--up); }
.chgCol.down { color: var(--down); }

.breadthCol {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bRatio {
  font-family: var(--mono);
  font-size: 11.5px;
}
.bRatio .up { color: var(--up); font-weight: 550; }
.bRatio .down { color: var(--down); font-weight: 550; }
.bRatio .flat { color: var(--dim); }
.bRatio .sep { color: var(--dim); opacity: 0.5; margin: 0 3px; }
.miniBar {
  display: flex;
  height: 4px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--panel-2);
}
.miniBar i { display: block; height: 100%; }
.miniBar i.up { background: var(--up); }
.miniBar i.down { background: var(--down); }

.limitBadge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-family: var(--mono);
  font-weight: 600;
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.25);
}
.dimZero {
  color: var(--dim);
  opacity: 0.4;
}

.topStockLink {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  text-decoration: none;
  color: var(--txt);
  transition: color 0.15s;
}
.topStockLink:hover .tsName {
  color: var(--accent);
}
.tsName {
  font-weight: 500;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tsCode {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
}
.tsChg {
  font-family: var(--mono);
  font-size: 12px;
}
.tsChg.up { color: var(--up); }
.tsChg.down { color: var(--down); }

.numCol {
  font-family: var(--mono);
  text-align: right;
  color: var(--txt);
}
.amtCol {
  color: var(--dim);
}

.actionCol {
  text-align: center;
}
.screenerLink {
  display: inline-block;
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  padding: 2px 6px;
  border-radius: 4px;
  transition: background 0.15s;
}
.screenerLink:hover {
  background: var(--hover);
  text-decoration: underline;
}

.emptyRow {
  text-align: center;
  padding: 40px;
  color: var(--dim);
  font-size: 13px;
}

/* 免责声明 */
.disclaimer {
  margin-top: 36px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  color: var(--dim);
  font-size: 11.5px;
  line-height: 1.8;
}

/* 响应式适配 */
@media (max-width: 1024px) {
  .sectorMetrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 768px) {
  .sectorMetrics {
    grid-template-columns: 1fr;
  }
  .tableToolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .searchBox {
    width: 100%;
  }
}
</style>
