<template>
    <div class="orbitPage" :class="{ light: isLight }">
        <div class="bgLayer">
            <div class="gridMask"></div>
            <div class="glow"></div>
        </div>

        <header class="topBar">
            <div class="brandRow">
                <div class="logoMark">
                    <!-- 线框牛头标识：牛角上扬 + 方正牛脸，红色渐变描边 -->
                    <svg viewBox="0 0 24 24" width="28" height="28" fill="none">
                        <defs>
                            <linearGradient id="logoGrad" x1="4" y1="4" x2="20" y2="21"
                                gradientUnits="userSpaceOnUse">
                                <stop offset="0" stop-color="#ff7875" />
                                <stop offset="1" stop-color="#d4380d" />
                            </linearGradient>
                        </defs>
                        <g stroke="url(#logoGrad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M8 11 C 6 5, 5 4, 7 7" />
                            <path d="M16 11 C 19 5, 20 4, 18 7" />
                            <path d="M6 11 Q6 9 8 9 L16 9 Q18 9 18 11 L18 19 Q18 21 16 21 L8 21 Q6 21 6 19 Z" />
                        </g>
                    </svg>
                </div>
                <span class="brandName">alpha-finder</span>
            </div>
            <div class="topRight">
                <span class="brandTag">A-SHARE SCREENER</span>
                <button class="themeBtn" :title="isLight ? '切换深色' : '切换浅色'" @click="toggleTheme">
                    <BulbFilled v-if="isLight" />
                    <BulbOutlined v-else />
                </button>
            </div>
        </header>

        <main class="mainArea">
            <!-- 左侧刻度转盘（1:1 复刻 langchain.com aadl_wheel：
                 54vh 暗色渐变圆盘、节点间隔 44°、1.1s cubic-bezier(0.6,0,0.15,1) 分档吸附、
                 双环为伪元素反向旋转、激活胶囊变形为 3rem 圆形图标芯片） -->
            <div class="dialZone">
                <!-- 旋转轮体：--rot = -turn * 44°，turn 无界累积实现循环 -->
                <div class="wheel" :style="{ '--rot': -turn * STEP + 'deg' }">
                    <div v-for="(item, i) in items" :key="item.key" class="dialItem" :class="{ on: i === activeIdx }"
                        :style="{ '--a': itemAngle(i) }" @click="jumpTo(i)">
                        <span class="pill">
                            <component :is="item.icon" class="pillIco" />
                            <span class="pillText">{{ item.key }}</span>
                        </span>
                    </div>
                </div>

                <!-- 激活芯片 → 内容区的连接线，每次切换重画 -->
                <div class="connector" :key="activeIdx"></div>
            </div>

            <!-- 中部文案：方向感知纵向轮播 -->
            <div class="contentZone">
                <transition :name="transName" mode="out-in">
                    <div :key="activeIdx" class="contentBlock">
                        <p class="eyebrow">{{ items[activeIdx].eyebrow }}</p>
                        <h1 class="contentTitle">{{ items[activeIdx].title }}</h1>
                        <p class="contentDesc">{{ items[activeIdx].desc }}</p>
                    </div>
                </transition>

                <div class="progressRow">
                    <span v-for="(item, i) in items" :key="item.key" class="progressSeg"
                        :class="{ on: i === activeIdx }" @click="jumpTo(i)"></span>
                </div>
            </div>

            <!-- 右侧登录卡片 -->
            <div class="formZone rise d3">
                <a-form class="loginCard" @submit.prevent="handleSubmit">
                    <h2 class="cardTitle">登录</h2>
                    <p class="cardSub">仅作客观数据筛选，不构成投资建议</p>

                    <a-form-item class="inputItem">
                        <a-input v-model:value="username" placeholder="账号" size="large" autocomplete="username">
                            <template #prefix>
                                <UserOutlined class="inputIcon" />
                            </template>
                        </a-input>
                    </a-form-item>

                    <a-form-item class="inputItem">
                        <a-input-password v-model:value="password" placeholder="密码" size="large"
                            autocomplete="current-password">
                            <template #prefix>
                                <LockOutlined class="inputIcon" />
                            </template>
                        </a-input-password>
                    </a-form-item>

                    <a-form-item class="rememberItem">
                        <a-checkbox v-model:checked="rememberMe" class="rememberCheck">记住账号</a-checkbox>
                    </a-form-item>

                    <!-- 卡片内错误行：接口返回 detail / 网络异常提示 -->
                    <p v-if="loginErr" class="loginErr">{{ loginErr }}</p>

                    <a-form-item class="submitItem">
                        <a-button class="loginButton" type="primary" html-type="submit" size="large" block
                            :loading="loading" :disabled="loading">登 录</a-button>
                    </a-form-item>

                    <p class="cardNote">账号由管理员创建，不开放注册</p>
                    <p class="riskLink" @click="discOpen = true">使用前请阅读《风险声明》</p>
                </a-form>

                <!-- 风险声明弹窗:卡片保持简洁,全文点开查看(与首次登录强制确认互为印证) -->
                <a-modal v-model:open="discOpen" title="风险声明" :footer="null" :width="480">
                    <div class="riskModalBody">
                        <p>本站为个人学习使用的行情数据整理工具，全部内容来自公开行情数据的<strong>客观统计与展示</strong>，不构成任何投资建议、证券分析意见或买卖依据。</p>
                        <p>股市有风险，投资须谨慎。任何基于本站信息作出的决策由<strong>使用者本人独立完成，盈亏由使用者本人承担</strong>，与本站及站长无关。</p>
                    </div>
                </a-modal>
            </div>
        </main>
    </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { setToken } from '../stores/auth';
