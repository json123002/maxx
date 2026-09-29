<template>
  <div class="neuralLabRoot">
    <!-- 1. 顶部紧凑状态与工具栏 (高度42px，精致紧凑，集成推理与回测双模式) -->
    <div class="nlHeader">
      <div class="nlTitleBox">
        <div class="nlMainTitle">
          <span class="nlTitleIcon">🧠</span>
          <span class="nlTitleText">神经网络实验室</span>
          <span class="nlVersionBadge">DL Engine v2.5</span>
        </div>

        <!-- 模式切换：实时特征拟合 vs 历史回测调参验证 -->
        <div class="modeSwitcher">
          <button
            class="modeTabBtn"
            :class="{ active: activeMode === 'predict' }"
            @click="switchMode('predict')"
            title="使用当前参数对全市场实时或指定历史截面进行特征拟合优选"
          >
            ⚡ 实时特征拟合
          </button>
          <button
            class="modeTabBtn"
            :class="{ active: activeMode === 'backtest' }"
            @click="switchMode('backtest')"
            title="在历史基准日运行模型，追踪选出个股在随后的真实涨跌与胜率，验证调参效果"
          >
            📈 历史回测调参验证
          </button>
        </div>
      </div>

      <div class="nlHeaderRight">
        <!-- 模式 A：实时推理数据源切换 -->
        <div class="sourceToggle" v-if="activeMode === 'predict'">
          <span class="sourceLabel">数据源:</span>
          <div class="segmentedBtns">
            <button
              class="segBtn"
              :class="{ active: form.data_source === 'latest' }"
              @click="switchDataSource('latest')"
              title="使用今日最新盘中实时行情快照 (真实成交与实时涨跌)"
            >
              ⚡ 今日盘中实时
            </button>
            <button
              class="segBtn"
              :class="{ active: form.data_source === 'history' }"
              @click="switchDataSource('history')"
              title="切换为历史完整交易日全截面"
            >
              📊 历史全截面
            </button>
          </div>

          <!-- 历史截面日期下拉选择 -->
          <div class="dateSelectBox" v-if="form.data_source === 'history'">
            <select v-model="form.trade_date" @change="runInference" class="dateSelect">
              <option v-for="d in availableDates.history_dates" :key="d.date" :value="d.date">
                {{ d.date }} ({{ d.count }}只)
              </option>
            </select>
          </div>
        </div>

        <!-- 模式 B：历史回测基准日选择 -->
        <div class="sourceToggle" v-else>
          <span class="sourceLabel">回测基准日:</span>
          <select v-model="backtestBaseDate" class="dateSelect" @change="runBacktest">
            <option v-for="d in availableDates.history_dates" :key="d.date" :value="d.date">
              {{ d.date }} 选出
            </option>
          </select>
          <span class="btTargetTip">→ 跟踪至最新成交</span>
        </div>

        <!-- 操作按钮组 -->
        <div class="nlActions">
          <template v-if="activeMode === 'predict'">
            <button class="nlRunBtnCompact" :disabled="loading" @click="runInference">
              <ThunderboltOutlined v-if="!loading" />
              <span v-else class="spinIcon">⏳</span>
              <span>{{ loading ? '前向推导中...' : '启动前向推理 (Ctrl+Enter)' }}</span>
            </button>
            <button class="nlResetBtnCompact" @click="resetToDefault">重置</button>
          </template>

          <template v-else>
            <button class="nlRunBtnCompact btRunBtn" :disabled="backtestLoading" @click="runBacktest">
              <RocketOutlined v-if="!backtestLoading" />
              <span v-else class="spinIcon">⏳</span>
              <span>{{ backtestLoading ? '回测运算中...' : '运行历史回测验证' }}</span>
            </button>
            <button class="nlResetBtnCompact" @click="resetToDefault">重置参数</button>
          </template>
        </div>
      </div>
    </div>

    <!-- 2. 醒目合规与风险提示条 (强调纯客观数学特征拟合工具，严禁理解为荐股) -->
    <div class="nlComplianceBanner">
      <span class="bannerIcon">⚠️</span>
      <span class="bannerText">
        <b>【量化实验合规声明】</b>本实验室仅供客观数学公式特征拟合与算法参数实验，<b>高拟合度（Fit Score）仅代表标的与您设定参数公式的数学契合程度，绝非买入推荐，绝不构成投资建议或个股推荐！</b>股市有风险，入市须谨慎，投资决策须由使用者独立作出并自担风险。
      </span>
    </div>

    <!-- 3. 策略预设模型与指标状态条 (单行展示，杜绝折叠换行与滚动条异常) -->
    <div class="nlPresetsBar">
      <div class="presetLabel">
        <ExperimentOutlined />
        <span>策略预设:</span>
      </div>
      <div class="presetButtons">
        <button
          v-for="p in PRESETS"
          :key="p.id"
          class="presetBtn"
          :class="{ active: currentPreset === p.id }"
          @click="applyPreset(p)"
        >
          <span class="presetIcon">{{ p.icon }}</span>
          <span class="presetName">{{ p.name }}</span>
          <span class="presetTag">{{ p.tag }}</span>
        </button>
      </div>

      <!-- 右侧状态标签 -->
      <div class="metaPillsInline" v-if="activeMode === 'predict' && telemetryMeta">
        <span class="mPill"><i class="mDot"></i>{{ telemetryMeta.dataMode }}</span>
        <span class="mPill">全市场: <b>{{ telemetryMeta.totalScanned?.toLocaleString() }}</b> 只</span>
        <span class="mPill">合格样本: <b>{{ telemetryMeta.qualifiedCount?.toLocaleString() }}</b> 只</span>
        <span class="mPill">耗时: <b>{{ telemetryMeta.inferenceTimeMs }}ms</b></span>
      </div>
      <div class="metaPillsInline" v-else-if="activeMode === 'backtest' && backtestMeta">
        <span class="mPill"><i class="mDot"></i>回测基准: <b>{{ backtestMeta.base_date }}</b></span>
        <span class="mPill">跟踪样本: <b>{{ backtestMeta.total_picked }}</b> 只</span>
        <span class="mPill">耗时: <b>{{ backtestMeta.elapsed_ms }}ms</b></span>
      </div>
    </div>

    <!-- 4. 核心工作区：外层严禁滚动条，左侧独立内部滚动 + 右侧独立内部滚动 -->
    <div class="nlMainGrid">
      <!-- 左侧：参数调优驾驶舱 (内部纵向滚动，包含卡片1突触、卡片2超参、卡片3过滤) -->
      <div class="nlLeftCol">
        <!-- 卡片 1: 突触权重配置 -->
        <div class="cockpitCard">
          <div class="cardHeader">
            <div class="cardTitle">
              <ApartmentOutlined />
              <span>特征突触权重 (Synaptic Weights)</span>
            </div>
            <span class="cardTip">[-100, +100] · 负抑制 / 正激励</span>
          </div>

          <div class="sliderGroup">
            <!-- 换手活跃度 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot turnoverDot"></span>换手活跃度权重 (f8)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_turnover)">
                  {{ form.weight_turnover > 0 ? '+' : '' }}{{ form.weight_turnover }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_turnover"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 主力资金净流入 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot capitalDot"></span>主力资金合力权重 (f62/f6)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_capital)">
                  {{ form.weight_capital > 0 ? '+' : '' }}{{ form.weight_capital }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_capital"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 量比爆发度 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot volratioDot"></span>量比爆发度权重 (f10)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_volume_ratio)">
                  {{ form.weight_volume_ratio > 0 ? '+' : '' }}{{ form.weight_volume_ratio }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_volume_ratio"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 当日涨幅动能 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot momentumDot"></span>当日涨幅动能权重 (f3)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_momentum)">
                  {{ form.weight_momentum > 0 ? '+' : '' }}{{ form.weight_momentum }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_momentum"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 竞价跳空幅度 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot gapDot"></span>竞价跳空高开权重 (f17/f18)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_auction_gap)">
                  {{ form.weight_auction_gap > 0 ? '+' : '' }}{{ form.weight_auction_gap }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_auction_gap"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 盘中振幅弹性 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot ampDot"></span>盘中振幅博弈权重 (f7)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_amplitude)">
                  {{ form.weight_amplitude > 0 ? '+' : '' }}{{ form.weight_amplitude }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_amplitude"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 60日趋势动能 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot trendDot"></span>60日中周期趋势权重 (f24)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_trend_60d)">
                  {{ form.weight_trend_60d > 0 ? '+' : '' }}{{ form.weight_trend_60d }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_trend_60d"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>

            <!-- 流通市值偏好 -->
            <div class="sliderItem">
              <div class="sliderLabelRow">
                <span class="factorName">
                  <span class="dot mcapDot"></span>市值规模偏好 (负数=偏好中小盘)
                </span>
                <span class="sliderVal" :class="weightValClass(form.weight_market_cap)">
                  {{ form.weight_market_cap > 0 ? '+' : '' }}{{ form.weight_market_cap }}
                </span>
              </div>
              <a-slider
                v-model:value="form.weight_market_cap"
                :min="-100"
                :max="100"
                :step="5"
                @change="onWeightChange"
              />
            </div>
          </div>
        </div>

        <!-- 卡片 2: 深度学习超参数设置 (始终可滚动查看) -->
        <div class="cockpitCard">
          <div class="cardHeader">
            <div class="cardTitle">
              <ControlOutlined />
              <span>网络超参数 (Hyperparameters)</span>
            </div>
          </div>

          <div class="hyperparamBody">
            <!-- 激活函数选择 -->
            <div class="paramRow">
              <div class="paramLabel">非线性激活函数 σ(x)</div>
              <a-radio-group v-model:value="form.activation" button-style="solid" size="small" @change="onWeightChange">
                <a-radio-button value="gelu">GELU (大模型)</a-radio-button>
                <a-radio-button value="tanh">Tanh (正切)</a-radio-button>
                <a-radio-button value="sigmoid">Sigmoid</a-radio-button>
                <a-radio-button value="leaky_relu">LeakyReLU</a-radio-button>
                <a-radio-button value="relu">ReLU</a-radio-button>
              </a-radio-group>
            </div>

            <!-- 温度系数 T -->
            <div class="paramRow">
              <div class="sliderLabelRow">
                <span class="paramLabel">
                  Softmax 温度系数 T:
                  <span class="subInfo">(T 越小分数梯度越锐利)</span>
                </span>
                <span class="sliderVal highlightVal">T = {{ form.temperature.toFixed(2) }}</span>
              </div>
              <a-slider
                v-model:value="form.temperature"
                :min="0.2"
                :max="2.0"
                :step="0.05"
                @change="onWeightChange"
              />
            </div>

            <!-- 放量滞涨惩罚 -->
            <div class="switchRow">
              <div class="switchLabel">
                <span class="swTitle">放量滞涨惩罚 (Stagflation Penalty)</span>
                <span class="swDesc">扣减爆天量但涨幅低迷翻绿标的的特征拟合度</span>
              </div>
              <a-switch v-model:checked="form.stagflation_penalty" @change="onWeightChange" />
            </div>
          </div>
        </div>

        <!-- 卡片 3: 刚性约束与样本空间过滤 -->
        <div class="cockpitCard">
          <div class="cardHeader">
            <div class="cardTitle">
              <FilterOutlined />
              <span>样本空间刚性过滤 (Constraints)</span>
            </div>
            <a-button type="link" size="small" class="relaxBtn" @click="relaxFilters">放宽门槛</a-button>
          </div>

          <div class="filterBody">
            <div class="switchesGrid">
              <div class="switchMini">
                <a-switch v-model:checked="form.exclude_st" size="small" @change="onWeightChange" />
                <span>剔除 ST / *ST / 退市</span>
              </div>
              <div class="switchMini">
                <a-switch v-model:checked="form.exclude_suspended" size="small" @change="onWeightChange" />
                <span>剔除停牌 (成交=0)</span>
              </div>
            </div>

            <div class="rangeRow">
              <span class="fLabel">换手率下限%:</span>
              <div class="rangeInputs">
                <a-input-number v-model:value="form.min_turnover" :min="0" :max="100" :step="0.5" size="small" />
                <span class="sep">~</span>
                <a-input-number v-model:value="form.max_turnover" :min="0" :max="100" :step="5" size="small" />
              </div>
            </div>

            <div class="rangeRow">
              <span class="fLabel">最低成交额(亿):</span>
              <div class="rangeInputs">
                <a-input-number v-model:value="form.min_amount_yi" :min="0" :step="0.05" size="small" />
              </div>
            </div>

            <div class="rangeRow">
              <span class="fLabel">流通市值(亿):</span>
              <div class="rangeInputs">
                <a-input-number v-model:value="form.min_market_cap_yi" :min="0" size="small" />
                <span class="sep">~</span>
                <a-input-number v-model:value="form.max_market_cap_yi" :min="0" size="small" />
              </div>
            </div>

            <div class="marketCheckboxes">
              <span class="fLabel">板块范围:</span>
              <a-checkbox-group v-model:value="form.markets" :options="MARKET_OPTIONS" @change="onWeightChange" />
            </div>
          </div>
        </div>

        <!-- 卡片 4: 历史回测寻优（在全部历史截面上真实搜索出的最优默认参数） -->
        <div class="cockpitCard optimizeCard">
          <div class="cardHeader">
            <div class="cardTitle">
              <RocketOutlined />
              <span>回测寻优 (Auto-Tuned)</span>
            </div>
            <button class="optRefreshBtn" :disabled="optLoading" @click="runOptimize(true)">
              {{ optLoading ? '搜索中…' : '重新寻优' }}
            </button>
          </div>
          <div class="optBody" v-if="optimizeResult">
            <div class="optKpis">
              <div class="optKpi">
                <span class="optKpiVal">{{ optimizeResult.best.win_rate }}%</span>
                <span class="optKpiLab">平均胜率</span>
              </div>
              <div class="optKpi">
                <span class="optKpiVal" :class="optimizeResult.best.alpha >= 0 ? 'upTxt' : 'downTxt'">
                  {{ optimizeResult.best.alpha > 0 ? '+' : '' }}{{ optimizeResult.best.alpha }}%
                </span>
                <span class="optKpiLab">平均 Alpha</span>
              </div>
              <div class="optKpi">
                <span class="optKpiVal">{{ optimizeResult.samples_evaluated }}</span>
                <span class="optKpiLab">评估参数组</span>
              </div>
            </div>
            <div class="optDates">
              训练截面: {{ optimizeResult.dates_used.join(' → ') }}{{ optimizeResult.cached ? ' (缓存)' : '' }}
              · 激活: {{ (optimizeResult.best.activation || 'gelu').toUpperCase() }}
              <span class="optAppliedTag" v-if="isOptimizedApplied">✓ 已设为默认参数</span>
            </div>
            <div class="optWeights">
              <div v-for="w in optimizeWeightBars" :key="w.name" class="optWRow">
                <span class="optWName">{{ w.label }}</span>
                <div class="optWBarTrack">
                  <div
                    class="optWBar"
                    :class="w.value >= 0 ? 'pos' : 'neg'"
                    :style="{
                      width: Math.abs(w.value) / 2 + '%',
                      marginLeft: w.value >= 0 ? '50%' : (50 - Math.abs(w.value) / 2) + '%'
                    }"
                  ></div>
                </div>
                <span class="optWVal" :class="w.value >= 0 ? 'upTxt' : 'downTxt'">
                  {{ w.value > 0 ? '+' : '' }}{{ w.value }}
                </span>
              </div>
            </div>
            <button class="optApplyBtn" @click="applyOptimized">⚡ 应用最优参数并推理</button>
          </div>
          <div class="optBody optEmpty" v-else>
            {{ optLoading ? '正在历史截面上搜索最优参数…' : '点击「重新寻优」基于历史回测训练最优默认参数' }}
          </div>
        </div>
      </div>

      <!-- 右侧：拓扑可视化 + 推理思考流（顶部并排） + 优选/回测结果 -->
      <div class="nlRightCol">
        <div class="nlTopTwinCards">
          <!-- 神经网络动态前向拓扑图 -->
          <div class="twinCard topologyCard">
            <div class="cardHeader">
              <div class="cardTitle">
                <DeploymentUnitOutlined />
                <span>前向传播网络拓扑 (Topology)</span>
              </div>
              <div class="topologyLegends">
                <span class="legItem"><i class="legDot dotInput"></i>输入特征</span>
                <span class="legItem"><i class="legDot dotLatent"></i>隐层核</span>
                <span class="legItem"><i class="legDot dotAct"></i>{{ form.activation.toUpperCase() }}</span>
                <span class="legItem"><i class="legDot dotOut"></i>Fit</span>
              </div>
            </div>

            <div class="topologyCanvasWrapper">
              <svg class="topologySvg" :class="{ inferring }" viewBox="0 0 680 175" preserveAspectRatio="xMidYMid meet">
                <defs>
                  <filter id="nodeGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2.5" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                <!-- 突触连接线 -->
                <g class="synapseLines">
                  <path
                    v-for="(syn, idx) in synapseConnections"
                    :key="'syn-' + idx"
                    :d="syn.path"
                    :stroke="syn.color"
                    :stroke-width="syn.width"
                    :stroke-dasharray="syn.dash"
                    fill="none"
                    class="synapsePath"
                    :class="{ pulsing: syn.active }"
                  />
                </g>

                <!-- 前向传播信号粒子（点击推理后沿突触实时流动） -->
                <g v-if="inferring" class="signalParticles">
                  <circle
                    v-for="(syn, idx) in synapseConnections"
                    :key="'pt-' + idx"
                    r="2.4"
                    class="particle"
                  >
                    <animateMotion
                      :dur="(0.8 + (idx % 5) * 0.18) + 's'"
                      :begin="((idx % 7) * 0.1) + 's'"
                      repeatCount="indefinite"
                      :path="syn.path"
                    />
                  </circle>
                </g>

                <!-- 输入层节点 (8个) -->
                <g class="inputNodesGroup">
                  <g
                    v-for="n in inputNodesCoords"
                    :key="'in-' + n.id"
                    :transform="`translate(${n.x}, ${n.y})`"
                    class="nodeGroup"
                  >
                    <circle r="7.5" :fill="n.active ? '#10b981' : '#94a3b8'" filter="url(#nodeGlow)" />
                    <circle r="4" fill="var(--panel, #ffffff)" />
                    <text x="-12" y="3.5" text-anchor="end" class="svgLabel inLabel">{{ n.name }}</text>
                    <text x="12" y="3.5" text-anchor="start" class="svgValText">{{ n.weightVal }}</text>
                  </g>
                </g>

                <!-- 隐层神经元节点 (4个) -->
                <g class="latentNodesGroup">
                  <g
                    v-for="n in latentNodesCoords"
                    :key="'lat-' + n.id"
                    :transform="`translate(${n.x}, ${n.y})`"
                    class="nodeGroup"
                  >
                    <circle r="11" fill="#6366f1" filter="url(#nodeGlow)" />
                    <circle r="7" fill="var(--panel, #ffffff)" />
                    <text x="0" y="3.5" text-anchor="middle" class="svgCoreCode">{{ n.symbol }}</text>
                    <text x="0" y="20" text-anchor="middle" class="svgSubLabel">{{ n.name }}</text>
                  </g>
                </g>

                <!-- 激活门节点 -->
                <g :transform="`translate(${activationNodeCoord.x}, ${activationNodeCoord.y})`" class="nodeGroup">
                  <rect x="-22" y="-11" width="44" height="22" rx="5" fill="#ec4899" filter="url(#nodeGlow)" />
                  <text x="0" y="3.5" text-anchor="middle" class="svgActText">σ:{{ form.activation.toUpperCase() }}</text>
                </g>

                <!-- 输出层拟合度节点 -->
                <g :transform="`translate(${outputNodeCoord.x}, ${outputNodeCoord.y})`" class="nodeGroup">
                  <circle r="14" fill="#f59e0b" filter="url(#nodeGlow)" />
                  <circle r="9" fill="var(--panel, #ffffff)" />
                  <text x="0" y="3.5" text-anchor="middle" class="svgOutText">Fit</text>
                  <text x="0" y="24" text-anchor="middle" class="svgOutSubText">公式拟合度</text>
                </g>
              </svg>
            </div>
          </div>

          <!-- 推理思考流 Telemetry 日志 -->
          <div class="twinCard telemetryCard">
            <div class="cardHeader">
              <div class="cardTitle">
                <CodeOutlined />
                <span>推理思考流 (Inference Telemetry)</span>
              </div>
              <span class="telemetryStatus" :class="{ running: loading || backtestLoading }">
                <span class="statusDot"></span>
                {{ (loading || backtestLoading) ? '模型计算中...' : 'Epoch 已收敛' }}
              </span>
            </div>

            <div class="telemetryConsole">
              <div v-if="loading || backtestLoading" class="telemetryLoading">
                <a-spin />
                <span class="tLoadTxt">正在提取全市场截面特征矩阵并计算多层前向推导...</span>
              </div>
              <div v-else class="telemetryLogs">
                <div v-for="t in telemetrySteps" :key="t.step" class="logStepItem">
                  <div class="logStepHeader">
                    <span class="stepBadge">Step {{ t.step }}</span>
                    <span class="phaseName">{{ t.phase }}</span>
                    <span class="stepMs">{{ t.time_ms }}ms</span>
                  </div>
                  <div class="stepMsg">{{ t.msg }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 场景 A：实时/历史特征拟合优选榜单卡片 -->
        <div class="cockpitCard predictionsCard" v-if="activeMode === 'predict'">
          <div class="predCardHeader">
            <div class="predTitleBox">
              <div class="predMainTitle">
                <RocketOutlined />
                <span>神经网络特征拟合多维优选榜</span>
                <span class="resCountBadge" v-if="predictions.length > 0">Top {{ predictions.length }} 优选</span>
                <span class="curSourceBadge" :class="{ isLive: form.data_source === 'latest' }">
                  {{ form.data_source === 'latest' ? '⚡ 盘中实时成交' : `📊 历史截面 (${form.trade_date || '最近'})` }}
                </span>
              </div>
            </div>

            <!-- 等级筛选药丸 -->
            <div class="gradeFilters" v-if="predictions.length > 0">
              <button
                class="gradeFilterBtn"
                :class="{ active: selectedGradeFilter === 'ALL' }"
                @click="selectedGradeFilter = 'ALL'"
              >
                全部 ({{ predictions.length }})
              </button>
              <button
                class="gradeFilterBtn gradeAplusplus"
                :class="{ active: selectedGradeFilter === 'A++' }"
                @click="selectedGradeFilter = 'A++'"
              >
                A++ 高匹配 ({{ gradeCount('A++') }})
              </button>
              <button
                class="gradeFilterBtn gradeAplus"
                :class="{ active: selectedGradeFilter === 'A+' }"
                @click="selectedGradeFilter = 'A+'"
              >
                A+ 良好 ({{ gradeCount('A+') }})
              </button>
              <button
                class="gradeFilterBtn gradeA"
                :class="{ active: selectedGradeFilter === 'A' }"
                @click="selectedGradeFilter = 'A'"
              >
                A 契合 ({{ gradeCount('A') }})
              </button>
            </div>
          </div>

          <!-- 优选结果原生表格 -->
          <div class="nlTableWrap" :class="{ loading }">
            <table v-if="paginatedPredictions.length" class="nlTable">
              <thead>
                <tr>
                  <th class="thCenter" style="width: 42px">排名</th>
                  <th style="width: 130px">股票标的</th>
                  <!-- 实时模式下显示实时现价；历史模式下显示选出日价格 -->
                  <th class="thRight" style="width: 100px">
                    {{ form.data_source === 'latest' ? '现价 / 涨跌' : '选出日价 / 涨跌' }}
                  </th>
                  <!-- 历史截面模式下，附加展示今日最新现价与累计盈亏 -->
                  <th class="thRight" style="width: 115px" v-if="form.data_source === 'history'">
                    最新价 / 累计盈亏
                  </th>
                  <th style="width: 88px">换手/量比</th>
                  <th style="width: 110px">成交额/主力</th>
                  <th style="width: 140px" title="客观数学特征吻合度分值，绝非买入推荐">
                    拟合度 ℹ️
                  </th>
                  <th style="min-width: 160px">特征归因</th>
                  <th class="thCenter" style="width: 96px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in paginatedPredictions" :key="r.code" class="nlRow">
                  <!-- 排名 -->
                  <td class="thCenter">
                    <span class="rankBadge" :class="'rank-' + r.rank">{{ r.rank }}</span>
                  </td>

                  <!-- 代码与名称 -->
                  <td>
                    <div class="stockCell">
                      <div class="stockMain">
                        <a class="stockCode" @click.stop="openAnalysis(r.code)">{{ r.code }}</a>
                        <span class="stockName" @click.stop="openAnalysis(r.code)">{{ r.name }}</span>
                        <span v-if="r.limit_up" class="ztTag">涨停</span>
                      </div>
                      <div class="stockSub">
                        <span class="industryTag">{{ r.industry || '综合' }}</span>
                        <span class="marketTag">{{ r.market }}</span>
                      </div>
                    </div>
                  </td>

                  <!-- 现价与涨跌幅 (选出日) -->
                  <td class="thRight">
                    <div class="priceCell" :class="cls(r.f3)">
                      <div class="f2Val">{{ fmtN(r.f2) }}</div>
                      <div class="f3Val">{{ r.f3 > 0 ? '+' : '' }}{{ fmtN(r.f3) }}%</div>
                    </div>
                  </td>

                  <!-- 今日最新价与累计盈亏 (仅历史截面模式展示) -->
                  <td class="thRight" v-if="form.data_source === 'history'">
                    <div class="priceCell" :class="cls(r.holding_return)">
                      <div class="f2Val">{{ fmtN(r.latest_f2) }}</div>
                      <div class="f3Val">
                        <span class="retPill" :class="r.holding_return >= 0 ? 'retWin' : 'retLoss'">
                          {{ r.holding_return > 0 ? '+' : '' }}{{ fmtN(r.holding_return) }}%
                        </span>
                      </div>
                    </div>
                  </td>

                  <!-- 换手与量比 -->
                  <td>
                    <div class="tovCell">
                      <div>换手 <b>{{ fmtN(r.f8) }}%</b></div>
                      <div class="dimTxt">量比 {{ fmtN(r.f10) }}</div>
                    </div>
                  </td>

                  <!-- 成交额与主力净流入 -->
                  <td>
                    <div class="capCell">
                      <div>成交 {{ fmtYiT(r.f6) }}</div>
                      <div :class="cls(r.f62)">主力 {{ fmtYiT(r.f62) }}</div>
                    </div>
                  </td>

                  <!-- 模型拟合度评分 -->
                  <td>
                    <div class="confCell">
                      <div class="confRow">
                        <span class="confNum">{{ r.confidence }}%</span>
                        <span class="gradeTag" :class="'g-' + r.grade">
                          {{ r.grade }} · {{ r.grade_desc }}
                        </span>
                      </div>
                      <div class="confBarTrack">
                        <div
                          class="confBarFill"
                          :class="'bar-' + r.grade"
                          :style="{ width: r.confidence + '%' }"
                        ></div>
                      </div>
                    </div>
                  </td>

                  <!-- 特征归因 -->
                  <td>
                    <div class="attrCell">
                      <div class="attrTitle">
                        <ThunderboltFilled class="attrIco" />
                        <span>{{ r.attribution.summary }}</span>
                      </div>
                      <div class="attrBar">
                        <div
                          class="seg segCap"
                          :style="{ width: r.attribution.capital + '%' }"
                          :title="'主力合力: ' + r.attribution.capital + '%'"
                        ></div>
                        <div
                          class="seg segMom"
                          :style="{ width: r.attribution.momentum + '%' }"
                          :title="'势能突破: ' + r.attribution.momentum + '%'"
                        ></div>
                        <div
                          class="seg segLiq"
                          :style="{ width: r.attribution.liquidity + '%' }"
                          :title="'活跃流动: ' + r.attribution.liquidity + '%'"
                        ></div>
                        <div
                          class="seg segEla"
                          :style="{ width: r.attribution.elasticity + '%' }"
                          :title="'筹码弹性: ' + r.attribution.elasticity + '%'"
                        ></div>
                      </div>
                      <div class="attrPills">
                        <span>资金 {{ r.attribution.capital }}%</span>
                        <span>动能 {{ r.attribution.momentum }}%</span>
                        <span>换手 {{ r.attribution.liquidity }}%</span>
                      </div>
                    </div>
                  </td>

                  <!-- 操作快捷入口 -->
                  <td class="thCenter">
                    <div class="rowActions">
                      <button class="actBtn anaBtn" @click.stop="openAnalysis(r.code)">分析</button>
                      <button
                        class="actBtn watchBtn"
                        :class="{ isWatched: inWatch(r.code) }"
                        :title="inWatch(r.code) ? '已加自选，点击移除' : '加入自选'"
                        @click.stop="handleToggleWatch(r.code)"
                      >
                        {{ inWatch(r.code) ? '★' : '☆' }}
                      </button>
                      <a :href="quoteUrl(r.code)" target="_blank" class="extBtn" title="查看行情" @click.stop>
                        <ExportOutlined />
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>

            <!-- 空结果提示 -->
            <div v-else class="nlEmptyBox">
              <div class="emptyIcon">🔍</div>
              <div class="emptyTitle">
                {{ loading ? '神经网络前向特征推导中，请稍候...' : '当前过滤条件下未找到符合约束的个股' }}
              </div>
              <div class="emptyDesc" v-if="!loading">
                建议切换为「⚡ 今日盘中实时」或放宽换手/成交额门槛：
              </div>
              <div class="emptyActions" v-if="!loading">
                <button class="emptyBtn primary" @click="switchDataSource('latest')">
                  ⚡ 切换为今日盘中实时 (5,916 标的)
                </button>
                <button class="emptyBtn" @click="relaxFilters">
                  ⚡ 放宽门槛并重新计算
                </button>
              </div>
            </div>

            <!-- 分页条 -->
            <div class="nlPagination" v-if="filteredPredictions.length > pageSize">
              <span class="pgInfo">
                第 {{ curPage }} / {{ totalPages }} 页 · 共 {{ filteredPredictions.length }} 只标的
              </span>
              <div class="pgBtns">
                <button class="pgBtn" :disabled="curPage <= 1" @click="curPage--">上一页</button>
                <button class="pgBtn" :disabled="curPage >= totalPages" @click="curPage++">下一页</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 场景 B：历史回测调参验证看板卡片 (回测绩效仪表盘 + 收益明细) -->
        <div class="cockpitCard predictionsCard" v-else>
          <div class="predCardHeader">
            <div class="predTitleBox">
              <div class="predMainTitle">
                <RocketOutlined />
                <span>历史回测与调参验证仪表盘</span>
                <span class="resCountBadge" v-if="backtestMeta">基准日: {{ backtestMeta.base_date }}</span>
              </div>
              <div class="predSubTip">
                在历史基准日（如 {{ backtestBaseDate }}）按当前权重公式模拟选股，跟踪至今日真实盈亏与胜率，用于验证调参科学性
              </div>
            </div>

            <!-- 回测盈亏过滤药丸 -->
            <div class="gradeFilters" v-if="backtestResults.length > 0">
              <button
                class="gradeFilterBtn"
                :class="{ active: selectedBacktestFilter === 'ALL' }"
                @click="selectedBacktestFilter = 'ALL'"
              >
                全部标的 ({{ backtestResults.length }})
              </button>
              <button
                class="gradeFilterBtn gradeAplus"
                :class="{ active: selectedBacktestFilter === 'WIN' }"
                @click="selectedBacktestFilter = 'WIN'"
              >
                盈利标的 ({{ backtestMeta?.win_count || 0 }})
              </button>
              <button
                class="gradeFilterBtn gradeAplusplus"
                :class="{ active: selectedBacktestFilter === 'LOSS' }"
                @click="selectedBacktestFilter = 'LOSS'"
              >
                亏损标的 ({{ backtestMeta?.loss_count || 0 }})
              </button>
            </div>
          </div>

          <!-- 收益区间分布微型胶囊条 -->
          <div class="btDistBar" v-if="backtestMeta?.distribution">
            <span class="distLabel">收益分布:</span>
            <span class="distTag bigGain">大涨≥10%: {{ backtestMeta.distribution.big_gain }}只</span>
            <span class="distTag midGain">上涨3%~10%: {{ backtestMeta.distribution.mid_gain }}只</span>
            <span class="distTag smallGain">微涨0%~3%: {{ backtestMeta.distribution.small_gain }}只</span>
            <span class="distTag smallLoss">微跌-3%~0%: {{ backtestMeta.distribution.small_loss }}只</span>
            <span class="distTag midLoss">下跌-10%~-3%: {{ backtestMeta.distribution.mid_loss }}只</span>
            <span class="distTag bigLoss">大跌<-10%: {{ backtestMeta.distribution.big_loss }}只</span>
          </div>

          <!-- 回测结果原生明细表格 -->
          <div class="nlTableWrap" :class="{ loading: backtestLoading }">
            <table v-if="paginatedBacktestResults.length" class="nlTable">
              <thead>
                <tr>
                  <th class="thCenter" style="width: 42px">排名</th>
                  <th style="width: 130px">股票标的</th>
                  <th class="thRight" style="width: 96px">基准日选出价</th>
                  <th class="thRight" style="width: 96px">最新现价</th>
                  <th class="thRight" style="width: 100px">回测收益率</th>
                  <th style="width: 80px" class="thCenter">实盘检验</th>
                  <th style="width: 120px">当时拟合度</th>
                  <th style="min-width: 140px">当时驱动因素</th>
                  <th class="thCenter" style="width: 96px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in paginatedBacktestResults" :key="r.code" class="nlRow">
                  <td class="thCenter">
                    <span class="rankBadge" :class="'rank-' + r.rank">{{ r.rank }}</span>
                  </td>
                  <td>
                    <div class="stockCell">
                      <div class="stockMain">
                        <a class="stockCode" @click.stop="openAnalysis(r.code)">{{ r.code }}</a>
                        <span class="stockName" @click.stop="openAnalysis(r.code)">{{ r.name }}</span>
                      </div>
                      <div class="stockSub">
                        <span class="industryTag">{{ r.industry || '综合' }}</span>
                        <span class="marketTag">{{ r.market }}</span>
                      </div>
                    </div>
                  </td>
                  <!-- 基准日选出价 -->
                  <td class="thRight">
                    <div class="f2Val">{{ fmtN(r.entry_price) }}</div>
                    <div class="dimTxt" style="font-size: 10px">{{ r.base_date }}</div>
                  </td>
                  <!-- 今日最新价 -->
                  <td class="thRight">
                    <div class="f2Val">{{ fmtN(r.latest_price) }}</div>
                    <div class="dimTxt" style="font-size: 10px">今日盘中实时</div>
                  </td>
                  <!-- 回测收益率 -->
                  <td class="thRight">
                    <span class="retPill" :class="r.is_win ? 'retWin' : 'retLoss'">
                      {{ r.return_pct > 0 ? '+' : '' }}{{ fmtN(r.return_pct) }}%
                    </span>
                  </td>
                  <!-- 胜负标签 -->
                  <td class="thCenter">
                    <span class="winBadge" :class="r.is_win ? 'wbWin' : 'wbLoss'">
                      {{ r.is_win ? '✓ 盈利' : '✕ 亏损' }}
                    </span>
                  </td>
                  <!-- 拟合度 -->
                  <td>
                    <div class="confCell">
                      <div class="confRow">
                        <span class="confNum">{{ r.confidence }}%</span>
                        <span class="gradeTag" :class="'g-' + r.grade">{{ r.grade }}</span>
                      </div>
                    </div>
                  </td>
                  <!-- 归因 -->
                  <td>
                    <div class="attrCell">
                      <div class="attrTitle">
                        <ThunderboltFilled class="attrIco" />
                        <span>{{ r.attribution.summary }}</span>
                      </div>
                    </div>
                  </td>
                  <!-- 操作 -->
                  <td class="thCenter">
                    <div class="rowActions">
                      <button class="actBtn anaBtn" @click.stop="openAnalysis(r.code)">分析</button>
                      <button
                        class="actBtn watchBtn"
                        :class="{ isWatched: inWatch(r.code) }"
                        @click.stop="handleToggleWatch(r.code)"
                      >
                        {{ inWatch(r.code) ? '★' : '☆' }}
                      </button>
                      <a :href="quoteUrl(r.code)" target="_blank" class="extBtn" title="查看行情" @click.stop>
                        <ExportOutlined />
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>

            <!-- 空结果提示 -->
            <div v-else class="nlEmptyBox">
              <div class="emptyIcon">📊</div>
              <div class="emptyTitle">
                {{ backtestLoading ? '正在执行历史模拟选股与跨周期跟踪...' : '点击上方「运行历史回测验证」查看参数实战表现' }}
              </div>
            </div>

            <!-- 分页 -->
            <div class="nlPagination" v-if="filteredBacktestResults.length > btPageSize">
              <span class="pgInfo">
                第 {{ curBtPage }} / {{ totalBtPages }} 页 · 共 {{ filteredBacktestResults.length }} 只标的
              </span>
              <div class="pgBtns">
                <button class="pgBtn" :disabled="curBtPage <= 1" @click="curBtPage--">上一页</button>
                <button class="pgBtn" :disabled="curBtPage >= totalBtPages" @click="curBtPage++">下一页</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 个股穿透诊断弹窗 -->
    <AnalysisModal ref="anaModalRef" :rows="activeMode === 'predict' ? predictions : backtestResults" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from "vue";
import { message } from "ant-design-vue";
import {
  Slider as ASlider,
  Switch as ASwitch,
  RadioGroup as ARadioGroup,
  RadioButton as ARadioButton,
  InputNumber as AInputNumber,
  CheckboxGroup as ACheckboxGroup,
  Spin as ASpin,
} from "ant-design-vue";
import {
  ThunderboltOutlined,
  ThunderboltFilled,
  ExperimentOutlined,
  ApartmentOutlined,
  ControlOutlined,
  FilterOutlined,
  DeploymentUnitOutlined,
  CodeOutlined,
  RocketOutlined,
  ExportOutlined,
} from "@ant-design/icons-vue";
import { api, track } from "../api/client";
import { fmtN, fmtYiT, cls, quoteUrl } from "../utils/format";
import { inWatch, toggleWatch, loadWatchCodes } from "../stores/watchlist";
import AnalysisModal from "../analysis/AnalysisModal.vue";

// 模式控制：'predict' (实时推理) vs 'backtest' (历史回测验证)
const activeMode = ref("predict");

// 推理进行中（驱动拓扑图前向传播动画）
const inferring = computed(() => loading.value || backtestLoading.value);

// 可用交易日期元数据 (从 /api/neural/dates 获取)
const availableDates = ref({ latest: null, history_dates: [] });
const backtestBaseDate = ref("2026-09-18");

// 市场板块多选选项
const MARKET_OPTIONS = [
  { label: "沪主板", value: "沪主板" },
  { label: "深主板", value: "深主板" },
  { label: "创业板", value: "创业板" },
  { label: "科创板", value: "科创板" },
  { label: "北交所", value: "北交所" },
];

// 经典模型策略预设库
const PRESETS = [
  {
    id: "hot_money",
    name: "游资接力模型",
    tag: "高换手·高量比·中小盘",
    icon: "🔥",
    weights: {
      weight_turnover: 85,
      weight_capital: 65,
      weight_volume_ratio: 80,
      weight_momentum: 75,
      weight_auction_gap: 60,
      weight_amplitude: 40,
      weight_trend_60d: 20,
      weight_market_cap: -45,
    },
    hyperparams: {
      activation: "gelu",
      temperature: 0.7,
      stagflation_penalty: true,
    },
  },
  {
    id: "smart_money",
    name: "主力潜伏模型",
    tag: "大单流入·低位蓄势",
    icon: "🛡️",
    weights: {
      weight_turnover: 35,
      weight_capital: 95,
      weight_volume_ratio: 25,
      weight_momentum: -15, // 偏好尚未爆拉暴涨的低位蓄势票
      weight_auction_gap: -10,
      weight_amplitude: -20,
      weight_trend_60d: 15,
      weight_market_cap: 10,
    },
    hyperparams: {
      activation: "tanh",
      temperature: 0.85,
      stagflation_penalty: false,
    },
  },
  {
    id: "bottom_breakout",
    name: "底部突破模型",
    tag: "超跌横盘·放量拐点",
    icon: "⚡",
    weights: {
      weight_turnover: 60,
      weight_capital: 75,
      weight_volume_ratio: 95,
      weight_momentum: 45,
      weight_auction_gap: 30,
      weight_amplitude: 50,
      weight_trend_60d: -40, // 偏好前期超跌处于低位
      weight_market_cap: -25,
    },
    hyperparams: {
      activation: "leaky_relu",
      temperature: 0.75,
      stagflation_penalty: true,
    },
  },
  {
    id: "dragon_leader",
    name: "龙头高标主升",
    tag: "极强动能·强趋势辨识",
    icon: "👑",
    weights: {
      weight_turnover: 70,
      weight_capital: 80,
      weight_volume_ratio: 60,
      weight_momentum: 95,
      weight_auction_gap: 70,
      weight_amplitude: 35,
      weight_trend_60d: 85,
      weight_market_cap: -15,
    },
    hyperparams: {
      activation: "gelu",
      temperature: 0.6,
      stagflation_penalty: true,
    },
  },
  {
    id: "custom",
    name: "自定义实验",
    tag: "自由调参",
    icon: "⚙️",
    weights: {},
    hyperparams: {},
  },
];

const currentPreset = ref("hot_money");

// 表单响应式数据：默认今日实时，确保价格涨跌100%最新准确！
const form = reactive({
  // 刚性约束
  exclude_st: true,
  exclude_suspended: true,
  min_turnover: 0.5,
  max_turnover: 80.0,
  min_amount_yi: 0.1,
  min_price: 1.0,
  max_price: 1000.0,
  min_market_cap_yi: 3.0,
  max_market_cap_yi: 5000.0,
  markets: ["沪主板", "深主板", "创业板", "科创板", "北交所"],

  // 突触权重
  weight_turnover: 85,
  weight_capital: 65,
  weight_volume_ratio: 80,
  weight_momentum: 75,
  weight_auction_gap: 60,
  weight_amplitude: 40,
  weight_trend_60d: 20,
  weight_market_cap: -45,

  // 隐层偏置
  hidden_liquidity_bias: 0.0,
  hidden_capital_bias: 0.0,
  hidden_momentum_bias: 0.0,
  hidden_elasticity_bias: 0.0,

  // 超参数
  activation: "gelu",
  temperature: 0.7,
  stagflation_penalty: true,
  top_k: 30,               // 与回测寻优训练口径一致
  data_source: "latest", // 默认今日盘中实时！
  trade_date: "",        // 指定历史日期
});

const loading = ref(false);
const telemetryMeta = ref(null);
const telemetrySteps = ref([]);
const predictions = ref([]);
const selectedGradeFilter = ref("ALL");

// 回测状态数据
const backtestLoading = ref(false);
const backtestMeta = ref(null);
const backtestResults = ref([]);
const selectedBacktestFilter = ref("ALL");

// 分页 (推理模式)
const curPage = ref(1);
const pageSize = 20;

// 分页 (回测模式)
const curBtPage = ref(1);
const btPageSize = 20;

// 分析弹窗引用
const anaModalRef = ref(null);
function openAnalysis(code) {
  track("neural_stock_analysis", code);
  if (anaModalRef.value) {
    anaModalRef.value.open(code);
  }
}

// 加自选
async function handleToggleWatch(code) {
  const willAdd = !inWatch(code);
  try {
    await toggleWatch(code, willAdd);
    message.success(willAdd ? "已添加到自选股" : "已从自选股移除");
  } catch (err) {
    message.error("操作自选失败: " + err.message);
  }
}

// 权重展示色彩
function weightValClass(v) {
  if (v > 50) return "highPos";
  if (v > 0) return "midPos";
  if (v < -30) return "highNeg";
  if (v < 0) return "midNeg";
  return "zeroVal";
}

// 切换模式
function switchMode(m) {
  activeMode.value = m;
  if (m === "backtest" && !backtestMeta.value) {
    runBacktest();
  }
}

// 切换数据源
function switchDataSource(src) {
  form.data_source = src;
  runInference();
}

// 放宽门槛
function relaxFilters() {
  form.min_turnover = 0.0;
  form.min_amount_yi = 0.0;
  form.min_market_cap_yi = 0.0;
  message.info({ content: "已放宽换手率与成交额门槛", key: "filter" });
  if (activeMode.value === "predict") {
    runInference();
  } else {
    runBacktest();
  }
}

// 应用预设
function applyPreset(p) {
  currentPreset.value = p.id;
  if (p.id === "custom") return;
  Object.assign(form, p.weights);
  Object.assign(form, p.hyperparams);
  message.info({ content: `已载入「${p.name}」模型参数`, key: "preset" });
  if (activeMode.value === "predict") {
    runInference();
  } else {
    runBacktest();
  }
}

function onWeightChange() {
  currentPreset.value = "custom";
}

function resetToDefault() {
  applyPreset(PRESETS[0]);
}

// 等级筛选与统计 (推理模式)
const filteredPredictions = computed(() => {
  if (selectedGradeFilter.value === "ALL") return predictions.value;
  return predictions.value.filter((p) => p.grade === selectedGradeFilter.value);
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredPredictions.value.length / pageSize)));

