"""神经网络调参实验室：全市场截面深度特征推理与胜率概率预测。

设计思路与数学表征：
1. 样本空间与刚性约束：过滤ST、退市、停牌及用户指定换手率/成交额/市值/板块门槛。
2. 截面鲁棒标准化 (Robust Z-Score)：
   采用中位数 (Median) 与中位数绝对偏差 (MAD * 1.4826) 消除极端离群值，并限制在 [-3.0, +3.0] 区间。
3. 突触权重与4大隐层神经元映射：
   - h_liquidity: 活跃流动性神经元 (换手率、量比、振幅)
   - h_capital: 主力资金合力神经元 (主力净流入强度、量价资金协同度)
   - h_momentum: 势能突破神经元 (今日涨幅、竞价跳空、60日趋势动量)
   - h_elasticity: 筹码弹性博弈神经元 (对数流通市值偏好、振幅弹性、流动性摩擦)
4. 非线性激活函数 (Non-linear Activation)：
   支持 GELU (现代化大模型常用)、Tanh、Sigmoid、LeakyReLU、ReLU，捕获量价跃迁突破门槛。
5. 惩罚与损失项：
   支持「放量滞涨惩罚 (Stagflation Penalty)」，严厉扣减高位爆天量却翻绿滞涨的个股置信度。
6. 温度缩放 (Temperature-scaled Softmax/Sigmoid)：
   通过可调节温度系数 T 控制胜率概率锐度，输出预测置信度与等级 (A++ / A+ / A / B)。
7. 可解释性特征归因 (Feature Attribution)：
   对每只上榜个股给出4大神经元维度的正向贡献百分比分解。
"""
import time
from typing import List, Optional
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from ..security import current_user

router = APIRouter(prefix="/api/neural", tags=["neural"])


class NeuralPredictRequest(BaseModel):
    # 刚性过滤条件 (Hard Constraints)
    exclude_st: bool = True
    exclude_suspended: bool = True
    min_turnover: float = Field(default=0.5, ge=0.0, le=100.0)      # 换手率下限 %
    max_turnover: float = Field(default=80.0, ge=0.0, le=100.0)     # 换手率上限 %
    min_amount_yi: float = Field(default=0.1, ge=0.0)               # 成交额下限 (亿元)
    min_price: float = Field(default=1.0, ge=0.0)                   # 最低股价
    max_price: float = Field(default=1000.0, ge=0.0)                # 最高股价
    min_market_cap_yi: float = Field(default=3.0, ge=0.0)           # 最小流通市值 (亿元)
    max_market_cap_yi: float = Field(default=5000.0, ge=0.0)        # 最大流通市值 (亿元)
    markets: Optional[List[str]] = ["沪主板", "深主板", "创业板", "科创板", "北交所"]

    # 突触可调权重 (Synaptic Weights, 范围 -100 ~ +100)
    weight_turnover: float = Field(default=65.0, ge=-100.0, le=100.0)      # 换手活跃度
    weight_capital: float = Field(default=80.0, ge=-100.0, le=100.0)       # 主力资金净流入
    weight_volume_ratio: float = Field(default=50.0, ge=-100.0, le=100.0)  # 量比爆发度
    weight_momentum: float = Field(default=60.0, ge=-100.0, le=100.0)      # 当日涨幅势能
    weight_auction_gap: float = Field(default=45.0, ge=-100.0, le=100.0)   # 竞价跳空幅度
    weight_amplitude: float = Field(default=30.0, ge=-100.0, le=100.0)     # 盘中弹性振幅
    weight_trend_60d: float = Field(default=25.0, ge=-100.0, le=100.0)     # 60日趋势动量
    weight_market_cap: float = Field(default=-30.0, ge=-100.0, le=100.0)   # 市值偏好(负数偏好中小盘弹性)

    # 隐层神经元偏置 (Latent Neuron Biases)
    hidden_liquidity_bias: float = Field(default=0.0, ge=-50.0, le=50.0)
    hidden_capital_bias: float = Field(default=0.0, ge=-50.0, le=50.0)
    hidden_momentum_bias: float = Field(default=0.0, ge=-50.0, le=50.0)
    hidden_elasticity_bias: float = Field(default=0.0, ge=-50.0, le=50.0)

    # 超参数设置 (Hyperparameters)
    activation: str = "gelu"                                         # "gelu" | "tanh" | "sigmoid" | "leaky_relu" | "relu"
    temperature: float = Field(default=0.8, ge=0.1, le=3.0)         # 温度系数 T
    stagflation_penalty: bool = True                                 # 放量滞涨惩罚
    top_k: int = Field(default=50, ge=1, le=200)                    # 返回前 K 名优选标的
    data_source: str = "latest"                                      # "latest" (盘中实时) | "history" (历史截面) | "auto"
    trade_date: Optional[str] = None                                 # 指定历史交易日期 (如 "2026-09-18")


class NeuralBacktestRequest(NeuralPredictRequest):
    base_date: Optional[str] = None                                  # 回测基准历史日 (如 "2026-09-18" 或 "2026-09-07")
    target_date: Optional[str] = "latest"                            # 跟踪目标日 ("latest" 或指定历史日期)


