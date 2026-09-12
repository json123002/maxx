/* ===== 各战法评估(移植自旧 screener-analysis.js,返回 HTML 片段 + 结论)=====
   算法按 skills/ 目录各战法的公开思路在浏览器端实现:
     a-share-trend-stock-selection  趋势波段·六维
     a-share-trend-startup          趋势启动（仅主板）
     a-share-oversold-rebound       超跌反弹（仅主板）
     a-share-3030-strategy          3030战法·支撑压力（日线级别）
     a-share-money-flow             主力资金流向（辅助验证）
   所有结论均为技术面概率框架，不构成投资建议。 */
import { fmtN, fmtYiT, esc } from "../utils/format";
import { smaLast, pctChg, pivots, makeZones } from "./indicators";

const OK = "✅", WARN = "⚠️", BAD = "❌";
const line = (mark, text) => `<div class="anaLine">${mark} ${text}</div>`;

// ===== 市场情绪（把全市场快照 allRows 当数据源，本地 O(n) 计算，零新增请求）=====
// 涨跌幅阈值按板块：主板10%（含 ST，按 2025 新规） / 创业板·科创板20% / 北交所30%
export function limitPctOf(code) { return /^(30|68)/.test(code) ? 20 : /^[48]/.test(code) ? 30 : 10; }
// 涨停容差按比例 2%（主板 9.8% / 创业 19.6% / 北交 29.4%），避免仅"封板"才算涨停
export function limitTol(lp) { return Math.max(0.2, lp * 0.02); }

// 情绪温度 0~100 = 上涨占比(40) + 涨跌停比(30) + 指数量能(30,无数据按中性15)
// idxBars 为上证指数日K（需含 amount；腾讯/新浪兜底源无 amount 时量能按中性处理）
// 盘中量能按当前上海交易时段线性外推（避免半日量被当全天量低估情绪）
export function computeSentiment(rows, idxBars) {
  let up = 0, limitUp = 0, limitDown = 0, bigDown = 0, valid = 0;
  rows.forEach(r => {
    if (typeof r.f3 !== "number") return;
    valid++;
    const lp = limitPctOf(r.f12);
    const tol = limitTol(lp);                       // 按比例容差
    if (r.f3 > 0) up++;
    if (r.f3 >= lp - tol) limitUp++;
    if (r.f3 <= -(lp - tol)) limitDown++;
    if (r.f3 <= -5) bigDown++;
  });
  if (!valid) return null;
  const upRatio = up / valid;
  const limitScore = (limitUp + limitDown) > 0 ? limitUp / (limitUp + limitDown) * 30 : 15;
  let volScore = 15, volRatio = null, volSrc = "缺失（按中性计）", volNote = "";
  if (idxBars && idxBars.length > 5) {
    const amts = idxBars.map(b => b.amount).filter(isFinite);
    if (amts.length > 5) {
      const ma = amts.slice(-6, -1).reduce((s, x) => s + x, 0) / 5;
      if (ma > 0) {
        let lastAmt = amts[amts.length - 1];
        const lastBar = idxBars[idxBars.length - 1];
        // 本地日期串（避免 toISOString 的 UTC 跨日错位）；K 线日期也是本地日历日
        const _now = new Date();
        const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
        // 上海交易时段（按浏览器本地时间，国内用户=上海时区）：9:30-11:30 / 13:00-15:00
        const mins = _now.getHours() * 60 + _now.getMinutes();
        const isWeekday = _now.getDay() % 6 !== 0;
        let elapsed = -1;   // -1 表示非盘中
        if (isWeekday) {
          if (mins >= 570 && mins < 690) elapsed = mins - 570;            // 09:30-11:30
          else if (mins >= 690 && mins < 780) elapsed = 120;              // 11:30-13:00 午休按上午满120
          else if (mins >= 780 && mins < 900) elapsed = 120 + (mins - 780); // 13:00-15:00
        }
        volSrc = "完整";
        if (elapsed > 0 && lastBar.date === today) {
          const ratio = Math.min(1, elapsed / 240);   // 交易时长 240 分钟
          if (ratio > 0.05 && ratio < 0.99) {
            lastAmt = lastAmt / ratio;
            volSrc = "盘中外推";
            volNote = `按 ${elapsed}/240 分钟外推`;
          }
        }
        volRatio = lastAmt / ma;
        volScore = Math.min(30, Math.max(0, (volRatio - 0.5) * 30));
      }
    }
  }
  const temp = Math.round(upRatio * 40 + limitScore + volScore);
  // 对称区间：冰点 0-19 / 低迷 20-39 / 中性 40-59 / 活跃 60-79 / 亢奋 80-100
  const level = temp < 20 ? "冰点" : temp < 40 ? "低迷" : temp < 60 ? "中性" : temp < 80 ? "活跃" : "亢奋";
  return { temp, level, up, down: valid - up, valid, limitUp, limitDown, bigDown, upRatio, volRatio, volSrc, volNote };
}

// 个股情绪特征（日K）：近10日涨停次数、当前连板数
export function stockHeat(bars, code) {
  const lp = limitPctOf(code);
  const isLimit = b => b.pct >= lp - limitTol(lp);
  const last10 = bars.slice(-10).filter(isLimit).length;
  let streak = 0;
  for (let i = bars.length - 1; i >= 0 && isLimit(bars[i]); i--) streak++;
  return { last10, streak };
}