const paginatedPredictions = computed(() => {
  const start = (curPage.value - 1) * pageSize;
  return filteredPredictions.value.slice(start, start + pageSize);
});

function gradeCount(g) {
  return predictions.value.filter((p) => p.grade === g).length;
}

// 过滤与分页 (回测模式)
const filteredBacktestResults = computed(() => {
  if (selectedBacktestFilter.value === "WIN") return backtestResults.value.filter((r) => r.is_win);
  if (selectedBacktestFilter.value === "LOSS") return backtestResults.value.filter((r) => !r.is_win);
  return backtestResults.value;
});

const totalBtPages = computed(() => Math.max(1, Math.ceil(filteredBacktestResults.value.length / btPageSize)));

const paginatedBacktestResults = computed(() => {
  const start = (curBtPage.value - 1) * btPageSize;
  return filteredBacktestResults.value.slice(start, start + btPageSize);
});

// 加载可用历史日期
async function loadAvailableDates() {
  try {
    const res = await api("/api/neural/dates");
    availableDates.value = res;
    if (res.history_dates && res.history_dates.length > 0) {
      if (!form.trade_date) {
        form.trade_date = res.history_dates[0].date;
      }
      if (!backtestBaseDate.value) {
        backtestBaseDate.value = res.history_dates[0].date;
      }
    }
  } catch (err) {
    console.error("加载日期元数据失败:", err);
  }
}