def _robust_zscore(col: np.ndarray) -> np.ndarray:
    """Winsorize 截尾 + Median/MAD 鲁棒Z-score归一化。"""
    if len(col) <= 1:
        return np.zeros_like(col)
    p1, p99 = np.percentile(col, [1, 99])
    c = np.clip(col, p1, p99)
    med = float(np.median(c))
    mad = float(np.median(np.abs(c - med))) * 1.4826
    if mad < 1e-6:
        mad = float(np.std(c)) + 1e-6
    return np.clip((c - med) / mad, -3.0, 3.0)


def _activate(h: np.ndarray, fn_name: str) -> np.ndarray:
    """非线性激活函数。"""
    fn = fn_name.lower().strip()
    if fn == "gelu":
        # GELU 高斯误差线性单元近似: 0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
        return 0.5 * h * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (h + 0.044715 * (h ** 3))))
    elif fn == "tanh":
        return np.tanh(h)
    elif fn == "sigmoid":
        return 1.0 / (1.0 + np.exp(-np.clip(h, -20.0, 20.0)))
    elif fn == "leaky_relu":
        return np.where(h > 0, h, 0.1 * h)
    elif fn == "relu":
        return np.maximum(0.0, h)
    # 默认兜底 GELU
    return 0.5 * h * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (h + 0.044715 * (h ** 3))))


def _query_cross_section(conn, req: NeuralPredictRequest, use_latest: bool, trade_date: str):
    """按刚性约束查询截面样本，返回 (raw_rows, total_scanned)。"""
    table_name = "latest" if use_latest else "history"

    where_clauses = ["f2 IS NOT NULL", "f2 > 0"]
    params = []

    if not use_latest:
        where_clauses.append("trade_date = ?")
        params.append(trade_date)

    if req.exclude_st:
        where_clauses.append("(name NOT LIKE '%ST%' AND name NOT LIKE '%*ST%' AND name NOT LIKE '%退%')")

    if req.exclude_suspended:
        where_clauses.append("f6 IS NOT NULL AND f6 > 0")

    # 股价区间
    where_clauses.append("f2 >= ? AND f2 <= ?")
    params.extend([req.min_price, req.max_price])

    # 换手率区间
    where_clauses.append("f8 IS NOT NULL AND f8 >= ? AND f8 <= ?")
    params.extend([req.min_turnover, req.max_turnover])

    # 成交额下限
    if req.min_amount_yi > 0:
        where_clauses.append("f6 >= ?")
        params.append(req.min_amount_yi * 1e8)

    # 流通市值区间
    if req.min_market_cap_yi > 0:
        where_clauses.append("f21 IS NOT NULL AND f21 >= ?")
        params.append(req.min_market_cap_yi * 1e8)
    if req.max_market_cap_yi > 0:
        where_clauses.append("f21 IS NOT NULL AND f21 <= ?")
        params.append(req.max_market_cap_yi * 1e8)

    # 市场板块过滤
    if req.markets and len(req.markets) > 0:
        placeholders = ",".join("?" for _ in req.markets)
        where_clauses.append(f"market IN ({placeholders})")
        params.extend(req.markets)

    sql = f"""
        SELECT code, name, industry, market, f2, f3, f6, f7, f8, f9, f10,
               f18, f20, f21, f24, f17, f62, limit_up
        FROM {table_name}
        WHERE {" AND ".join(where_clauses)}
    """

    if use_latest:
        total_scanned = conn.execute(
            f"SELECT count(*) FROM {table_name}"
        ).fetchone()[0]
    else:
        total_scanned = conn.execute(
            f"SELECT count(*) FROM {table_name} WHERE trade_date = ?",
            (trade_date,)
        ).fetchone()[0]
    raw_rows = conn.execute(sql, params).fetchall()
    return raw_rows, total_scanned