// —— 趋势波段·六维（a-share-trend-stock-selection）——
export function evalTrend(ctx) {
  const { price, ma5, ma10, ma20, ma60, rsi, macd, bars, mf, idx } = ctx;
  const c = bars.map(b => b.close), v = bars.map(b => b.vol);
  const last = bars[bars.length - 1];
  const vma5 = smaLast(v, 5);
  const lines = [];
  let veto = false, trendPass = false, buyPoint = false;

  // 关键指标盘（先给客观数值，再给六维判断）
  const lo60 = Math.min(...bars.slice(-60).map(b => b.low));
  const hi60 = Math.max(...bars.slice(-60).map(b => b.high));
  const pos60 = hi60 > lo60 ? Math.min(100, Math.max(0, (price - lo60) / (hi60 - lo60) * 100)) : 50;
  const kv = (n, val) => `<div class="anaKV"><span>${n}</span><b>${val}</b></div>`;
  lines.push(`<div class="anaGrid">` +
    kv("MA5 / MA10", `${fmtN(ma5)} / ${fmtN(ma10)}`) +
    kv("MA20 / MA60", `${fmtN(ma20)} / ${fmtN(ma60)}`) +
    kv("RSI14", rsi === null ? "—" : rsi.toFixed(0)) +
    kv("MACD DIF/DEA", macd ? `${fmtN(macd.dif, 3)} / ${fmtN(macd.dea, 3)}` : "—") +
    kv("60日位置", pos60.toFixed(0) + "%") +
    kv("量比(vs5日)", vma5 ? (last.vol / vma5).toFixed(2) : "—") +
    `</div>`);

  // 1 趋势
  if (ma20 && ma60) {
    if (price > ma20 && ma20 > ma60 && ma5 > ma10 && ma10 > ma20) {
      lines.push(line(OK, `趋势：多头排列，价 ${fmtN(price)} > MA20 ${fmtN(ma20)} > MA60 ${fmtN(ma60)}`));
      trendPass = true;
    } else if (price < ma20 && ma20 < ma60) {
      lines.push(line(BAD, `趋势：空头排列（价 < MA20 < MA60），顺势框架直接淘汰`));
      veto = true;
    } else {
      lines.push(line(WARN, `趋势：均线缠绕（价 ${fmtN(price)} / MA20 ${fmtN(ma20)} / MA60 ${fmtN(ma60)}），方向未明`));
    }
  }

  // 2 量价
  if (vma5) {
    const vr = last.vol / vma5;
    if (vr > 2 && Math.abs(last.pct) < 1) lines.push(line(WARN, `量价：天量滞涨（量 ${vr.toFixed(1)}×5日均量，涨跌 ${fmtN(last.pct)}%），警惕出货`));
    else if (vr > 1.5 && last.pct > 0) lines.push(line(OK, `量价：放量上涨（${vr.toFixed(1)}×5日均量）`));
    else if (vr < 0.8 && last.pct < 0 && trendPass) lines.push(line(OK, `量价：缩量回调（${vr.toFixed(2)}×5日均量），回踩健康`));
    else if (vr > 1.5 && last.pct < 0) lines.push(line(WARN, `量价：放量下跌（${vr.toFixed(1)}×5日均量），承接存疑`));
    else lines.push(line(WARN, `量价：量 ${vr.toFixed(2)}×5日均量，无显著异动`));
  }

  // 3 形态与买点
  const dev20 = ma20 ? (price / ma20 - 1) * 100 : null;
  const h20 = Math.max(...bars.slice(-20).map(b => b.high));
  const nearMa = ma20 && Math.min(...bars.slice(-3).map(b => b.low)) <= ma20 * 1.02 && price > ma20;
  if (dev20 !== null && dev20 > 18) {
    lines.push(line(WARN, `形态：离 MA20 乖离 ${dev20.toFixed(1)}% > 18%，乖离偏高，仅列观察`));
  } else if (last.close >= h20 * 0.999 && vma5 && last.vol > 1.5 * vma5) {
    lines.push(line(OK, `形态：放量创 20 日新高（平台突破买点）`));
    buyPoint = true;
  } else if (nearMa) {
    lines.push(line(OK, `形态：近 3 日回踩 MA10/MA20 企稳（回踩均线买点）`));
    buyPoint = true;
  } else {
    lines.push(line(WARN, `形态：无平台突破/回踩均线等经典买点信号`));
  }

  // 4 相对强度
  const p20 = pctChg(c, 20);
  const ip20 = idx && idx.length > 20 ? pctChg(idx.map(b => b.close), 20) : null;
  if (p20 !== null && ip20 !== null) {
    lines.push(p20 > ip20
      ? line(OK, `相对强度：20日涨幅 ${p20.toFixed(1)}% 强于上证 ${ip20.toFixed(1)}%`)
      : line(WARN, `相对强度：20日涨幅 ${p20.toFixed(1)}% 弱于上证 ${ip20.toFixed(1)}%（滞涨）`));
  } else lines.push(line(WARN, `相对强度：指数数据不可用，未验证`));

  // 5 资金验证
  if (mf && mf.length) {
    const sum5 = mf.slice(-5).reduce((s, x) => s + x.main, 0) / 1e8;
    lines.push(sum5 > 0
      ? line(OK, `资金验证：近5日主力累计净流入 ${sum5.toFixed(2)} 亿（仅辅助印证）`)
      : line(WARN, `资金验证：近5日主力累计净流出 ${Math.abs(sum5).toFixed(2)} 亿，趋势>资金，谨慎`));
  } else lines.push(line(WARN, `资金验证：资金流数据不可用，未验证`));

  // 6 雷区
  const mines = [];
  if (/ST|退/.test(ctx.row.f14)) mines.push("ST/退市风险");
  if (rsi !== null && rsi > 72) mines.push(`RSI ${rsi.toFixed(0)} 偏热(>72)`);
  if (veto) mines.push("空头排列");
  lines.push(mines.length ? line(BAD, `雷区：${mines.join("；")}`) : line(OK, `雷区：未命中排除项（公告/解禁/财务雷区需人工另行核验）`));
  if (/ST|退/.test(ctx.row.f14)) veto = true;

  // 判定
  let verdict, vCls, waitBuy = false;
  if (veto) { verdict = "回避"; vCls = "bad"; }
  else if (trendPass && buyPoint && dev20 !== null && dev20 <= 18) { verdict = "技术条件通过（待复核）"; vCls = "good"; }
  else if (trendPass && dev20 !== null && dev20 <= 18) { verdict = "多头排列，等待右侧买点"; vCls = "good"; waitBuy = true; }
  else if (trendPass && dev20 !== null && dev20 > 18) { verdict = "多头排列但乖离过高（>18%）"; vCls = "warn"; }
  else { verdict = "观察"; vCls = "warn"; }
  lines.push(`<div class="anaVerdict ${vCls}">买点判断：${verdict}${vCls === "good" ? "——板块强度/盘中实时信号/公告解禁仍需人工复核" : ""}</div>`);
  // 技术条件通过时给关键参考价位（描述性口径，不构成操作建议）
  if (vCls === "good" && ma10 && ma20) {
    const stop = Math.min(...bars.slice(-10).map(b => b.low));
    const watch = Math.max(...bars.slice(-20).map(b => b.high));
    if (waitBuy) {
      lines.push(`<div class="anaNote">多头排列成立但暂无经典买点信号——` +
        `历史形态上，放量突破近20日高点 ${fmtN(watch)} 或回踩 MA10~MA20（${fmtN(ma10)} ~ ${fmtN(ma20)}）企稳通常被视为确认信号 · ` +
        `收盘跌破近10日最低 ${fmtN(stop)} 通常视为支撑失效信号 · ` +
        `${fmtN(ma20 * 1.18)}（MA20+18%）以上乖离偏高，历史回测胜率显著下降</div>`);
    } else {
      lines.push(`<div class="anaNote">参考区间：历史形态上，回踩 MA10~MA20（${fmtN(ma10)} ~ ${fmtN(ma20)}）一带常被视为支撑观察区 · ` +
        `收盘跌破近10日最低 ${fmtN(stop)} 通常视为支撑失效信号 · ` +
        `${fmtN(ma20 * 1.18)}（MA20+18%）以上乖离偏高 · ` +
        `该框架不提供仓位建议</div>`);
    }
  }
  return { title: "趋势波段 · 六维评估", verdict, vCls, trendPass, buyPoint, waitBuy,
    brief: veto ? "空头排列/雷区命中" : trendPass ? (buyPoint ? "多头排列 + 有经典买点" : "多头排列，等右侧买点") : "均线缠绕，趋势未明",
    html: lines.join("") };
}