// 执行前向推理
async function runInference() {
  loading.value = true;
  curPage.value = 1;
  try {
    const res = await api("/api/neural/predict", {
      method: "POST",
      body: form,
    });

    telemetryMeta.value = {
      dataMode: res.data_mode,
      tradeDate: res.trade_date,
      totalScanned: res.total_scanned,
      qualifiedCount: res.qualified_count,
      inferenceTimeMs: res.inference_time_ms,
    };
    telemetrySteps.value = res.telemetry || [];
    predictions.value = res.results || [];
    track("neural_inference_run", `${currentPreset.value} -> ${predictions.value.length} items`);
  } catch (err) {
    if (err.message !== "unauthorized") {
      message.error("神经网络推理失败: " + (err.message || "请求异常"));
    }
  } finally {
    loading.value = false;
  }
}

// 执行历史回测调参验证
async function runBacktest() {
  backtestLoading.value = true;
  curBtPage.value = 1;
  try {
    const payload = {
      ...form,
      base_date: backtestBaseDate.value,
    };
    const res = await api("/api/neural/backtest", {
      method: "POST",
      body: payload,
    });

    backtestMeta.value = res;
    backtestResults.value = res.results || [];
    track("neural_backtest_run", `${backtestBaseDate.value} -> win ${res.win_rate}%`);
    message.success({
      content: `历史回测完成！样本胜率: ${res.win_rate}%, 平均收益: ${res.avg_return > 0 ? '+' : ''}${res.avg_return}%`,
      key: "bt",
    });
  } catch (err) {
    if (err.message !== "unauthorized") {
      message.error("历史回测失败: " + (err.message || "请求异常"));
    }
  } finally {
    backtestLoading.value = false;
  }
}