import {
    UserOutlined, LockOutlined, BulbOutlined, BulbFilled,
    SwapOutlined, FireOutlined, CrownOutlined, FundOutlined, RocketOutlined,
} from '@ant-design/icons-vue';

/* 转盘条目（A 股选股功能，文案统一为客观描述口径，不含收益暗示） */
const items = [
    { key: '换手', icon: SwapOutlined, eyebrow: 'TURNOVER', title: '换手率筛选', desc: '按换手率统计全市场个股活跃度，客观呈现量价分布。' },
    { key: '涨停', icon: FireOutlined, eyebrow: 'LIMIT-UP', title: '涨停雷达', desc: '统计涨停与连板形态，客观呈现强势股分布。' },
    { key: '龙头', icon: CrownOutlined, eyebrow: 'LEADER', title: '板块强度', desc: '按板块强度梳理领涨个股，仅作形态统计。' },
    { key: '资金', icon: FundOutlined, eyebrow: 'CAPITAL', title: '资金流向', desc: '资金流向的客观展示，供盘中观察与研究。' },
    { key: '趋势', icon: RocketOutlined, eyebrow: 'TREND', title: '趋势统计', desc: '趋势形态的统计与复盘，不构成收益预期。' },
];

/* 与 langchain.com 一致：相邻节点间隔 44° */
const STEP = 44;

/*
 * 循环转盘：turn 无界累积（…,-1,0,1,2,…），转盘始终沿滚动方向连续转动，
 * 激活项取模得到 —— 转到最后一个再下滑即回到第一个，永不反向空转。
 */
const turn = ref(0);
const activeIdx = computed(() => ((turn.value % items.length) + items.length) % items.length);

/*
 * 循环转盘的基准角：胶囊角度 = (i + n * 圈数) * STEP - turn * STEP。
 * 圈数随 turn 动态推进，使胶囊始终分布在东点附近的可见弧面（±88°内）；
 * 跨缝胶囊的瞬移发生在 ±88°（屏幕左缘之外），不可见。
 */
const itemAngle = (i) => {
    const n = items.length;
    const cycle = Math.floor((turn.value - i + 2) / n);
    return (i + n * cycle) * STEP + 'deg';
};

/* 文案轮播方向：向下滚 -> 上出下进；向上滚 -> 下出上进 */
const lastDir = ref(1);
const transName = ref('swapDown');
watch(activeIdx, () => {
    transName.value = lastDir.value > 0 ? 'swapDown' : 'swapUp';
});