// —— 趋势启动（a-share-trend-startup，仅主板，满分130）——
export function evalStartup(ctx) {
  if (!/^(60|00)/.test(ctx.row.f12))
    return { title: "趋势启动 · 第一起跳点", verdict: "不适用", vCls: "dim", brief: "仅适用主板",
      html: line(WARN, "该战法规则仅限主板（60/00 开头），当前标的为 ±20%/±30% 板块，跳过") };
  const { price, bars, ma5, ma10, ma20, ma60, rsi, macd } = ctx;
  const c = bars.map(b => b.close), v = bars.map(b => b.vol);
  const last = bars[bars.length - 1];
  const lo60 = Math.min(...bars.slice(-60).map(b => b.low));
  const hi60 = Math.max(...bars.slice(-60).map(b => b.high));
  // 创新低/新高时钳到 0~100，避免出现负位置
  const pos60 = hi60 > lo60 ? Math.min(100, Math.max(0, (price - lo60) / (hi60 - lo60) * 100)) : 50;
  const vma10 = smaLast(v, 10);
  const lines = [];
  let score = 0;
  const lowPos = pos60 <= 40;

  if (lowPos) { score += 30; lines.push(line(OK, `低位约束：60日区间位置 ${pos60.toFixed(0)}%（≤40%）+30`)); }
  else lines.push(line(WARN, `位置：60日区间位置 ${pos60.toFixed(0)}% > 40%，高位横盘收敛属出货平台，蓄势不记分`));

  if (ma5 && ma10 && ma20) {
    const conv = (Math.max(ma5, ma10, ma20) - Math.min(ma5, ma10, ma20)) / price * 100;
    if (conv < 3 && lowPos) { score += 25; lines.push(line(OK, `均线收敛：MA5/10/20 收敛度 ${conv.toFixed(1)}%（<3%）+25`)); }
    else lines.push(line(WARN, `均线收敛：收敛度 ${conv.toFixed(1)}%${conv < 3 ? "（但非低位）" : ""}，未达标`));
  }

  if (vma10 && last.vol > 1.8 * vma10) { score += 25; lines.push(line(OK, `倍量起跳：量 ${(last.vol / vma10).toFixed(1)}×10日均量（>1.8×）+25`)); }
  else lines.push(line(WARN, `倍量起跳：量 ${vma10 ? (last.vol / vma10).toFixed(2) : "—"}×10日均量，未达 1.8×`));

  const amp = (bs) => { const h = Math.max(...bs.map(b => b.high)), l = Math.min(...bs.map(b => b.low)); return (h - l) / l; };
  const a20 = amp(bars.slice(-20)), a60 = amp(bars.slice(-60));
  if (a20 < a60 * 0.8) { score += 20; lines.push(line(OK, `VCP 波动收窄：20日振幅 ${(a20 * 100).toFixed(1)}% < 60日振幅 ${(a60 * 100).toFixed(1)}%×0.8 +20`)); }
  else lines.push(line(WARN, `VCP：20日振幅 ${(a20 * 100).toFixed(1)}% 未收窄至 60日振幅×0.8`));

  if (macd && macd.dif > macd.dea && macd.difPrev <= macd.deaPrev) { score += 15; lines.push(line(OK, `MACD 金叉（DIF ${fmtN(macd.dif, 3)} 上穿 DEA）+15`)); }
  else if (macd && macd.dif > macd.dea) { score += 8; lines.push(line(WARN, `MACD 多头区（金叉发生在更早），+8`)); }
  else lines.push(line(WARN, `MACD：DIF 仍在 DEA 下方，未金叉`));

  if (rsi !== null && rsi >= 50 && rsi <= 70) { score += 15; lines.push(line(OK, `RSI ${rsi.toFixed(0)} 突破50中轴进入强势区（50~70）+15`)); }
  else lines.push(line(WARN, `RSI ${rsi === null ? "—" : rsi.toFixed(0)}，未进入 50~70 强势区`));

  const dryup = bars.slice(-30, -1).some((b, i, arr) => { const vv = smaLast(v.slice(0, v.length - 30 + i + 1), 20); return vv && b.vol < 0.5 * vv; });
  if (dryup) lines.push(line(OK, `辅助特征：近30日出现过地量筑底（had_dryup）`));

  let verdict, vCls;
  if (score >= 70) { verdict = `高价值启动点（${score}/130）`; vCls = "good"; }
  else if (score >= 40) { verdict = `潜在观察点（${score}/130）`; vCls = "warn"; }
  else { verdict = `普通（${score}/130）`; vCls = "dim"; }
  lines.push(`<div class="anaVerdict ${vCls}">启动状态：${verdict}——临界点信号对当日盘口敏感，需人工复核实时盘口后再定</div>`);
  if (vCls !== "dim") {
    const stop = Math.min(...bars.slice(-20).map(b => b.low));
    const watch = Math.max(...bars.slice(-20).map(b => b.high));
    lines.push(`<div class="anaNote">风险提示：历史形态上，放量突破近20日高点 ${fmtN(watch)} 通常被视为确认信号 · ` +
      `收盘跌破近20日最低 ${fmtN(stop)}（收敛区下沿）通常视为结构失效信号 · ` +
      `已明显扩张的走势不纳入本框架；历史回测中破位不止损是该类形态的主要亏损来源</div>`);
  }
  return { title: "趋势启动 · 第一起跳点", verdict, vCls,
    brief: `60日位置 ${pos60.toFixed(0)}%，量比 ${vma10 ? (last.vol / vma10).toFixed(1) : "—"}，得分 ${score}/130`,
    html: lines.join("") };
}