// 神经网络 SVG 拓扑图坐标与突触计算
const inputNodesCoords = computed(() => {
  const names = [
    { id: "turnover", name: "换手率", val: form.weight_turnover },
    { id: "capital", name: "主力合力", val: form.weight_capital },
    { id: "volratio", name: "量比爆发", val: form.weight_volume_ratio },
    { id: "momentum", name: "当日涨幅", val: form.weight_momentum },
    { id: "gap", name: "竞价跳空", val: form.weight_auction_gap },
    { id: "amplitude", name: "振幅博弈", val: form.weight_amplitude },
    { id: "trend", name: "60日趋势", val: form.weight_trend_60d },
    { id: "mcap", name: "规模偏好", val: form.weight_market_cap },
  ];
  const startY = 16;
  const gapY = 20;
  return names.map((item, idx) => ({
    ...item,
    x: 95,
    y: startY + idx * gapY,
    active: Math.abs(item.val) > 20,
    weightVal: (item.val > 0 ? "+" : "") + item.val,
  }));
});

const latentNodesCoords = computed(() => {
  const latents = [
    { id: "h_liq", symbol: "H1", name: "流动性" },
    { id: "h_cap", symbol: "H2", name: "主力合力" },
    { id: "h_mom", symbol: "H3", name: "势能突破" },
    { id: "h_ela", symbol: "H4", name: "筹码弹性" },
  ];
  const startY = 25;
  const gapY = 38;
  return latents.map((item, idx) => ({
    ...item,
    x: 285,
    y: startY + idx * gapY,
  }));
});