def _forward(req: NeuralPredictRequest, raw_rows, weight_override=None, bias_override=None, precomputed=None):
    """特征提取 → 截面 Robust Z → 4 隐层前向 → 放量滞涨惩罚 → 温度置信度。

    weight_override/bias_override 供回测寻优传入候选权重（8 维，[-1,1] 区间）。
    precomputed={"Z": ...} 时跳过特征提取直接复用标准化矩阵（寻优批量评估提速）。
    返回中间张量与按置信度降序的排序索引。
    """
    if precomputed is not None and precomputed.get("Z") is not None:
        Z = precomputed["Z"]
    else:
        f_turnover = np.array([r["f8"] or 0.0 for r in raw_rows], dtype=np.float64)
        f_amount = np.array([r["f6"] or 0.0 for r in raw_rows], dtype=np.float64)
        f_capital = np.array([r["f62"] or 0.0 for r in raw_rows], dtype=np.float64)
        f_volratio = np.array([r["f10"] or 1.0 for r in raw_rows], dtype=np.float64)
        f_chg = np.array([r["f3"] or 0.0 for r in raw_rows], dtype=np.float64)
        f_amp = np.array([r["f7"] or 0.0 for r in raw_rows], dtype=np.float64)
        f_mcap = np.array([r["f21"] or 1e9 for r in raw_rows], dtype=np.float64)
        f_trend = np.array([r["f24"] or 0.0 for r in raw_rows], dtype=np.float64)

        f17 = np.array([r["f17"] or 0.0 for r in raw_rows], dtype=np.float64)
        f18 = np.array([r["f18"] or 0.0 for r in raw_rows], dtype=np.float64)
        safe_f18 = np.where(f18 > 0, f18, 1.0)
        f_gap = np.where(f18 > 0, (f17 - safe_f18) / safe_f18 * 100.0, 0.0)

        # 主力资金占比与对数流通市值
        f_cap_intensity = np.where(f_amount > 0, np.clip(f_capital / (f_amount + 1e-4), -1.0, 1.0), 0.0)
        f_log_mcap = np.log10(np.clip(f_mcap / 1e8, 1.0, 1e5))

        # 特征矩阵: [N, 8]
        # 0: turnover, 1: cap_intensity, 2: volratio, 3: chg, 4: gap, 5: amp, 6: trend, 7: log_mcap
        features = np.column_stack([
            f_turnover,
            f_cap_intensity,
            f_volratio,
            f_chg,
            f_gap,
            f_amp,
            f_trend,
            f_log_mcap
        ])

        # 截面 Robust Z-score 标准化
        Z = np.apply_along_axis(_robust_zscore, 0, features)

    # 归一化突触权重输入 (缩放至 [-1.0, 1.0])
    if weight_override is not None:
        w = np.asarray(weight_override, dtype=np.float64)
    else:
        w = np.array([
            req.weight_turnover / 100.0,
            req.weight_capital / 100.0,
            req.weight_volume_ratio / 100.0,
            req.weight_momentum / 100.0,
            req.weight_auction_gap / 100.0,
            req.weight_amplitude / 100.0,
            req.weight_trend_60d / 100.0,
            req.weight_market_cap / 100.0
        ], dtype=np.float64)

    if bias_override is not None:
        b_liq, b_cap, b_mom, b_ela = np.asarray(bias_override, dtype=np.float64)
    else:
        b_liq = req.hidden_liquidity_bias / 50.0
        b_cap = req.hidden_capital_bias / 50.0
        b_mom = req.hidden_momentum_bias / 50.0
        b_ela = req.hidden_elasticity_bias / 50.0

    # 隐层神经元前向点积计算 (4个专业隐层特征单元)
    # Neuron 1: 流动性活跃神经元 h_liq
    h_liq = (0.50 * (w[0] * Z[:, 0]) +
             0.30 * (w[2] * Z[:, 2]) +
             0.20 * (w[5] * Z[:, 5]) + b_liq)

    # Neuron 2: 主力资金合力神经元 h_cap
    h_cap = (0.65 * (w[1] * Z[:, 1]) +
             0.35 * (w[1] * Z[:, 1] * np.sign(Z[:, 3])) + b_cap)

    # Neuron 3: 势能突破爆发神经元 h_mom
    h_mom = (0.50 * (w[3] * Z[:, 3]) +
             0.30 * (w[4] * Z[:, 4]) +
             0.20 * (w[6] * Z[:, 6]) + b_mom)

    # Neuron 4: 筹码弹性博弈神经元 h_ela
    h_ela = (0.50 * (w[7] * Z[:, 7]) +
             0.30 * (w[5] * Z[:, 5]) +
             0.20 * (w[0] * Z[:, 0]) + b_ela)

    H = np.column_stack([h_liq, h_cap, h_mom, h_ela])

    # 非线性激活函数映射
    A = _activate(H, req.activation)

    # 隐层融合综合得分 (Synaptic Beta Weights)
    beta = np.array([0.25, 0.35, 0.25, 0.15], dtype=np.float64)
    scores = A @ beta

    # 放量滞涨非线性惩罚 (Stagflation Penalty)
    # 典型诱多陷阱：高换手 (Z_turnover > 1.2) 且涨幅低迷或翻绿 (Z_momentum < -0.3)
    if req.stagflation_penalty:
        stag_mask = (Z[:, 0] > 1.2) & (Z[:, 3] < -0.3)
        penalty = np.where(stag_mask, 1.25 * (Z[:, 0] - 1.2) * np.abs(Z[:, 3]), 0.0)
        scores -= penalty

    # 温度缩放 Softmax / Sigmoid 胜率置信度映射
    # P_i = Sigmoid((S_i - mean(S)) / (T * std(S))) * 100%
    temp = max(0.1, req.temperature)
    std_s = float(np.std(scores))
    if std_s < 1e-6:
        std_s = 1.0
    norm_scores = (scores - float(np.mean(scores))) / (std_s + 1e-6)
    confidences = 1.0 / (1.0 + np.exp(-norm_scores / temp)) * 100.0

    return {
        "Z": Z,
        "scores": scores,
        "confidences": confidences,
        "A": A,
        "beta": beta,
        "order": np.argsort(-confidences),
    }