// —— 超跌反弹（a-share-oversold-rebound，仅主板）——
export function evalOversold(ctx) {
  if (!/^(60|00)/.test(ctx.row.f12))
    return { title: "超跌反弹 · 极短线博弈", verdict: "不适用", vCls: "dim", brief: "仅适用主板",
      html: line(WARN, "该战法规则仅限主板（60/00 开头），当前标的为 ±20%/±30% 板块，跳过") };
  const { price, bars, ma10, ma20, rsi } = ctx;
  const c = bars.map(b => b.close), v = bars.map(b => b.vol);
  const last = bars[bars.length - 1], prev = bars[bars.length - 2];
  const lo60 = Math.min(...bars.slice(-60).map(b => b.low));
  const hi60 = Math.max(...bars.slice(-60).map(b => b.high));
  const pos60 = hi60 > lo60 ? Math.min(100, Math.max(0, (price - lo60) / (hi60 - lo60) * 100)) : 50;
  const dd60 = (price / hi60 - 1) * 100;
  const vma5 = smaLast(v, 5);
  const lines = [];
  let oversold = false, stabilize = false, space = false, veto = false;

  // 1 超跌程度
  const conds = [];
  if (dd60 <= -20) conds.push(`距60日高回撤 ${dd60.toFixed(1)}%`);
  if (rsi !== null && rsi < 35) conds.push(`RSI ${rsi.toFixed(0)}`);
  if (pos60 < 20) conds.push(`60日位置 ${pos60.toFixed(0)}%`);
  if (conds.length >= 2) { oversold = true; lines.push(line(OK, `超跌程度：${conds.join("、")}，够"超"`)); }
  else if (conds.length === 1) lines.push(line(WARN, `超跌程度：仅 ${conds[0]} 一项达标，超跌不充分`));
  else lines.push(line(BAD, `超跌程度：回撤 ${dd60.toFixed(1)}% / RSI ${rsi === null ? "—" : rsi.toFixed(0)} / 位置 ${pos60.toFixed(0)}%，只是普通回调，不在射程`));

  // 2 恐慌出清
  const panic = bars.slice(-10).some(b => {
    const rng = b.high - b.low;
    return rng > 0 && (Math.min(b.open, b.close) - b.low) / rng > 0.5 && vma5 && b.vol > 1.5 * vma5;
  });
  lines.push(panic
    ? line(OK, `恐慌出清：近10日有放量长下影，恐慌盘有释放`)
    : line(WARN, `恐慌出清：未见放量杀跌/长下影，无量阴跌=未出清，历史上反弹失败率高`));

  // 3 企稳信号
  const isYang = last.close > last.open;
  const volOk = vma5 && last.vol > 1.5 * vma5;
  const hammer = (last.high - last.low) > 0 && (Math.min(last.open, last.close) - last.low) / (last.high - last.low) > 0.5;
  const reclaim = prev && last.close > prev.open;
  if ((isYang && volOk) || (hammer && volOk) || (reclaim && volOk)) {
    stabilize = true;
    lines.push(line(OK, `企稳信号：今日${hammer ? "长下影" : isYang ? "放量止跌阳" : "收复昨日实体"}（量比 ${(last.vol / vma5).toFixed(1)}×），有放量确认`));
  } else if (isYang || hammer) {
    lines.push(line(WARN, `企稳信号：有形态但量不足（${vma5 ? (last.vol / vma5).toFixed(2) : "—"}×5日均量），弱信号只观察`));
  } else lines.push(line(BAD, `企稳信号：今日无止跌形态，未企稳`));

  // 4 空间与压力
  const resist = [ma10, ma20].filter(x => x && x > price).sort((a, b) => a - b);
  const nearR = resist[0];
  if (nearR) {
    const sp = (nearR / price - 1) * 100;
    if (sp >= 5) { space = true; lines.push(line(OK, `空间压力：距最近压力（均线 ${fmtN(nearR)}）${sp.toFixed(1)}%，空间够`)); }
    else lines.push(line(WARN, `空间压力：距压力 ${fmtN(nearR)} 仅 ${sp.toFixed(1)}%（<5%），贴近压力，空间不足`));
  }

  // 5 排雷
  if (/ST|退/.test(ctx.row.f14)) { veto = true; lines.push(line(BAD, `排雷：ST/退市风险，一票否决`)); }
  else lines.push(line(OK, `排雷：名称无 ST/退市标记（财务暴雷/公告需人工另行核验）`));

  // 6 题材验证
  lines.push(line(WARN, `题材验证：催化/板块共振需人工核对，本模块不自动判定`));

  let verdict, vCls;
  if (last.pct > 7) { verdict = "启动窗口已过·追高风险大"; vCls = "warn"; }
  else if (veto || (!oversold && !stabilize)) { verdict = "回避"; vCls = "bad"; }
  else if (oversold && stabilize && space) { verdict = "出现脉冲信号（历史统计多为 1-3 天）"; vCls = "good"; }
  else { verdict = "观察"; vCls = "warn"; }
  const stop = fmtN(Math.min(last.low, prev ? prev.low : last.low));
  lines.push(`<div class="anaVerdict ${vCls}">判定：${verdict}</div>`);
  if (vCls === "good")
    lines.push(`<div class="anaNote">参考位：上方压力 MA10 ${fmtN(ma10)} · 历史形态上，收盘跌破 ${stop}（今日/昨日最低）通常视为反弹失败信号 · 次日低开/杀跌在历史回测中通常意味着脉冲结束 · 该框架不提供仓位建议</div>`);
  return { title: "超跌反弹 · 极短线博弈", verdict, vCls,
    brief: `回撤 ${dd60.toFixed(1)}%，RSI ${rsi === null ? "—" : rsi.toFixed(0)}，${stabilize ? "有企稳信号" : "未企稳"}`,
    html: lines.join("") };
}