const activationNodeCoord = { x: 445, y: 85 };
const outputNodeCoord = { x: 575, y: 85 };

// 计算动态突触路径
const synapseConnections = computed(() => {
  const lines = [];
  const inCoords = inputNodesCoords.value;
  const latCoords = latentNodesCoords.value;

  inCoords.forEach((inNode, i) => {
    latCoords.forEach((latNode, j) => {
      const isStrong = (i % 2 === j % 2);
      const w = Math.abs(inNode.val);
      if (w < 10 && !isStrong) return;

      const path = `M ${inNode.x + 8} ${inNode.y} C ${inNode.x + 75} ${inNode.y}, ${latNode.x - 75} ${latNode.y}, ${latNode.x - 11} ${latNode.y}`;
      let color = "rgba(148, 163, 184, 0.35)";
      let width = 1;
      let dash = "none";
      if (inNode.val > 50) {
        color = "#f59e0b";
        width = 2.0;
      } else if (inNode.val > 0) {
        color = "#10b981";
        width = 1.3;
      } else if (inNode.val < -20) {
        color = "#06b6d4";
        width = 1.3;
        dash = "3,3";
      }

      lines.push({ path, color, width, dash, active: w > 40 });
    });
  });

  latCoords.forEach((latNode) => {
    const path = `M ${latNode.x + 11} ${latNode.y} C ${latNode.x + 55} ${latNode.y}, ${activationNodeCoord.x - 55} ${activationNodeCoord.y}, ${activationNodeCoord.x - 22} ${activationNodeCoord.y}`;
    lines.push({ path, color: "#818cf8", width: 1.8, dash: "none", active: true });
  });

  lines.push({
    path: `M ${activationNodeCoord.x + 22} ${activationNodeCoord.y} C ${activationNodeCoord.x + 45} ${activationNodeCoord.y}, ${outputNodeCoord.x - 45} ${outputNodeCoord.y}, ${outputNodeCoord.x - 14} ${outputNodeCoord.y}`,
    color: "#f59e0b",
    width: 2.4,
    dash: "none",
    active: true,
  });

  return lines;
});