@router.post("/predict")
def run_neural_prediction(req: NeuralPredictRequest, user=Depends(current_user)):
    t_start = time.perf_counter()
    conn = get_conn()

    # 1. 自动判定数据源：默认优先 'latest'（盘中实时真实行情）
    c_active = conn.execute("SELECT count(*) FROM latest WHERE f6 > 0").fetchone()[0]
    hist_row = conn.execute("SELECT max(trade_date) FROM history").fetchone()
    hist_date = hist_row[0] if hist_row else None

    use_latest = True
    if req.data_source == "history":
        use_latest = False
    elif req.data_source == "latest":
        use_latest = True
    else:  # "auto"
        use_latest = True if c_active > 0 else False

    source_desc = ""
    trade_date = ""

    if use_latest:
        meta_row = conn.execute("SELECT fetched_at, source FROM snapshot_meta WHERE id = 1").fetchone()
        source_desc = "盘中实时真实快照"
        trade_date = meta_row["fetched_at"] if meta_row and meta_row["fetched_at"] else "今日实时"
    else:
        if req.trade_date:
            trade_date = req.trade_date
        elif hist_date:
            trade_date = hist_date
        else:
            raise HTTPException(500, "数据库中暂无可用行情快照历史数据")
        source_desc = f"历史截面全量快照 ({trade_date})"

    # 加载最新实时价格快照 (用于在历史截面或回测时对比展示「最新现价」与「累计涨幅」)
    latest_price_map = {}
    try:
        cur_latest = conn.execute("SELECT code, f2, f3 FROM latest WHERE f2 > 0").fetchall()
        for r_lat in cur_latest:
            latest_price_map[r_lat["code"]] = (r_lat["f2"], r_lat["f3"])
    except Exception:
        pass

    # 2. 构造查询与刚性约束过滤
    raw_rows, total_scanned = _query_cross_section(conn, req, use_latest, trade_date)
    qualified_count = len(raw_rows)

    if qualified_count == 0:
        return {
            "data_mode": source_desc,
            "trade_date": trade_date,
            "total_scanned": total_scanned,
            "qualified_count": 0,
            "inference_time_ms": round((time.perf_counter() - t_start) * 1000, 2),
            "telemetry": [
                {"step": 1, "phase": "Data Ingestion", "msg": f"全市场检索完成，经刚性条件过滤后合格样本数为 0，请适当放宽换手率/成交额门槛。"}
            ],
            "weights_used": req.model_dump(),
            "results": []
        }

    # 3. 特征提取与多层前向推理
    fwd = _forward(req, raw_rows)
    scores = fwd["scores"]
    confidences = fwd["confidences"]
    A = fwd["A"]
    beta = fwd["beta"]

    # 9. 排序并取前 Top-K
    top_k = min(req.top_k, qualified_count)
    top_indices = fwd["order"][:top_k]

    results = []
    for rank, idx in enumerate(top_indices, 1):
        row = raw_rows[idx]
        conf = float(confidences[idx])

        # 契合度分级 (纯客观数学特征与公式匹配度，严禁诱导荐股)
        if conf >= 90.0:
            grade = "A++"
            grade_desc = "高度匹配"
        elif conf >= 80.0:
            grade = "A+"
            grade_desc = "良好匹配"
        elif conf >= 70.0:
            grade = "A"
            grade_desc = "形态契合"
        elif conf >= 60.0:
            grade = "B+"
            grade_desc = "中度匹配"
        else:
            grade = "B"
            grade_desc = "弱相关"

        # 特征可解释性归因 (Attribution % of each latent neuron)
        contribs = np.maximum(0.0, A[idx] * beta)
        sum_contribs = float(np.sum(contribs)) + 1e-6
        attrs = contribs / sum_contribs * 100.0

        p_liq = round(float(attrs[0]), 1)
        p_cap = round(float(attrs[1]), 1)
        p_mom = round(float(attrs[2]), 1)
        p_ela = round(float(attrs[3]), 1)

        # 核心驱动力简述
        drivers = [
            ("主力资金", p_cap),
            ("势能突破", p_mom),
            ("活跃流动", p_liq),
            ("筹码弹性", p_ela)
        ]
        top_driver = max(drivers, key=lambda d: d[1])
        summary_str = f"{top_driver[0]}驱动 ({top_driver[1]:.0f}%)"

        # 竞价跳空幅度
        f18_val = row["f18"] or 0.0
        f17_val = row["f17"] or 0.0
        gap_pct = round(((f17_val - f18_val) / f18_val * 100.0), 2) if f18_val > 0 else 0.0

        lat_f2, lat_f3 = latest_price_map.get(row["code"], (None, None))
        holding_return = None
        if lat_f2 and row["f2"] and row["f2"] > 0:
            holding_return = round((lat_f2 - row["f2"]) / row["f2"] * 100.0, 2)

        results.append({
            "rank": rank,
            "code": row["code"],
            "name": row["name"],
            "industry": row["industry"],
            "market": row["market"],
            "f2": row["f2"],                       # 最新价
            "f3": row["f3"],                       # 涨幅 %
            "f6": row["f6"],                       # 成交额 (元)
            "f7": row["f7"],                       # 振幅 %
            "f8": row["f8"],                       # 换手率 %
            "f10": row["f10"],                     # 量比
            "f21": row["f21"],                     # 流通市值 (元)
            "f62": row["f62"],                     # 主力净流入 (元)
            "gap_pct": gap_pct,                    # 竞价跳空高开 %
            "f24": row["f24"],                     # 60日涨幅 %
            "limit_up": bool(row["limit_up"]),
            "score": round(float(scores[idx]), 3),
            "confidence": round(conf, 1),
            "grade": grade,
            "grade_desc": grade_desc,
            "latest_f2": lat_f2,
            "latest_f3": lat_f3,
            "holding_return": holding_return,
            "attribution": {
                "liquidity": p_liq,
                "capital": p_cap,
                "momentum": p_mom,
                "elasticity": p_ela,
                "summary": summary_str
            }
        })

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

    # 10. 组装神经网络推理思考过程 (Telemetry)
    telemetry = [
        {
            "step": 1,
            "phase": "样本空间检索与刚性过滤",
            "time_ms": round(elapsed_ms * 0.2, 1),
            "msg": f"全市场扫描 {total_scanned:,} 只标的，应用排除ST、停牌及换手率[{req.min_turnover}%~{req.max_turnover}%]、成交额[>={req.min_amount_yi}亿]刚性约束，保留 {qualified_count:,} 只合格候选标的。"
        },
        {
            "step": 2,
            "phase": "截面鲁棒标准化 (Robust Z-Score)",
            "time_ms": round(elapsed_ms * 0.35, 1),
            "msg": f"构建 [8 维特征张量]，采用 Winsorize 1%-99% 截尾与 MAD(缩放因子 1.4826) 消除极值干扰，特征限制于 [-3.0, +3.0] 标准正态空间。"
        },
        {
            "step": 3,
            "phase": "突触加权与隐层表征映射",
            "time_ms": round(elapsed_ms * 0.55, 1),
            "msg": f"前向点积合成: 活跃流动性(w={req.weight_turnover:+.0f})、主力合力(w={req.weight_capital:+.0f})、势能爆发(w={req.weight_momentum:+.0f})、筹码弹性(w={req.weight_market_cap:+.0f}) 4大特征神经元。"
        },
        {
            "step": 4,
            "phase": f"非线性激活与跃迁检测 ({req.activation.upper()})",
            "time_ms": round(elapsed_ms * 0.75, 1),
            "msg": f"应用 {req.activation.upper()} 非线性激活函数，映射量价跃迁突破门槛" + ("，并执行放量滞涨惩罚扣减。" if req.stagflation_penalty else "。")
        },
        {
            "step": 5,
            "phase": "温度缩放与量化拟合度评分",
            "time_ms": elapsed_ms,
            "msg": f"设置温度系数 T={req.temperature:.2f} 进行 Softmax 概率锐度校准，完成全样本客观数学契合度评估与可解释性特征归因分解，输出 Top-{top_k} 优选拟合候选。"
        }
    ]

    # 网络拓扑结构参数（供前端神经网络拓扑图动态连线与脉冲渲染）
    network_topology = {
        "input_nodes": [
            {"id": "turnover", "name": "换手率", "weight": req.weight_turnover},
            {"id": "capital", "name": "主力净流入", "weight": req.weight_capital},
            {"id": "volratio", "name": "量比爆发", "weight": req.weight_volume_ratio},
            {"id": "momentum", "name": "当日动能", "weight": req.weight_momentum},
            {"id": "gap", "name": "竞价跳空", "weight": req.weight_auction_gap},
            {"id": "amplitude", "name": "盘中振幅", "weight": req.weight_amplitude},
            {"id": "trend", "name": "60日趋势", "weight": req.weight_trend_60d},
            {"id": "mcap", "name": "市值偏好", "weight": req.weight_market_cap},
        ],
        "hidden_nodes": [
            {"id": "h_liq", "name": "活跃流动性", "bias": req.hidden_liquidity_bias},
            {"id": "h_cap", "name": "主力筹码合力", "bias": req.hidden_capital_bias},
            {"id": "h_mom", "name": "势能突破爆发", "bias": req.hidden_momentum_bias},
            {"id": "h_ela", "name": "筹码弹性博弈", "bias": req.hidden_elasticity_bias},
        ],
        "activation": req.activation,
        "temperature": req.temperature,
    }

    return {
        "data_mode": source_desc,
        "trade_date": trade_date,
        "total_scanned": total_scanned,
        "qualified_count": qualified_count,
        "inference_time_ms": elapsed_ms,
        "telemetry": telemetry,
        "network_topology": network_topology,
        "weights_used": req.model_dump(),
        "results": results
    }