// —— 3030战法·支撑压力（a-share-3030-strategy，日线级别）——
export function eval3030(ctx) {
  const { price, bars } = ctx;
  const c = bars.map(b => b.close);
  const ma30 = smaLast(c, 30), ma30p = smaLast(c.slice(0, -5), 30);
  const ma60v = smaLast(c, 60), ma120 = smaLast(c, 120);
  const lines = [];

  let state = "震荡";
  if (ma30 && ma30p) {
    const slope = (ma30 / ma30p - 1) * 100;
    if (slope > 0.5) state = "上升"; else if (slope < -0.5) state = "下降";
    lines.push(line(state === "上升" ? OK : state === "下降" ? BAD : WARN,
      `市场状态：${state}（MA30 近5日斜率 ${slope.toFixed(2)}%，现价${price > ma30 ? "站上" : "跌破"} MA30 ${fmtN(ma30)}）`));
  }

  const { hi, lo } = pivots(bars, 3);
  const supPts = [], resPts = [];
  if (ma30 && ma30 < price) supPts.push({ p: ma30, src: "MA30" });
  if (ma60v && ma60v < price) supPts.push({ p: ma60v, src: "MA60" });
  if (ma120 && ma120 < price) supPts.push({ p: ma120, src: "MA120" });
  if (ma30 && ma30 > price) resPts.push({ p: ma30, src: "MA30" });
  if (ma60v && ma60v > price) resPts.push({ p: ma60v, src: "MA60" });
  lo.slice(-8).forEach(x => { if (x.p < price * 0.995) supPts.push({ p: x.p, src: "前低 " + x.d.slice(5) }); });
  hi.slice(-8).forEach(x => { if (x.p > price * 1.005) resPts.push({ p: x.p, src: "前高 " + x.d.slice(5) }); });
  // 未回补缺口
  for (let i = 1; i < bars.length; i++) {
    if (bars[i].low > bars[i - 1].high) { // 向上缺口 → 支撑
      const zl = bars[i - 1].high;
      const filled = bars.slice(i + 1).some(b => b.low <= zl);
      if (!filled && zl < price) supPts.push({ p: zl, src: "缺口 " + bars[i].date.slice(5) });
    } else if (bars[i].high < bars[i - 1].low) { // 向下缺口 → 压力
      const zh = bars[i - 1].low;
      const filled = bars.slice(i + 1).some(b => b.high >= zh);
      if (!filled && zh > price) resPts.push({ p: zh, src: "缺口 " + bars[i].date.slice(5) });
    }
  }

  const supAll = makeZones(supPts).filter(z => z.mid < price);
  const resAll = makeZones(resPts).filter(z => z.mid > price);
  // 展示按共振评分排序；剧本取最贴近现价的区间（支撑取最高者、压力取最近者）
  const sup = [...supAll].sort((a, b) => b.score - a.score || b.mid - a.mid).slice(0, 3);
  const res = [...resAll].sort((a, b) => b.score - a.score || a.mid - b.mid).slice(0, 3);

  const zoneTxt = z => `${fmtN(z.lo)} ~ ${fmtN(z.hi)}（${z.srcs.join(" + ")}，共振 ${z.score}）`;
  lines.push(`<div class="anaSub">支撑区（按共振排序）</div>`);
  lines.push(sup.length ? sup.map(z => line("", zoneTxt(z))).join("") : line(WARN, "下方无明显候选支撑"));
  lines.push(`<div class="anaSub">压力区（按共振排序）</div>`);
  lines.push(res.length ? res.map(z => line("", zoneTxt(z))).join("") : line(WARN, "上方无明显候选压力"));

  const s1 = supAll.length ? supAll.reduce((a, b) => a.mid > b.mid ? a : b) : null; // 最贴近现价的支撑
  const r1 = resAll.length ? resAll.reduce((a, b) => a.mid < b.mid ? a : b) : null; // 最贴近现价的压力
  lines.push(`<div class="anaSub">互斥剧本（按收盘价确认，非影线）</div>`);
  if (s1) lines.push(line("", `守住：收盘不破 ${fmtN(s1.lo)} → 支撑有效；失效位：收盘跌破 ${fmtN(s1.lo * 0.99)}`));
  if (r1) lines.push(line("", `突破：收盘站上 ${fmtN(r1.hi)} → 有效突破，看高一档；假突破识别：放量长上影/三日收回区间=诱多`));
  if (s1) lines.push(line("", `跌破：收盘跌破 ${fmtN(s1.lo)} 且次日不能收回 → 历史形态上视为支撑失效信号`));
  lines.push(`<div class="anaNote">仅日线级别（5/15/30/60分钟多周期结构未在浏览器端展开）· 点位为区间而非精确值 · 该框架由公开内容归纳，不构成投资建议</div>`);
  const vCls = state === "上升" ? "good" : state === "下降" ? "bad" : "warn";
  return { title: "3030战法 · 支撑压力（日线）", verdict: "市场状态：" + state, vCls,
    brief: `支撑 ${s1 ? fmtN(s1.lo) + "~" + fmtN(s1.hi) : "—"} · 压力 ${r1 ? fmtN(r1.lo) + "~" + fmtN(r1.hi) : "—"}`,
    levels: { s1: s1 ? { lo: s1.lo, hi: s1.hi } : null, r1: r1 ? { lo: r1.lo, hi: r1.hi } : null },
    html: lines.join("") };
}