// 快捷键支持 Ctrl+Enter
function onKeyDown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    if (activeMode.value === "predict") {
      runInference();
    } else {
      runBacktest();
    }
  }
}

// ===== 回测寻优（后端在全部历史截面上真实搜索最优权重） =====
const optLoading = ref(false);
const optimizeResult = ref(null);

const OPT_WEIGHT_LABELS = [
  ["weight_turnover", "换手活跃度"],
  ["weight_capital", "主力合力"],
  ["weight_volume_ratio", "量比爆发"],
  ["weight_momentum", "当日动能"],
  ["weight_auction_gap", "竞价跳空"],
  ["weight_amplitude", "振幅博弈"],
  ["weight_trend_60d", "60日趋势"],
  ["weight_market_cap", "规模偏好"],
];

const optimizeWeightBars = computed(() => {
  if (!optimizeResult.value) return [];
  const w = optimizeResult.value.best.weights;
  return OPT_WEIGHT_LABELS.map(([k, label]) => ({ name: k, label, value: w[k] }));
});

// 当前参数是否即为回测最优（默认参数已自动设为最优）
const isOptimizedApplied = computed(() => {
  if (!optimizeResult.value) return false;
  const w = optimizeResult.value.best.weights;
  return OPT_WEIGHT_LABELS.every(([k]) => Math.abs((form[k] || 0) - w[k]) < 0.01);
});

async function runOptimize(force = false) {
  optLoading.value = true;
  try {
    const res = await api("/api/neural/optimize", {
      method: "POST",
      body: { top_k: 30, samples: 2000, force },
    });
    optimizeResult.value = res;
    if (force) {
      message.success({
        content: `寻优完成：平均胜率 ${res.best.win_rate}%，Alpha ${res.best.alpha > 0 ? "+" : ""}${res.best.alpha}%`,
        key: "opt",
      });
    }
  } catch (err) {
    if (err.message !== "unauthorized") {
      message.error("回测寻优失败: " + (err.message || "请求异常"));
    }
  } finally {
    optLoading.value = false;
  }
}

function applyOptimized() {
  if (!optimizeResult.value) return;
  Object.assign(form, optimizeResult.value.best.weights);
  if (optimizeResult.value.best.activation) {
    form.activation = optimizeResult.value.best.activation;
  }
  currentPreset.value = "custom";
  message.success({ content: "已应用回测最优参数", key: "preset" });
  if (activeMode.value === "predict") {
    runInference();
  } else {
    runBacktest();
  }
}

onMounted(async () => {
  loadWatchCodes();
  await loadAvailableDates();
  // 先取回测寻优结果，把经历史截面验证的最优参数设为默认，再做首次推理
  await runOptimize(false);
  if (optimizeResult.value) {
    Object.assign(form, optimizeResult.value.best.weights);
    if (optimizeResult.value.best.activation) {
      form.activation = optimizeResult.value.best.activation;
    }
    currentPreset.value = "custom";
  }
  runInference();
  window.addEventListener("keydown", onKeyDown);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeyDown);
});
</script>

<style scoped>
/* 整个页面根节点：外层锁死不出现任何滚动条，100% 贴合窗口 */
.neuralLabRoot {
  flex: 1;
  min-height: 0;
  max-height: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  background: var(--bg);
  color: var(--txt);
  box-sizing: border-box;
}