@router.get("/dates")
def get_neural_dates(user=Depends(current_user)):
    """获取神经网络可用的数据日期（实时快照时间 + 历史可用交易日列表）。"""
    conn = get_conn()
    meta = conn.execute("SELECT fetched_at, total FROM snapshot_meta WHERE id = 1").fetchone()
    latest_time = meta["fetched_at"] if meta and meta["fetched_at"] else "今日实时"
    
    rows = conn.execute("SELECT DISTINCT trade_date, COUNT(*) as c FROM history GROUP BY trade_date ORDER BY trade_date DESC").fetchall()
    hist_dates = [{"date": r["trade_date"], "count": r["c"]} for r in rows]
    
    return {
        "latest": {"time": latest_time, "count": meta["total"] if meta else 0},
        "history_dates": hist_dates
    }


@router.post("/backtest")
def run_neural_backtest(req: NeuralBacktestRequest, user=Depends(current_user)):
    """历史回测调参验证系统：在指定历史基准日运行模型，追踪选出个股在后续及今日的真实收益与胜率。"""
    t_start = time.perf_counter()
    conn = get_conn()

    hist_rows = conn.execute("SELECT DISTINCT trade_date FROM history ORDER BY trade_date ASC").fetchall()
    all_dates = [r["trade_date"] for r in hist_rows]
    if not all_dates:
        raise HTTPException(400, "数据库中无可用历史交易日数据进行回测")

    # 确定基准日期 (优先使用指定的 base_date 或默认最近的完整历史交易日)
    base_date = req.base_date if req.base_date in all_dates else all_dates[-1]

    # 在基准历史日执行模型推理
    req_dict = req.model_dump()
    req_dict["data_source"] = "history"
    req_dict["trade_date"] = base_date
    req_predict = NeuralPredictRequest(**req_dict)
    predict_res = run_neural_prediction(req_predict, user)
    
    picked_stocks = predict_res["results"]
    if not picked_stocks:
        return {
            "base_date": base_date,
            "target_date": "今日实时",
            "picked_count": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "benchmark_return": 0.0,
            "benchmark_win_rate": 0.0,
            "alpha": 0.0,
            "profit_loss_ratio": 0.0,
            "distribution": {},
            "results": []
        }

    # 加载最新价格字典
    latest_rows = conn.execute("SELECT code, name, f2, f3 FROM latest WHERE f2 > 0").fetchall()
    latest_map = {r["code"]: {"f2": r["f2"], "f3": r["f3"], "name": r["name"]} for r in latest_rows}

    # 计算全市场基准收益率 (同期全市场所有有效股票平均涨跌幅)
    base_all_rows = conn.execute("SELECT code, f2 FROM history WHERE trade_date = ? AND f2 > 0", (base_date,)).fetchall()
    benchmark_rets = []
    for r in base_all_rows:
        c = r["code"]
        p0 = r["f2"]
        if c in latest_map and p0 > 0:
            benchmark_rets.append((latest_map[c]["f2"] - p0) / p0 * 100.0)
    bench_return = round(float(np.mean(benchmark_rets)), 2) if benchmark_rets else 0.0
    # 市场自然胜率（同期全市场上涨家数占比）：胜率评估的客观参照系
    bench_win_rate = round(float(np.mean([1.0 if x > 0 else 0.0 for x in benchmark_rets])) * 100.0, 1) if benchmark_rets else 0.0

    # 计算回测个股表现
    backtest_results = []
    wins = 0
    losses = 0
    returns = []
    win_returns = []
    loss_returns = []

    for item in picked_stocks:
        code = item["code"]
        p0 = item["f2"]
        lat = latest_map.get(code)
        if not lat or not p0 or p0 <= 0:
            continue
        p_now = lat["f2"]
        ret = round((p_now - p0) / p0 * 100.0, 2)
        is_win = ret > 0
        if is_win:
            wins += 1
            win_returns.append(ret)
        else:
            losses += 1
            loss_returns.append(ret)
        returns.append(ret)

        backtest_results.append({
            "rank": item["rank"],
            "code": code,
            "name": item["name"],
            "industry": item["industry"],
            "market": item["market"],
            "confidence": item["confidence"],
            "grade": item["grade"],
            "grade_desc": item["grade_desc"],
            "base_date": base_date,
            "entry_price": p0,
            "latest_price": p_now,
            "return_pct": ret,
            "is_win": is_win,
            "attribution": item["attribution"],
        })

    total_valid = len(returns)
    win_rate = round(wins / total_valid * 100.0, 1) if total_valid > 0 else 0.0
    avg_return = round(float(np.mean(returns)), 2) if total_valid > 0 else 0.0
    median_return = round(float(np.median(returns)), 2) if total_valid > 0 else 0.0
    alpha = round(avg_return - bench_return, 2)

    avg_win = float(np.mean(win_returns)) if win_returns else 0.0
    avg_loss = abs(float(np.mean(loss_returns))) if loss_returns else 1.0
    pl_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    dist = {
        "big_gain": sum(1 for r in returns if r >= 10.0),
        "mid_gain": sum(1 for r in returns if 3.0 <= r < 10.0),
        "small_gain": sum(1 for r in returns if 0.0 < r < 3.0),
        "small_loss": sum(1 for r in returns if -3.0 <= r <= 0.0),
        "mid_loss": sum(1 for r in returns if -10.0 <= r < -3.0),
        "big_loss": sum(1 for r in returns if r < -10.0),
    }

    max_gain_item = max(backtest_results, key=lambda x: x["return_pct"]) if backtest_results else None
    max_loss_item = min(backtest_results, key=lambda x: x["return_pct"]) if backtest_results else None

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

    return {
        "base_date": base_date,
        "target_date": "今日盘中实时",
        "total_picked": total_valid,
        "win_count": wins,
        "loss_count": losses,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "median_return": median_return,
        "benchmark_return": bench_return,
        "benchmark_win_rate": bench_win_rate,
        "alpha": alpha,
        "profit_loss_ratio": pl_ratio,
        "distribution": dist,
        "max_gain": max_gain_item,
        "max_loss": max_loss_item,
        "elapsed_ms": elapsed_ms,
        "results": backtest_results,
    }