/* 滚轮分档吸附：累积滚轮量，过阈值进一档，过渡动画期间锁定，避免连跳 */
let acc = 0;
let locked = false;

const stepTurn = (dir) => {
    locked = true;
    lastDir.value = dir;
    turn.value += dir;
    setTimeout(() => {
        locked = false;
    }, 1000);
};

const onWheel = (e) => {
    if (locked) return;
    if (Math.sign(e.deltaY) !== Math.sign(acc)) acc = 0;
    acc += e.deltaY;
    if (Math.abs(acc) < 120) return;
    const dir = acc > 0 ? 1 : -1;
    acc = 0;
    stepTurn(dir);
    resetAuto();
};

/* 点击跳转：沿最短弧走（支持跨循环边界，如 4 -> 0 只走 +1 档） */
const jumpTo = (i) => {
    if (i === activeIdx.value || locked) return;
    const n = items.length;
    let delta = i - activeIdx.value;
    if (delta > n / 2) delta -= n;
    if (delta < -n / 2) delta += n;
    lastDir.value = delta > 0 ? 1 : -1;
    locked = true;
    turn.value += delta;
    setTimeout(() => {
        locked = false;
    }, 1000);
    resetAuto();
};

/* 7s 自动切换：手动滚轮/点击后重置计时，避免刚操作完就被自动切换打断 */
let autoTimer;
const resetAuto = () => {
    if (autoTimer !== undefined) clearInterval(autoTimer);
    autoTimer = window.setInterval(() => {
        if (!locked) stepTurn(1);
    }, 7000);
};

/* 亮暗主题切换（默认深色，记忆选择；key 与全站主题一致） */
const THEME_KEY = 'ts-theme';
const isLight = ref(localStorage.getItem(THEME_KEY) === 'light');
const toggleTheme = () => {
    isLight.value = !isLight.value;
    localStorage.setItem(THEME_KEY, isLight.value ? 'light' : 'dark');
};

/* ================= 登录逻辑（内联实现） ================= */
const router = useRouter();

const username = ref('');
const password = ref('');
const rememberMe = ref(false);
const loading = ref(false);
const loginErr = ref('');
const discOpen = ref(false);   // 风险声明弹窗

/* 记住账号：只存用户名，绝不存密码 */
const REMEMBER_KEY = 'ts-login-name';

const handleSubmit = async () => {
    if (loading.value) return;
    loginErr.value = '';
    if (!username.value || !password.value) {
        loginErr.value = '请输入账号和密码';
        return;
    }
    loading.value = true;
    try {
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username.value, password: password.value }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            loginErr.value = data.detail || '登录失败，请检查账号和密码';
            return;
        }
        if (rememberMe.value) {
            localStorage.setItem(REMEMBER_KEY, username.value);
        } else {
            localStorage.removeItem(REMEMBER_KEY);
        }
        setToken(data.token);
        router.replace('/');
    } catch (e) {
        loginErr.value = '网络错误，请稍后重试';
    } finally {
        loading.value = false;
    }
};

onMounted(() => {
    window.addEventListener('wheel', onWheel, { passive: true });
    resetAuto();
    /* 回填记住的账号名 */
    const saved = localStorage.getItem(REMEMBER_KEY);
    if (saved) {
        username.value = saved;
        rememberMe.value = true;
    }
});

onUnmounted(() => {
    window.removeEventListener('wheel', onWheel);
    if (autoTimer !== undefined) clearInterval(autoTimer);
});
</script>

<style scoped>
/*
 * 罗盘登录页（1:1 复刻 langchain.com 首页 aadl_wheel 转盘的实现参数）
 * 转盘直径 54vh、节点间隔 44°、过渡 1.1s cubic-bezier(0.6,0,0.15,1)、
 * 激活胶囊变形为 3rem 圆形图标芯片、连接线切换时重画
 * 配色为 A 股牛市红色主题（红 #ff4d4f/#d4380d，金橙 #ffa940 点缀）
 */
.orbitPage {
    --ease-wheel: cubic-bezier(0.6, 0, 0.15, 1);
    --dur-wheel: 1.1s;
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
    background: #05070b;
    color: #e8edf5;
    transition: background 0.45s ease, color 0.45s ease;
}