// —— 资金流向（a-share-money-flow，仅辅助验证）——
export function evalMoneyFlow(ctx) {
  const { mf, bars } = ctx;
  if (!mf || !mf.length)
    return { title: "资金流向 · 辅助验证", verdict: "未验证", vCls: "dim",
      html: line(WARN, "资金流数据不可用，本维度未验证（不可用不解释为空仓信号）") };
  const amtByDate = {};
  bars.forEach(b => { amtByDate[b.date] = b.amount; });
  const last = mf[mf.length - 1];
  const amt = amtByDate[last.date];
  const ratio = amt ? last.main / amt * 100 : null;
  const dayPct = (bars.find(b => b.date === last.date) || {}).pct;
  const sum5 = mf.slice(-5).reduce((s, x) => s + x.main, 0) / 1e8;
  const inDays = mf.slice(-5).filter(x => x.main > 0).length;
  const lines = [];

  let dir;
  if (last.main < 0 && dayPct < 0) dir = "同向走弱（资金面确认下跌）";
  else if (last.main > 0 && dayPct > 0) dir = "同向走强（资金面确认上涨）";
  else if (last.main < 0 && dayPct > 0) dir = "背离！主力流出+价涨，疑似拉高出货/散户接盘";
  else dir = "背离：主力流入+价跌，逆势吸纳还是对倒需结合趋势位置判断";
  lines.push(line(dir.includes("背离") ? WARN : OK,
    `最近一日（${last.date}）：主力净${last.main > 0 ? "流入" : "流出"} ${Math.abs(last.main / 1e8).toFixed(2)} 亿` +
    (ratio !== null ? `，净占比 ${ratio.toFixed(1)}%${Math.abs(ratio) >= 20 ? "（力度很强）" : Math.abs(ratio) >= 10 ? "（力度较大）" : ""}` : "") +
    `，${dir}`));
  lines.push(line(sum5 > 0 ? OK : WARN,
    `近5日：累计净${sum5 > 0 ? "流入" : "流出"} ${Math.abs(sum5).toFixed(2)} 亿，${inDays} 日流入 / ${5 - inDays} 日流出`));
  lines.push(`<div class="anaSub">近5日分级净流入（亿）· 主力=超大单+大单</div>`);
  lines.push(`<table class="anaTable"><thead><tr><th class="l">日期</th><th>主力</th><th>超大单</th><th>大单</th><th>中单</th><th>小单</th><th>主力净占比</th></tr></thead><tbody>` +
    mf.slice(-5).map(x => {
      const a = amtByDate[x.date];
      const rt = a ? (x.main / a * 100).toFixed(1) + "%" : "—";
      const cell = val => `<td class="${val > 0 ? "up" : val < 0 ? "down" : ""}">${(val / 1e8).toFixed(2)}</td>`;
      return `<tr><td class="l">${x.date.slice(5)}</td>${cell(x.main)}${cell(x.super)}${cell(x.big)}${cell(x.mid)}${cell(x.small)}<td>${rt}</td></tr>`;
    }).join("") + `</tbody></table>`);
  lines.push(`<div class="anaNote">资金流是按成交单大小的事后拆分统计，可被对倒/拆单伪造——只作最后辅助印证：趋势 > 量价形态 > 资金流，绝不单独定买卖</div>`);
  const vCls = dir.includes("背离") ? "warn" : sum5 > 0 ? "good" : "warn";
  return { title: "资金流向 · 辅助验证", verdict: dir.split("（")[0].split("：")[0], vCls, brief: dir, html: lines.join("") };
}