/* ===== 1. 顶部状态与工具栏 ===== */
.nlHeader {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 5px 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.nlTitleBox {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nlMainTitle {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nlTitleIcon {
  font-size: 17px;
  line-height: 1;
}

.nlTitleText {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.2px;
  color: var(--txt);
}

.nlVersionBadge {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  font-weight: 600;
  line-height: 1.2;
}

/* 模式切换器 */
.modeSwitcher {
  display: inline-flex;
  padding: 2px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  gap: 2px;
}

.modeTabBtn {
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 11.5px;
  padding: 2px 9px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.modeTabBtn.active {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.nlHeaderRight {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 分段切换按钮 */
.sourceToggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
}

.sourceLabel {
  color: var(--dim);
  font-size: 11px;
}

.segmentedBtns {
  display: inline-flex;
  padding: 2px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
}

.segBtn {
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.segBtn.active {
  background: var(--panel);
  color: var(--txt);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.dateSelect {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--txt);
  font-size: 11px;
  padding: 2px 6px;
  cursor: pointer;
  outline: none;
}

.dateSelect:focus {
  border-color: var(--accent);
}

.btTargetTip {
  font-size: 10.5px;
  color: var(--dim);
}

.nlActions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nlRunBtnCompact {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 2px 6px rgba(124, 58, 237, 0.25);
  transition: opacity 0.15s, transform 0.1s;
}

.nlRunBtnCompact.btRunBtn {
  background: linear-gradient(135deg, #059669, #10b981);
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.25);
}

.nlRunBtnCompact:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
}

.nlRunBtnCompact:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.nlResetBtnCompact {
  height: 28px;
  padding: 0 9px;
  font-size: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s;
}

.nlResetBtnCompact:hover {
  color: var(--txt);
  border-color: var(--dim);
}

/* ===== 2. 醒目合规与风险提示条 ===== */
.nlComplianceBanner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.28);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.4;
  color: #b45309;
}

[data-theme="dark"] .nlComplianceBanner {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.35);
  color: #fcd34d;
}

.bannerIcon {
  font-size: 13px;
  flex-shrink: 0;
}

.bannerText {
  flex: 1;
}

.bannerText b {
  font-weight: 700;
}

/* ===== 3. 模型预设快捷条 ===== */
.nlPresetsBar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}

.presetLabel {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--dim);
  white-space: nowrap;
}

.presetButtons {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.presetBtn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--txt);
  font-size: 11.5px;
  line-height: 1.3;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.presetBtn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.presetBtn.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}

.presetTag {
  font-size: 9.5px;
  color: var(--dim);
  background: var(--panel);
  padding: 1px 4px;
  border-radius: 3px;
}

.metaPillsInline {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--dim);
  white-space: nowrap;
}

.mPill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.mDot {
  width: 6px;
  height: 6px;
  background: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 5px #10b981;
}

/* ===== 4. 核心工作区网格：左参数 + 右（拓扑/思考流/结果） ===== */
.nlMainGrid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 250px 1fr;
  gap: 10px;
  overflow: hidden;
}

@media (max-width: 1200px) {
  .nlMainGrid {
    grid-template-columns: 235px 1fr;
  }
}

/* 左侧驾驶舱：内部纵向滚动 */
.nlLeftCol {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 4px;
}

.nlLeftCol::-webkit-scrollbar {
  width: 5px;
}
.nlLeftCol::-webkit-scrollbar-thumb {
  background: var(--line-strong, #cbd5e1);
  border-radius: 4px;
}

.cockpitCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.cardHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding-bottom: 5px;
  border-bottom: 1px solid var(--line);
}

.cardTitle {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--txt);
  display: flex;
  align-items: center;
  gap: 5px;
}

.cardTip {
  font-size: 10.5px;
  color: var(--dim);
}

.relaxBtn {
  font-size: 11px;
  padding: 0;
  height: auto;
}

/* 权重滑块 */
.sliderGroup {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sliderItem {
  display: flex;
  flex-direction: column;
}

.sliderLabelRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11.5px;
}