/* ================= 入场 ================= */
.rise {
    animation: rise 0.9s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.d3 {
    animation-delay: 0.25s;
}

@keyframes rise {
    from {
        opacity: 0;
        transform: translateY(20px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* ================= 背景 ================= */
.bgLayer {
    position: absolute;
    inset: 0;
    overflow: hidden;
}

.gridMask {
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
    background-size: 48px 48px;
    -webkit-mask-image: radial-gradient(ellipse 75% 70% at 40% 45%, #000 25%, transparent 75%);
    mask-image: radial-gradient(ellipse 75% 70% at 40% 45%, #000 25%, transparent 75%);
}

.glow {
    position: absolute;
    top: -200px;
    left: 18%;
    width: 640px;
    height: 480px;
    border-radius: 50%;
    background: radial-gradient(closest-side, rgba(255, 77, 79, 0.14), transparent);
    filter: blur(50px);
}

/* ================= 顶部导航 ================= */
.topBar {
    position: relative;
    z-index: 2;
    height: 64px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 40px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.brandRow {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logoMark {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    filter: drop-shadow(0 2px 6px rgba(255, 77, 79, 0.35));
}

.brandName {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #ffffff;
}

.brandTag {
    font-size: 11px;
    letter-spacing: 3px;
    color: rgba(255, 255, 255, 0.3);
}

.topRight {
    display: flex;
    align-items: center;
    gap: 16px;
}

.themeBtn {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    cursor: pointer;
    color: rgba(255, 255, 255, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.14);
    background: rgba(255, 255, 255, 0.05);
    transition: color 0.25s ease, border-color 0.25s ease, background 0.25s ease;
}

.themeBtn:hover {
    color: #ffffff;
    border-color: rgba(255, 120, 117, 0.5);
}

/* ================= 主区域：三段铺开，左右留足呼吸 ================= */
.mainArea {
    position: relative;
    z-index: 1;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-right: 6vw;
}

/* ================= 刻度转盘（参数 1:1 对齐 langchain.com） ================= */
.dialZone {
    position: relative;
    width: 24vw;
    flex-shrink: 0;
    height: 100%;
}

/*
 * 轮盘：54vh 暗色渐变圆盘，left: calc(9.375rem - 54vh)（东点恰在左缘 150px）
 * 盘面 radial-gradient + 内阴影；双环为伪元素，随轮旋转的同时反向自转，
 * 使环上渐变在视觉上保持静止。
 */
.wheel {
    position: absolute;
    left: calc(9.375rem - 54vh);
    top: 50%;
    margin-top: -27vh;
    width: 54vh;
    height: 54vh;
    border-radius: 50%;
    background-image: radial-gradient(circle, #04060a 0% 64%, #150a0c 84%, rgba(212, 56, 13, 0.35) 96%, rgba(255, 77, 79, 0.1) 100%);
    box-shadow: inset 0 0 5.625rem rgba(255, 77, 79, 0.1);
    transform: rotate(var(--rot, 0deg));
    transition: transform var(--dur-wheel) var(--ease-wheel);
}

.wheel::before,
.wheel::after {
    content: '';
    position: absolute;
    border-radius: 50%;
    padding: 1px;
    -webkit-mask:
        linear-gradient(#fff 0 0) content-box,
        linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    pointer-events: none;
    transform: rotate(calc(-1 * var(--rot, 0deg)));
    transition: transform var(--dur-wheel) var(--ease-wheel);
}

.wheel::before {
    inset: 0;
    background: linear-gradient(115deg,
            rgba(255, 120, 117, 0.95),
            rgba(255, 120, 117, 0.2) 35%,
            rgba(212, 56, 13, 0.18) 60%,
            rgba(255, 169, 64, 0.45) 100%);
    filter: drop-shadow(0 0 5px rgba(255, 77, 79, 0.55)) drop-shadow(0 0 14px rgba(255, 120, 117, 0.3));
}

.wheel::after {
    inset: 6vh;
    background: linear-gradient(140deg,
            rgba(255, 120, 117, 0.45),
            rgba(255, 120, 117, 0.06) 45%,
            rgba(212, 56, 13, 0.14) 75%,
            rgba(255, 169, 64, 0.22) 100%);
    filter: drop-shadow(0 0 5px rgba(255, 77, 79, 0.4)) drop-shadow(0 0 12px rgba(255, 120, 117, 0.22));
}

/* 节点：轮心 0x0 原点，先转到自身角度 --a，再沿半径推出 27vh */
.dialItem {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    cursor: pointer;
    transform: rotate(var(--a)) translateX(27vh);
}

.dialItem.on {
    z-index: 2;
}

/* 胶囊：反向旋转 (--a + --rot)，文字始终水平（尺寸/配色对齐原版 .aadl_pill） */
.pill {
    position: absolute;
    top: 0;
    left: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    box-sizing: border-box;
    height: 2.125rem;
    padding: 0 1.0625rem;
    border-radius: 999px;
    border: 1px solid #1a2231;
    background: #0b1018;
    color: #8b96a8;
    font-size: 0.78125rem;
    letter-spacing: 0.12em;
    white-space: nowrap;
    transform: translate(-50%, -50%) rotate(calc(-1 * (var(--a) + var(--rot, 0deg))));
    transition:
        transform var(--dur-wheel) var(--ease-wheel),
        width 0.7s var(--ease-wheel),
        height 0.7s var(--ease-wheel),
        padding 0.7s var(--ease-wheel),
        background 0.55s var(--ease-wheel) 0.1s,
        border-color 0.55s var(--ease-wheel) 0.1s,
        box-shadow 0.75s var(--ease-wheel) 0.15s,
        color 0.4s var(--ease-wheel);
}

/* 激活胶囊的渐变描边（mask 技巧，切换时淡入） */
.pill::after {
    content: '';
    position: absolute;
    inset: -1px;
    border-radius: 999px;
    padding: 1px;
    background: linear-gradient(135deg, #ff7875, rgba(255, 77, 79, 0.1) 45%, rgba(255, 77, 79, 0.06) 62%, rgba(255, 169, 64, 0.55) 100%);
    -webkit-mask:
        linear-gradient(#fff 0 0) content-box,
        linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    opacity: 0;
    transition: opacity 0.5s var(--ease-wheel) 0.15s;
    pointer-events: none;
}

.dialItem:hover .pill {
    color: #e8edf5;
    border-color: rgba(255, 120, 117, 0.4);
}

.pillText {
    max-width: 6.25rem;
    overflow: hidden;
    transition: max-width 0.6s var(--ease-wheel), opacity 0.25s var(--ease-wheel);
}

.pillIco {
    display: inline-flex;
    max-width: 0;
    opacity: 0;
    overflow: hidden;
    font-size: 1.25rem;
    color: #ff7875;
    transform: scale(0.4);
    transition:
        max-width 0.5s var(--ease-wheel),
        opacity 0.3s var(--ease-wheel),
        transform 0.55s var(--ease-wheel);
}

/* 激活胶囊变形为 3rem 圆形图标芯片：文字收起、图标延迟放大进入 */
.dialItem.on {
    pointer-events: none;
}

.dialItem.on .pill {
    width: 3rem;
    height: 3rem;
    padding: 0;
    background: radial-gradient(circle at 35% 30%, #2a1214, #140a0c);
    border-color: transparent;
}

.dialItem.on .pill::after {
    opacity: 1;
}

.dialItem.on .pillText {
    max-width: 0;
    opacity: 0;
}

.dialItem.on .pillIco {
    max-width: 1.25rem;
    opacity: 1;
    transform: scale(1);
    transition-delay: 0.3s;
}

/* 连接线：left 10rem（圆盘东点 150px 外侧），宽 8.75rem，每次切换重画 */
.connector {
    position: absolute;
    left: 10rem;
    top: 50%;
    width: 8.75rem;
    height: 1px;
    transform: translateY(-50%);
    transform-origin: left;
    background-image: linear-gradient(90deg, rgba(255, 120, 117, 0.9), rgba(255, 120, 117, 0));
    pointer-events: none;
    animation: connectorDraw 0.35s var(--ease-wheel) 1.1s backwards;
}

@keyframes connectorDraw {
    from {
        transform: translateY(-50%) scaleX(0);
        opacity: 0;
    }

    to {
        transform: translateY(-50%) scaleX(1);
        opacity: 1;
    }
}

/* ================= 中部联动文案（方向感知轮播） ================= */
.contentZone {
    flex: 1;
    min-width: 0;
    max-width: 440px;
    /* 半格偏移，避免文字左边压着背景网格竖线 */
    padding-left: 24px;
}

.contentBlock {
    min-height: 190px;
}

.eyebrow {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 4px;
    color: #ff7875;
    margin: 0 0 14px;
}

.contentTitle {
    font-size: 34px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #ffffff;
    margin: 0 0 14px;
}

.contentDesc {
    font-size: 14px;
    line-height: 1.9;
    color: rgba(219, 228, 243, 0.55);
    margin: 0;
    max-width: 380px;
}

/* 向下：上出下进；向上：下出上进（对齐 langchain 的面板轮播方向） */
.swapDown-enter-active {
    transition: opacity 0.5s var(--ease-wheel) 0.075s, transform 0.5s var(--ease-wheel) 0.075s;
}

.swapDown-leave-active {
    transition: opacity 0.25s var(--ease-wheel), transform 0.25s var(--ease-wheel);
}

.swapDown-enter-from {
    opacity: 0;
    transform: translateY(2.75rem);
}

.swapDown-leave-to {
    opacity: 0;
    transform: translateY(-2.75rem);
}

.swapUp-enter-active {
    transition: opacity 0.5s var(--ease-wheel) 0.075s, transform 0.5s var(--ease-wheel) 0.075s;
}

.swapUp-leave-active {
    transition: opacity 0.25s var(--ease-wheel), transform 0.25s var(--ease-wheel);
}

.swapUp-enter-from {
    opacity: 0;
    transform: translateY(-2.75rem);
}

.swapUp-leave-to {
    opacity: 0;
    transform: translateY(2.75rem);
}

/* 进度指示条 */
.progressRow {
    display: flex;
    gap: 8px;
    margin-top: 34px;
}

.progressSeg {
    width: 34px;
    height: 3px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.1);
    cursor: pointer;
    transition: background 0.4s ease;
}

.progressSeg:not(.on):hover {
    background: rgba(255, 255, 255, 0.35);
}

.progressSeg.on {
    background: #ff4d4f;
}

/* ================= 登录卡片 ================= */
.formZone {
    flex-shrink: 0;
}

.loginCard {
    width: 360px;
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.09);
    background: rgba(14, 21, 38, 0.7);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
    padding: 34px 32px 26px;
    transition: background 0.45s ease, border-color 0.45s ease, box-shadow 0.45s ease;
}

.cardTitle {
    font-size: 20px;
    font-weight: 600;
    color: #ffffff;
    margin: 0 0 6px;
}

.cardSub {
    font-size: 13px;
    color: rgba(219, 228, 243, 0.4);
    margin: 0 0 24px;
}

.inputItem {
    margin-bottom: 16px;
}

.inputIcon {
    color: rgba(255, 255, 255, 0.28);
}

.loginCard :deep(.ant-input-affix-wrapper),
.loginCard :deep(.ant-input) {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.12);
    color: #dbe4f3;
    border-radius: 8px;
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

/* 嵌套在 affix-wrapper 内的输入框保持透明，避免半透明背景叠出"框中框" */
.loginCard :deep(.ant-input-affix-wrapper .ant-input) {
    background: transparent;
    border: none;
    box-shadow: none;
}

.loginCard :deep(.ant-input::placeholder) {
    color: rgba(255, 255, 255, 0.28);
}

.loginCard :deep(.ant-input-affix-wrapper:hover) {
    border-color: rgba(255, 255, 255, 0.24);
}

.loginCard :deep(.ant-input-affix-wrapper-focused) {
    border-color: #ff4d4f;
    box-shadow: 0 0 0 3px rgba(255, 77, 79, 0.16);
}

.loginCard :deep(.ant-input-password input) {
    background: transparent;
    color: #dbe4f3;
}

.loginCard :deep(.ant-input-suffix) {
    color: rgba(255, 255, 255, 0.28);
}

/* 覆盖浏览器自动填充的默认浅色背景，避免输入框出现“白条” */
.loginCard :deep(input:-webkit-autofill),
.loginCard :deep(input:-webkit-autofill:hover),
.loginCard :deep(input:-webkit-autofill:focus) {
    -webkit-text-fill-color: #dbe4f3;
    -webkit-box-shadow: 0 0 0 1000px #171c28 inset;
    caret-color: #dbe4f3;
    transition: background-color 9999s ease-in-out 0s;
}

.rememberItem {
    margin-bottom: 16px;
}

.rememberCheck {
    color: rgba(219, 228, 243, 0.55);
    font-size: 13px;
}

/* 卡片内错误行 */
.loginErr {
    margin: 0 0 16px;
    font-size: 13px;
    line-height: 1.6;
    color: #ff7875;
}

.submitItem {
    margin-bottom: 0;
}

.loginButton {
    height: 42px;
    font-size: 14px;
    letter-spacing: 4px;
    border-radius: 8px;
    border: none;
    font-weight: 600;
    color: #ffffff;
    background: linear-gradient(135deg, #ff4d4f, #c81e1e);
    box-shadow: 0 6px 18px rgba(255, 77, 79, 0.3);
    transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease, background 0.25s ease;
}

.loginButton:hover {
    background: linear-gradient(135deg, #ff7875, #d4380d);
    color: #ffffff;
    transform: translateY(-1px);
    box-shadow: 0 10px 24px rgba(255, 77, 79, 0.4);
}

.loginButton:active {
    transform: translateY(0);
}

.cardNote {
    margin: 14px 0 0;
    font-size: 12px;
    text-align: center;
    color: rgba(219, 228, 243, 0.32);
}

/* 风险声明入口:卡片底部一行小字链接,点击弹窗看全文 */
.riskLink {
    margin: 8px 0 0;
    font-size: 12px;
    text-align: center;
    color: rgba(255, 152, 149, 0.55);
    cursor: pointer;
    transition: color 0.2s ease;
}

.riskLink:hover {
    color: rgba(255, 152, 149, 0.9);
}

.riskModalBody p {
    line-height: 1.9;
    margin: 0 0 10px;
}

.riskModalBody p:last-child {
    margin-bottom: 0;
}

/* ================= 浅色主题 ================= */
.light {
    background: #f4f7fc;
    color: #22314a;
}

.light .gridMask {
    background-image:
        linear-gradient(rgba(10, 37, 64, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(10, 37, 64, 0.05) 1px, transparent 1px);
}

.light .glow {
    background: radial-gradient(closest-side, rgba(255, 77, 79, 0.16), transparent);
}

.light .topBar {
    border-bottom-color: rgba(10, 37, 64, 0.08);
}

.light .brandName {
    color: #0a2540;
}

.light .brandTag {
    color: rgba(10, 37, 64, 0.4);
}

.light .themeBtn {
    color: rgba(10, 37, 64, 0.55);
    border-color: rgba(10, 37, 64, 0.14);
    background: rgba(10, 37, 64, 0.04);
}

.light .themeBtn:hover {
    color: #0a2540;
    border-color: rgba(207, 19, 34, 0.5);
}

.light .wheel {
    background-image: radial-gradient(circle, #ffffff 0% 64%, #fdf0ee 84%, rgba(255, 120, 117, 0.22) 96%, rgba(212, 56, 13, 0.07) 100%);
    box-shadow: inset 0 0 5.625rem rgba(212, 56, 13, 0.08), 0 18px 46px rgba(10, 37, 64, 0.1);
}

.light .wheel::before {
    background: linear-gradient(115deg,
            rgba(212, 56, 13, 0.75),
            rgba(212, 56, 13, 0.16) 35%,
            rgba(212, 56, 13, 0.12) 60%,
            rgba(212, 56, 13, 0.35) 100%);
    filter: drop-shadow(0 0 5px rgba(212, 56, 13, 0.3));
}

.light .wheel::after {
    background: linear-gradient(140deg,
            rgba(212, 56, 13, 0.35),
            rgba(212, 56, 13, 0.05) 45%,
            rgba(212, 56, 13, 0.1) 75%,
            rgba(212, 56, 13, 0.18) 100%);
    filter: none;
}

.light .pill {
    background: rgba(255, 255, 255, 0.95);
    color: rgba(10, 37, 64, 0.6);
    border-color: rgba(10, 37, 64, 0.14);
}

.light .dialItem:hover .pill {
    color: #0a2540;
    border-color: rgba(207, 19, 34, 0.45);
}

.light .dialItem.on .pill {
    background: radial-gradient(circle at 35% 30%, #ffffff, #fbe9e7);
    box-shadow: 0 0 22px rgba(212, 56, 13, 0.25);
}

.light .pillIco {
    color: #cf1322;
}

.light .connector {
    background-image: linear-gradient(90deg, rgba(207, 19, 34, 0.75), rgba(207, 19, 34, 0));
}

.light .eyebrow {
    color: #cf1322;
}

.light .contentTitle {
    color: #0a2540;
}

.light .contentDesc {
    color: rgba(10, 37, 64, 0.6);
}

.light .progressSeg {
    background: rgba(10, 37, 64, 0.12);
}

.light .progressSeg:not(.on):hover {
    background: rgba(10, 37, 64, 0.3);
}

.light .progressSeg.on {
    background: #cf1322;
}

.light .loginCard {
    background: rgba(255, 255, 255, 0.88);
    border-color: rgba(10, 37, 64, 0.08);
    box-shadow: 0 24px 60px rgba(10, 37, 64, 0.12);
}

.light .cardTitle {
    color: #0a2540;
}

.light .cardSub {
    color: rgba(10, 37, 64, 0.45);
}

.light .inputIcon {
    color: rgba(10, 37, 64, 0.3);
}

.light .loginCard :deep(.ant-input-affix-wrapper),
.light .loginCard :deep(.ant-input) {
    background: rgba(10, 37, 64, 0.035);
    border-color: rgba(10, 37, 64, 0.14);
    color: #22314a;
}

.light .loginCard :deep(.ant-input-affix-wrapper .ant-input) {
    background: transparent;
}

.light .loginCard :deep(.ant-input::placeholder) {
    color: rgba(10, 37, 64, 0.3);
}

.light .loginCard :deep(.ant-input-affix-wrapper:hover) {
    border-color: rgba(10, 37, 64, 0.3);
}

.light .loginCard :deep(.ant-input-affix-wrapper-focused) {
    border-color: #cf1322;
    box-shadow: 0 0 0 3px rgba(207, 19, 34, 0.14);
}

.light .loginCard :deep(.ant-input-password input) {
    color: #22314a;
}

.light .loginCard :deep(.ant-input-suffix) {
    color: rgba(10, 37, 64, 0.3);
}

/* 覆盖浏览器自动填充的默认浅色背景，避免输入框出现“白条” */
.light .loginCard :deep(input:-webkit-autofill),
.light .loginCard :deep(input:-webkit-autofill:hover),
.light .loginCard :deep(input:-webkit-autofill:focus) {
    -webkit-text-fill-color: #22314a;
    -webkit-box-shadow: 0 0 0 1000px #f3f5f9 inset;
    caret-color: #22314a;
    transition: background-color 9999s ease-in-out 0s;
}

.light .rememberCheck {
    color: rgba(10, 37, 64, 0.6);
}

.light .loginErr {
    color: #cf1322;
}

.light .cardNote {
    color: rgba(10, 37, 64, 0.4);
}

.light .riskLink {
    color: rgba(207, 19, 34, 0.55);
}

.light .riskLink:hover {
    color: #cf1322;
}

/* 小屏隐藏刻度盘与文案区 */
@media (max-width: 1100px) {

    .dialZone,
    .contentZone {
        display: none;
    }

    .mainArea {
        justify-content: center;
        padding-right: 0;
    }
}
</style>