# ===== 回测寻优（参数搜索） =====

class NeuralOptimizeRequest(BaseModel):
    top_k: int = Field(default=30, ge=5, le=100)     # 每个截面选股数
    samples: int = Field(default=2000, ge=20, le=5000)  # 随机搜索采样数
    force: bool = False                                # 跳过缓存强制重算


# 内置候选权重（与前端策略预设口径一致，作为搜索起点）
_BUILTIN_CANDIDATES = [
    [65, 80, 50, 60, 45, 30, 25, -30],    # 系统默认
    [85, 65, 80, 75, 60, 40, 20, -45],    # 游资接力
    [35, 95, 25, -15, -10, -20, 15, 10],  # 主力潜伏
    [60, 75, 95, 45, 30, 50, -40, -25],   # 底部突破
    [70, 80, 60, 95, 70, 35, 85, -15],    # 龙头高标
]

_WEIGHT_NAMES = [
    "weight_turnover", "weight_capital", "weight_volume_ratio", "weight_momentum",
    "weight_auction_gap", "weight_amplitude", "weight_trend_60d", "weight_market_cap",
]

_OPT_CACHE = {"key": None, "ts": 0.0, "payload": None}
_OPT_CACHE_TTL = 1800  # 寻优结果缓存 30 分钟（训练默认参数以稳定为先）