.factorName {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--txt);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.turnoverDot { background: #10b981; }
.capitalDot { background: #f59e0b; }
.volratioDot { background: #06b6d4; }
.momentumDot { background: #ef4444; }
.gapDot { background: #a855f7; }
.ampDot { background: #ec4899; }
.trendDot { background: #3b82f6; }
.mcapDot { background: #14b8a6; }

.sliderVal {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 3px;
}
.highPos { color: #059669; background: rgba(16, 185, 129, 0.12); }
.midPos { color: #10b981; background: rgba(16, 185, 129, 0.08); }
.highNeg { color: #0284c7; background: rgba(56, 189, 248, 0.12); }
.midNeg { color: #0ea5e9; background: rgba(56, 189, 248, 0.08); }
.zeroVal { color: var(--dim); background: var(--panel-2); }
.highlightVal { color: #d97706; background: rgba(245, 158, 11, 0.12); }

/* 超参部分 */
.hyperparamBody {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.paramRow {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.paramLabel {
  font-size: 10.5px;
  color: var(--dim);
}

.subInfo {
  font-size: 9px;
  color: var(--dim);
}

.switchRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 7px;
  background: var(--panel-2);
  border-radius: 6px;
  border: 1px solid var(--line);
}

.switchLabel {
  display: flex;
  flex-direction: column;
}

.swTitle {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--txt);
}

.swDesc {
  font-size: 9px;
  color: var(--dim);
}

/* 过滤约束 */
.filterBody {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.switchesGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.switchMini {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  color: var(--txt);
}

.rangeRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.fLabel {
  font-size: 10.5px;
  color: var(--dim);
}

.rangeInputs {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sep {
  color: var(--dim);
  font-size: 11px;
}

.marketCheckboxes {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

/* ===== 5. 右侧工作区：拓扑 + 思考流（顶部并排） + 优选/回测榜单 ===== */
.nlRightCol {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nlTopTwinCards {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

@media (max-width: 1400px) {
  .nlTopTwinCards {
    grid-template-columns: 1fr;
  }
}

.twinCard {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
}

.topologyLegends {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  color: var(--dim);
}

.legItem {
  display: flex;
  align-items: center;
  gap: 3px;
}

.legDot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.dotInput { background: #10b981; }
.dotLatent { background: #6366f1; }
.dotAct { background: #ec4899; }
.dotOut { background: #f59e0b; }

.topologyCanvasWrapper {
  width: 100%;
  height: 145px;
  position: relative;
  background: var(--panel-2);
  border-radius: 6px;
  border: 1px solid var(--line);
  overflow: hidden;
}

.topologySvg {
  width: 100%;
  height: 100%;
}

.svgLabel {
  font-size: 9px;
  fill: var(--txt);
  font-weight: 500;
}

.svgValText {
  font-size: 8.5px;
  fill: var(--dim);
  font-family: var(--mono);
}

.svgCoreCode {
  font-size: 8.5px;
  fill: var(--txt);
  font-weight: bold;
}

.svgSubLabel {
  font-size: 9px;
  fill: #6366f1;
  font-weight: 600;
}

.svgActText {
  font-size: 8px;
  fill: #fff;
  font-weight: bold;
}

.svgOutText {
  font-size: 9px;
  fill: var(--txt);
  font-weight: bold;
}

.svgOutSubText {
  font-size: 9px;
  fill: #d97706;
  font-weight: 600;
}

.synapsePath {
  transition: all 0.3s ease;
}

.synapsePath.pulsing {
  stroke-dasharray: 4, 4;
  animation: pulsePath 2s linear infinite;
}

@keyframes pulsePath {
  to {
    stroke-dashoffset: -28;
  }
}

/* 思考流日志 */
.telemetryStatus {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  color: #10b981;
}

.telemetryStatus.running {
  color: #f59e0b;
}

.statusDot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.telemetryConsole {
  height: 145px;
  overflow-y: auto;
  background: var(--panel-2);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: var(--mono);
  font-size: 10.5px;
  border: 1px solid var(--line);
}

.telemetryLoading {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--dim);
}

.telemetryLogs {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.logStepItem {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
  border-bottom: 1px dashed var(--line);
}

.logStepHeader {
  display: flex;
  align-items: center;
  gap: 5px;
}

.stepBadge {
  color: var(--accent);
  font-weight: bold;
  font-size: 10px;
}

.phaseName {
  color: var(--txt);
  font-weight: 600;
}

.stepMs {
  margin-left: auto;
  color: var(--dim);
  font-size: 9.5px;
}

.stepMsg {
  color: var(--dim);
  line-height: 1.3;
  padding-left: 4px;
}

/* ===== 6. 优选/回测榜单主卡片 ===== */
.predictionsCard {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px 12px;
}

.predCardHeader {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}

.predTitleBox {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.predMainTitle {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--txt);
  display: flex;
  align-items: center;
  gap: 6px;
}

.resCountBadge {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--accent-dim);
  color: var(--accent);
  border-radius: 999px;
  font-weight: 600;
}

.curSourceBadge {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--panel-2);
  color: var(--dim);
  border: 1px solid var(--line);
  border-radius: 4px;
}

.curSourceBadge.isLive {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border-color: rgba(16, 185, 129, 0.3);
}

.predSubTip {
  font-size: 11px;
  color: var(--dim);
}

.gradeFilters {
  display: flex;
  gap: 5px;
}

.gradeFilterBtn {
  font-size: 10.5px;
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--dim);
  cursor: pointer;
  transition: all 0.15s;
}

.gradeFilterBtn:hover {
  color: var(--txt);
}

.gradeFilterBtn.active {
  background: var(--panel);
  color: var(--txt);
  border-color: var(--accent);
  font-weight: 600;
}

.gradeFilterBtn.gradeAplusplus.active {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
  border-color: #a855f7;
}

.gradeFilterBtn.gradeAplus.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border-color: #10b981;
}

.btDistBar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.distLabel {
  color: var(--dim);
  font-weight: 600;
}

.distTag {
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 10px;
}
.bigGain { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.midGain { background: rgba(245, 158, 11, 0.15); color: #d97706; }
.smallGain { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.smallLoss { background: rgba(148, 163, 184, 0.15); color: var(--dim); }
.midLoss { background: rgba(2, 132, 199, 0.15); color: #0284c7; }
.bigLoss { background: rgba(59, 130, 246, 0.15); color: #2563eb; border: 1px solid rgba(59, 130, 246, 0.3); }

/* 原生表格容器：内部纵向 + 横向平滑滚动，表头吸顶 */
.nlTableWrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: var(--panel);
}

.nlTableWrap::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.nlTableWrap::-webkit-scrollbar-thumb {
  background: var(--line-strong, #cbd5e1);
  border-radius: 4px;
}

.nlTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  color: var(--txt);
}

.nlTable thead th {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--panel-2);
  padding: 5px 7px;
  font-weight: 600;
  color: var(--dim);
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}

.nlTable td {
  padding: 3px 7px;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}

.nlRow:hover td {
  background: var(--hover);
}

.thCenter { text-align: center !important; }
.thRight { text-align: right !important; }

/* 排名 */
.rankBadge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  background: var(--panel-2);
  color: var(--dim);
}
.rank-1 { background: #f59e0b; color: #fff; box-shadow: 0 0 5px rgba(245, 158, 11, 0.4); }
.rank-2 { background: #94a3b8; color: #fff; }
.rank-3 { background: #b45309; color: #fff; }

/* 股票 */
.stockCell {
  display: flex;
  flex-direction: column;
  gap: 0;
  white-space: nowrap;
}
.stockMain {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.stockCode {
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--accent);
  cursor: pointer;
  white-space: nowrap;
}
.stockName {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--txt);
  cursor: pointer;
  white-space: nowrap;
}
.stockName:hover, .stockCode:hover {
  text-decoration: underline;
}
.ztTag {
  font-size: 9.5px;
  padding: 0 3px;
  line-height: 14px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-radius: 3px;
}
.stockSub {
  display: flex;
  gap: 5px;
  font-size: 10.5px;
  color: var(--dim);
  white-space: nowrap;
}

/* 现价 */
.priceCell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-family: var(--mono);
}
.f2Val { font-size: 12.5px; font-weight: 700; }
.f3Val { font-size: 10.5px; font-weight: 600; }

.retPill {
  display: inline-block;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 700;
  font-size: 11px;
}
.retWin {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}
.retLoss {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.winBadge {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
}
.wbWin {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.wbLoss {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.tovCell, .capCell {
  font-size: 11.5px;
  display: flex;
  flex-direction: column;
  gap: 0;
  white-space: nowrap;
}

/* 拟合度 */
.confCell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.confRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  white-space: nowrap;
  gap: 4px;
}
.confNum {
  font-size: 12px;
  font-weight: 800;
  font-family: var(--mono);
  color: var(--txt);
}
.gradeTag {
  font-size: 9.5px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
}
.g-A\+\+ { background: rgba(168, 85, 247, 0.15); color: #a855f7; border: 1px solid rgba(168, 85, 247, 0.3); }
.g-A\+ { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
.g-A { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); }
.g-B\+ { background: rgba(148, 163, 184, 0.15); color: var(--dim); }

.confBarTrack {
  width: 100%;
  height: 4px;
  background: var(--panel-2);
  border-radius: 999px;
  overflow: hidden;
}
.confBarFill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.35s ease;
}
.bar-A\+\+ { background: linear-gradient(90deg, #8b5cf6, #d946ef); }
.bar-A\+ { background: linear-gradient(90deg, #10b981, #06b6d4); }
.bar-A { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-B\+ { background: #94a3b8; }

/* 归因 */
.attrCell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.attrTitle {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  font-weight: 600;
  color: #f59e0b;
  white-space: nowrap;
}
.attrIco { font-size: 9.5px; }

.attrBar {
  display: flex;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
  background: var(--panel-2);
}
.seg { height: 100%; }
.segCap { background: #f59e0b; }
.segMom { background: #ef4444; }
.segLiq { background: #10b981; }
.segEla { background: #06b6d4; }

.attrPills {
  display: flex;
  gap: 5px;
  font-size: 9.5px;
  color: var(--dim);
}

/* 行操作 */
.rowActions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  white-space: nowrap;
}
.actBtn {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--txt);
  cursor: pointer;
  transition: all 0.15s;
}
.actBtn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.anaBtn {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.anaBtn:hover {
  background: #2563eb;
  color: #fff;
}
.watchBtn.isWatched {
  color: #f59e0b;
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}
.extBtn {
  color: var(--dim);
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  padding: 1px;
}
.extBtn:hover {
  color: var(--accent);
}

/* 空状态 */
.nlEmptyBox {
  padding: 30px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--dim);
  text-align: center;
}
.emptyIcon { font-size: 28px; }
.emptyTitle { font-size: 13px; font-weight: 600; color: var(--txt); }
.emptyDesc { font-size: 11.5px; max-width: 440px; }
.emptyActions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.emptyBtn {
  padding: 4px 12px;
  border-radius: 5px;
  font-size: 11.5px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--txt);
  cursor: pointer;
}
.emptyBtn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

/* 分页 */
.nlPagination {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--dim);
  border-top: 1px solid var(--line);
}
.pgBtns { display: flex; gap: 5px; }
.pgBtn {
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--txt);
  cursor: pointer;
  font-size: 11px;
}
.pgBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 涨跌颜色变量适配 */
.up { color: var(--up) !important; }
.down { color: var(--down) !important; }
.dimTxt { color: var(--dim); }

/* ===== 前向传播推理动画 ===== */
.topologySvg.inferring .synapsePath {
  stroke-dasharray: 5 7;
  animation: synFlow 0.7s linear infinite;
}

@keyframes synFlow {
  to { stroke-dashoffset: -24; }
}

.signalParticles .particle {
  fill: #f59e0b;
  filter: drop-shadow(0 0 3px rgba(245, 158, 11, 0.9));
}

.topologySvg.inferring .nodeGroup > circle:first-child {
  animation: nodePulse 1.1s ease-in-out infinite;
}

@keyframes nodePulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ===== 思考流：终端风格 + 分步浮现 ===== */
.telemetryConsole {
  background: linear-gradient(180deg, #0d1524, #0a101c);
  border-color: #1e2a3d;
}

.telemetryConsole .phaseName { color: #e2e8f0; }
.telemetryConsole .stepMsg { color: #8fa3bd; }
.telemetryConsole .stepBadge { color: #38bdf8; }
.telemetryConsole .stepMs { color: #64748b; }
.telemetryConsole .logStepItem { border-bottom-color: rgba(148, 163, 184, 0.18); }
.telemetryConsole .tLoadTxt { color: #8fa3bd; }

.logStepItem {
  animation: stepIn 0.35s ease both;
}
.logStepItem:nth-child(2) { animation-delay: 0.08s; }
.logStepItem:nth-child(3) { animation-delay: 0.16s; }
.logStepItem:nth-child(4) { animation-delay: 0.24s; }
.logStepItem:nth-child(5) { animation-delay: 0.32s; }

@keyframes stepIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: none; }
}

/* ===== 回测寻优卡片 ===== */
.optBody {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.optKpis {
  display: flex;
  gap: 6px;
}

.optKpi {
  flex: 1;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 4px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}

.optKpiVal {
  font-size: 13px;
  font-weight: 800;
  font-family: var(--mono);
}

.optKpiLab {
  font-size: 9.5px;
  color: var(--dim);
}

.optDates {
  font-size: 10px;
  color: var(--dim);
  line-height: 1.3;
}

.optAppliedTag {
  display: inline-block;
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 9.5px;
  font-weight: 600;
  color: #059669;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.optWeights {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.optWRow {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
}

.optWName {
  width: 52px;
  flex-shrink: 0;
  color: var(--dim);
}

.optWBarTrack {
  flex: 1;
  height: 5px;
  background: var(--panel-2);
  border-radius: 3px;
  position: relative;
  overflow: hidden;
}

.optWBar {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 3px;
}

.optWBar.pos { background: #10b981; }
.optWBar.neg { background: #3b82f6; }

.optWVal {
  width: 36px;
  flex-shrink: 0;
  text-align: right;
  font-family: var(--mono);
  font-size: 10px;
}

.upTxt { color: var(--up); }
.downTxt { color: var(--down); }

.optApplyBtn {
  margin-top: 2px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #059669, #10b981);
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.optApplyBtn:hover { opacity: 0.9; }

.optRefreshBtn {
  font-size: 10.5px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--dim);
  border-radius: 4px;
  padding: 1px 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.optRefreshBtn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}

.optRefreshBtn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.optEmpty {
  font-size: 10.5px;
  color: var(--dim);
  padding: 6px 0;
}

/* ===== 超参卡片紧凑化（ant 组件默认尺寸偏大，统一压小） ===== */
.hyperparamBody :deep(.ant-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
}

.hyperparamBody :deep(.ant-radio-button-wrapper) {
  font-size: 10px;
  padding: 0 6px;
  height: 20px;
  line-height: 18px;
}

.hyperparamBody :deep(.ant-slider) {
  margin: 4px 0;
}
</style>