// —— 基本面快照（行情口径，无 F10 深度财务）——
export function evalFundamental(ctx) {
  const r = ctx.row;
  const item = (n, v) => `<div class="anaKV"><span>${n}</span><b>${v}</b></div>`;
  const lines = [`<div class="anaGrid">` +
    item("行业", esc(r.f100 || "—")) +
    item("总市值", fmtYiT(r.f20)) +
    item("流通市值", fmtYiT(r.f21)) +
    item("市盈率(动)", fmtN(r.f9, 1)) +
    item("市净率", fmtN(r.f23, 2)) +
    item("60日涨幅", typeof r.f24 === "number" ? r.f24.toFixed(1) + "%" : "—") +
    item("年初至今", typeof r.f25 === "number" ? r.f25.toFixed(1) + "%" : "—") +
    item("换手率", typeof r.f8 === "number" ? r.f8.toFixed(2) + "%" : "—") +
    item("成交额", fmtYiT(r.f6)) +
    item("振幅", typeof r.f7 === "number" ? r.f7.toFixed(2) + "%" : "—") +
    item("量比", fmtN(r.f10, 2)) +
    `</div>`];
  const warns = [];
  if (typeof r.f9 === "number" && r.f9 < 0) warns.push("动态市盈率为负（亏损状态），回避型资金谨慎");
  if (typeof r.f9 === "number" && r.f9 > 100) warns.push(`PE ${r.f9.toFixed(0)} 极高，估值透支风险`);
  if (typeof r.f23 === "number" && r.f23 > 10) warns.push(`PB ${r.f23.toFixed(1)} 偏高`);
  warns.forEach(w => lines.push(line(WARN, w)));
  if (!warns.length) lines.push(line(OK, "估值快照未见极端值（仅 PE/PB 粗筛口径）"));
  lines.push(`<div class="anaNote">仅为行情口径快照（PE/PB/市值），ROE、营收、商誉、解禁减持等深度财务需另行查 F10 核验</div>`);
  const vCls = warns.length ? "warn" : "good";
  return { title: "基本面 · 行情快照", verdict: warns.length ? "有提示" : "未见极端值", vCls,
    brief: warns.join("；") || `PE ${fmtN(r.f9, 1)} / PB ${fmtN(r.f23, 2)}，无极端值`, html: lines.join("") };
}