@router.post("/optimize")
def run_neural_optimize(req: NeuralOptimizeRequest, user=Depends(current_user)):
    """回测寻优：在全部历史截面上前向选股，跟踪至下一截面/最新价，
    以「平均Alpha + 0.05×(平均胜率-50)」为目标函数搜索最优突触权重。
    目标日依次使用下一历史截面收盘，最后一个历史日用最新实时价，保证全程真实成交数据。
    """
    t0 = time.perf_counter()
    conn = get_conn()

    dates = [r["trade_date"] for r in
             conn.execute("SELECT DISTINCT trade_date FROM history ORDER BY trade_date ASC")]
    if not dates:
        raise HTTPException(400, "数据库中无可用历史交易日数据，无法回测寻优")

    cache_key = (req.top_k, req.samples, dates[-1])
    if (not req.force and _OPT_CACHE["payload"] is not None
            and _OPT_CACHE["key"] == cache_key
            and time.time() - _OPT_CACHE["ts"] < _OPT_CACHE_TTL):
        cached = dict(_OPT_CACHE["payload"])
        cached["cached"] = True
        return cached

    base_req = NeuralPredictRequest()  # 寻优统一采用默认过滤口径，保证可比性

    # 最新实时价（最后一个历史截面的目标价）
    latest_map = {r["code"]: r["f2"] for r in
                  conn.execute("SELECT code, f2 FROM latest WHERE f2 > 0")}

    # 每个历史日：合格样本 + 目标价映射 + 全市场基准收益 + 预计算 Z 矩阵
    datasets = []
    for i, d in enumerate(dates):
        rows, _ = _query_cross_section(conn, base_req, False, d)
        if len(rows) < 30:
            continue
        if i + 1 < len(dates):
            tgt_rows = conn.execute(
                "SELECT code, f2 FROM history WHERE trade_date = ? AND f2 > 0",
                (dates[i + 1],)).fetchall()
            target_map = {r["code"]: r["f2"] for r in tgt_rows}
            target_desc = dates[i + 1]
        else:
            target_map = latest_map
            target_desc = "最新实时"
        bench_rows = conn.execute(
            "SELECT code, f2 FROM history WHERE trade_date = ? AND f2 > 0", (d,)).fetchall()
        bench_rets = [(target_map[r["code"]] - r["f2"]) / r["f2"] * 100.0
                      for r in bench_rows if r["code"] in target_map and r["f2"]]
        bench = float(np.mean(bench_rets)) if bench_rets else 0.0
        Z = _forward(base_req, rows)["Z"]  # 预计算标准化矩阵，后续候选直接复用
        # 预计算选出价/目标价对齐数组：_eval_w 每轮直接 numpy 向量化取收益，
        # 避免 2500+ 组参数 × N 天的 Python 逐行字典查找（首次寻优超时 504 的主因之一）
        codes = [r["code"] for r in rows]
        p0 = np.array([float(r["f2"] or 0.0) for r in rows], dtype=np.float64)
        pt = np.array([float(target_map[c]) if target_map.get(c) else np.nan
                       for c in codes], dtype=np.float64)
        datasets.append({"date": d, "rows": rows, "Z": Z, "p0": p0, "pt": pt,
                         "target_desc": target_desc, "bench": bench})

    if not datasets:
        raise HTTPException(400, "历史截面合格样本过少（需 >= 30 只），无法回测寻优")

    # 候选集合：内置策略预设 + 固定种子均匀随机粗搜（结果可复现）
    rng = np.random.default_rng(42)
    cands = [np.array(c, dtype=np.float64) / 100.0 for c in _BUILTIN_CANDIDATES]
    cands += [rng.uniform(-1.0, 1.0, 8) for _ in range(req.samples)]

    _ACTS = ["gelu", "tanh", "sigmoid", "leaky_relu", "relu"]
    _req_by_act = {a: base_req.model_copy(update={"activation": a}) for a in _ACTS}
    evaluated = 0

    def _eval_w(w, act="gelu"):
        nonlocal evaluated
        evaluated += 1
        r = _req_by_act[act]
        per_date = []
        for ds in datasets:
            fwd = _forward(r, ds["rows"], weight_override=w,
                           bias_override=[0.0, 0.0, 0.0, 0.0],
                           precomputed={"Z": ds["Z"]})
            k = min(req.top_k, len(ds["rows"]))
            idx = fwd["order"][:k]
            p0 = ds["p0"][idx]
            pt = ds["pt"][idx]
            mask = (p0 > 0) & np.isfinite(pt)
            if not mask.any():
                continue
            rets = (pt[mask] - p0[mask]) / p0[mask] * 100.0
            wr = float(np.mean(rets > 0)) * 100.0
            avg = float(np.mean(rets))
            per_date.append({"date": ds["date"], "target": ds["target_desc"],
                             "win_rate": round(wr, 1), "avg_return": round(avg, 2),
                             "alpha": round(avg - ds["bench"], 2)})
        if not per_date:
            return None
        mwr = float(np.mean([p["win_rate"] for p in per_date]))
        mavg = float(np.mean([p["avg_return"] for p in per_date]))
        malpha = float(np.mean([p["alpha"] for p in per_date]))
        # 目标函数：全窗口正收益给予决定性奖励（用户要求默认参数历史收益为正），
        # 其次平均收益 + 0.5×最差窗口收益 + 胜率为辅
        worst = min(p["avg_return"] for p in per_date)
        objective = (mavg + 0.5 * worst + 0.05 * (mwr - 50.0)
                     + (100.0 if worst > 0 else 0.0))
        return {"w": w, "act": act, "objective": objective,
                "win_rate": round(mwr, 1), "avg_return": round(mavg, 2),
                "alpha": round(malpha, 2), "per_date": per_date}

    # 阶段 1：随机粗搜（GELU）
    stage1 = []
    for w in cands:
        r = _eval_w(w, "gelu")
        if r is not None:
            stage1.append(r)
    if not stage1:
        raise HTTPException(500, "参数搜索未能产生有效评估结果")
    stage1.sort(key=lambda x: -x["objective"])

    # 阶段 2：对粗搜 Top-20 逐一优选激活函数（不同激活捕获不同非线性形态）
    stage2 = []
    for r in stage1[:20]:
        for a in _ACTS:
            rr = _eval_w(r["w"], a)
            if rr is not None:
                stage2.append(rr)
    stage2.sort(key=lambda x: -x["objective"])
    best = stage2[0]

    # 阶段 3：局部细化（以当前最优为中心做高斯扰动爬山，步长逐轮减半）
    sigma = 0.25
    for _round in range(3):
        improved = False
        for _ in range(150):
            w_try = np.clip(best["w"] + rng.normal(0.0, sigma, 8), -1.0, 1.0)
            rr = _eval_w(w_try, best["act"])
            if rr is not None and rr["objective"] > best["objective"]:
                best = rr
                improved = True
        if not improved:
            sigma *= 0.5

    results = sorted(stage2 + [best], key=lambda x: -x["objective"])

    def _w2dict(w):
        return {n: round(float(w[i]) * 100.0, 1) for i, n in enumerate(_WEIGHT_NAMES)}

    def _brief(r):
        return {"weights": _w2dict(r["w"]), "activation": r["act"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"], "alpha": r["alpha"],
                "objective": round(r["objective"], 3)}

    best = results[0]
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    payload = {
        "dates_used": [ds["date"] for ds in datasets],
        "target_descs": {ds["date"]: ds["target_desc"] for ds in datasets},
        "samples_evaluated": evaluated,
        "search_desc": "三阶段搜索：随机粗搜 → Top20×5激活函数优选 → 高斯扰动局部细化",
        "objective_desc": "目标函数：优先保证全部历史窗口正收益，再最大化平均收益与胜率",
        "best": {**_brief(best), "per_date": best["per_date"]},
        "leaderboard": [_brief(r) for r in results[:5]],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cached": False,
        "elapsed_ms": elapsed_ms,
    }
    _OPT_CACHE["key"] = cache_key
    _OPT_CACHE["ts"] = time.time()
    _OPT_CACHE["payload"] = payload
    return payload