// —— 综合分析（汇总各战法判定 + 情绪环境，给出主线结论；置于页签首位）——
// 主线逻辑：顺势优先（趋势波段>趋势启动>超跌脉冲）；三套尺子结论相反属正常，只选其一执行
// 情绪只作调节项不作否决项：冰点期降级信号评级、亢奋期提示追高风险（符合 skills「趋势>量价>资金/情绪」）
export function evalOverall(ctx, mods, senti, reso, heat) {
  const [t, s, o, z] = mods;   // 趋势波段 / 趋势启动 / 超跌反弹 / 3030 / 资金 / 基本面
  const lines = [];

  let verdict, vCls, mainTxt;
  if (t.vCls === "good" && !t.waitBuy) {
    verdict = "主线：趋势波段"; vCls = "good";
    mainTxt = "顺势框架成立且有经典买点信号——关键参考价位见「趋势波段」页；历史形态上收盘跌破支撑位通常视为趋势失效信号。";
  } else if (s.vCls === "good") {
    verdict = "主线：趋势启动"; vCls = "good";
    mainTxt = "低位起跳结构得分最高——历史形态上，放量突破确认后才进入统计胜率较高的区间，详见「趋势启动」页。";
  } else if (o.vCls === "good") {
    verdict = "仅超跌脉冲信号"; vCls = "warn";
    mainTxt = "只有超跌反弹维度出现信号——历史统计上这类逆势脉冲持续时间短（1-3 天）、失败率高，与顺势框架逻辑不同，不可混用。";
  } else if (t.vCls === "good" && t.waitBuy) {
    verdict = "趋势良好，暂无买点信号"; vCls = "good";
    mainTxt = "多头排列已确立但暂无经典买点信号——历史形态上，放量突破或回踩企稳通常被视为右侧确认信号，详见「趋势波段」页。";
  } else if (t.vCls === "bad") {
    verdict = "回避"; vCls = "bad";
    mainTxt = "趋势维度命中排除项——顺势框架直接淘汰该标的。";
  } else if (t.trendPass && t.vCls === "warn") {
    verdict = "趋势向上但乖离偏高"; vCls = "warn";
    mainTxt = "多头排列成立但离 MA20 乖离 >18%——当前乖离偏高，框架不输出介入信号。";
  } else {
    // 各战法信号都不充分——给出动态描述，而不是统一模板
    const reasons = [];
    if (!t.trendPass) reasons.push("均线缠绕，方向未明");
    if (s.vCls === "dim") reasons.push("趋势启动得分低（<40/130），不在低位蓄势");
    if (o.vCls === "warn" && !o.verdict.includes("不适用")) reasons.push("超跌反弹条件不满足（不够超跌/未企稳）");
    verdict = "观察"; vCls = "warn";
    mainTxt = (reasons.length ? reasons.join("；") + "——" : "") + "形态/量能尚未确认，趋势不明时框架不输出信号。";
  }

  // 情绪调节（只调节不否决，阈值与 computeSentiment 的 level 区间同步）
  if (senti) {
    if (senti.temp < 20 && vCls === "good") {
      vCls = "warn";
      mainTxt = `⚠️ 市场处于冰点期（情绪 ${senti.temp}），顺势信号评级降一档——${mainTxt} 冰点期历史胜率显著更低。`;
    } else if (senti.temp < 20 && o.vCls === "good") {
      mainTxt = `冰点期（情绪 ${senti.temp}）恐慌出清更充分，超跌博弈环境成立——${mainTxt}`;
    } else if (senti.temp >= 80 && vCls !== "bad") {
      mainTxt += ` ⚠️ 市场亢奋期（情绪 ${senti.temp}），历史统计上追高风险显著放大。`;
    }
  }
  lines.push(`<div class="anaVerdict ${vCls}">综合结论：${verdict}</div>`);
  lines.push(`<div class="anaLine">${mainTxt}</div>`);

  // 情绪环境（市场温度 + 板块共振 + 个股情绪特征）
  if (senti) {
    // level → 标记/标签 class（与 computeSentiment 的 level 区间同步）
    const lvMark = senti.temp < 20 || senti.temp >= 80 ? WARN
      : (senti.temp < 40 || senti.temp >= 60) ? "🟡" : OK;
    const lvTag = senti.temp < 20 ? "bad"
      : senti.temp < 40 ? "warn"
      : senti.temp < 60 ? "dim"
      : senti.temp < 80 ? "warn" : "bad";
    const upPct = (senti.upRatio * 100).toFixed(0);
    const kv = (n, v) => `<div class="anaKV"><span>${n}</span><b>${v}</b></div>`;
    // 统计范围：从 DOM 读取市场勾选（与 sentiBadge 同源）
    const mktLabels = [...document.querySelectorAll(".mkt:checked")].map(c => c.parentElement.textContent.trim());
    const scope = mktLabels.length ? mktLabels.join("、") : "全市场";
    lines.push(`<div class="anaSub">情绪环境 <span class="anaTag dim" style="font-size:10px">范围：${esc(scope)} · ${senti.valid} 家</span></div>`);
    lines.push(`<div class="anaLine">${lvMark} 市场温度：<b style="font-size:14px;font-family:var(--mono)">${senti.temp}</b> ` +
      `<span class="anaTag ${lvTag}">${senti.level}</span>` +
      (senti.volRatio !== null
        ? ` · 指数量能 <b>${senti.volRatio.toFixed(2)}×</b>5日均额 <span class="anaTag ${senti.volSrc === "缺失（按中性计）" ? "dim" : senti.volSrc === "盘中外推" ? "warn" : "good"}">${senti.volSrc}</span>${senti.volNote}`
        : ` · <span class="anaTag dim">指数量能缺失</span>`) +
      `</div>`);
    lines.push(`<div class="anaGrid">` +
      kv("上涨 / 总数", `${senti.up} / ${senti.valid} 家 (${upPct}%)`) +
      kv("涨停 / 跌停", `${senti.limitUp} / ${senti.limitDown}`) +
      kv("大跌(>5%)", `${senti.bigDown} 家`) +
      kv("下跌家数", `${senti.down} 家`) +
      `</div>`);
  }
  if (reso && reso.n > 1) {
    const pct = (reso.ratio * 100).toFixed(0);
    lines.push(line(reso.ratio >= 0.3 ? OK : WARN,
      `板块共振：同行业（${esc(reso.name)}）${reso.n} 家中 ${reso.up} 家涨超 3%（${pct}%）——${reso.ratio >= 0.3 ? "有板块效应，信号更可靠" : "板块效应弱，偏个股行为"}`));
  }
  if (heat && (heat.last10 > 0 || heat.streak > 0)) {
    lines.push(line(heat.streak >= 2 || heat.last10 >= 3 ? WARN : OK,
      `个股情绪：近10日涨停 ${heat.last10} 次${heat.streak ? `，当前 ${heat.streak} 连板` : ""}` +
      (heat.streak >= 2 || heat.last10 >= 3 ? "——情绪高标，波动和追高风险大" : "")));
  }

  // 各战法判定一览（点击行跳转对应页签；i+1 因为本页占第 0 位）
  lines.push(`<div class="anaSub">各战法判定（点击行查看详情）</div>`);
  lines.push(`<table class="anaTable anaJumpTbl"><tbody>` + mods.map((m, i) =>
    `<tr class="anaJump" data-i="${i + 1}"><td class="l">${m.title.split(" · ")[0]}</td>` +
    `<td style="white-space:normal"><span class="anaTag ${m.vCls}">${esc(m.verdict)}</span></td>` +
    `<td class="l" style="white-space:normal;color:var(--dim)">${esc(m.brief || "")}</td></tr>`).join("") +
    `</tbody></table>`);

  // 关键价位（取 3030 模块的最贴近支撑/压力）
  const lv = z.levels || {};
  if (lv.s1 || lv.r1) {
    lines.push(`<div class="anaSub">关键价位（详见 3030战法 页）</div>`);
    lines.push(`<div class="anaGrid">` +
      (lv.s1 ? `<div class="anaKV"><span>最近支撑</span><b>${fmtN(lv.s1.lo)} ~ ${fmtN(lv.s1.hi)}</b></div>` : "") +
      (lv.r1 ? `<div class="anaKV"><span>最近压力</span><b>${fmtN(lv.r1.lo)} ~ ${fmtN(lv.r1.hi)}</b></div>` : "") +
      `</div>`);
  }

  lines.push(`<div class="anaNote">提醒：趋势波段、趋势启动、超跌反弹是三把不同的尺子——同一只票结论相反很正常，选定一把执行到底，不混用；资金流向只作辅助印证，不单独定买卖。</div>`);
  return { title: "综合分析 · 主线结论", verdict, vCls, brief: mainTxt, html: lines.join("") };
}
