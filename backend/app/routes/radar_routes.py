"""涨停雷达：一进二候选筛选（服务端粗筛层）。

口径：昨日（history 最新交易日）首板涨停 ∩ 今日（latest 快照）竞价/量能/资金过滤。
基因与前高基于个股日K缓存（kline 模块，前复权 250 日）：前高取区间最高价，
基因含 A杀/最高连板/炸板（盘中触及涨停但收盘未封）；日K不可用时退化到
history 收盘序列（无炸板维度、窗口受落库天数限制）。
竞价金额占比、上板时间、分时结构需要盘中精细数据，由个股弹窗终检，不在此层。
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends

from .. import kline
from ..db import get_conn
from ..security import current_user

router = APIRouter(prefix="/api/radar", tags=["radar"])

# 维度阈值（skill「一进二」量化口径；✅区间外再设⚠️缓冲带，其余 ❌）
OPEN_GOOD = (3.0, 6.0)       # 竞价涨幅%：高开 3-6 最完美
OPEN_WARN = (2.0, 8.0)
TOV_GOOD = (10.0, 25.0)      # 名义换手%（实际换手缺自由流通股本，口径偏宽已标注）
TOV_WARN = (6.0, 30.0)
AMT_GOOD = (0.5, 1.5)        # 今日成交额 / 昨日成交额
AMT_WARN = (0.3, 2.5)
MAIN_NET_GOOD_YI = 1.0       # 主力净流入 > 1 亿
DIST_BREAK = 0.0             # 距前高：>=0 视为强势突破（涨停价越过高点）
DIST_ROOM = -20.0            # <= -20% 上方空间足
DIST_DANGER = (-12.0, -4.0)  # 距前高 8% 左右的阻力区，坚决不碰
GENE_DAYS = 250              # 基因统计窗口（约一年交易日）
PREV_HIGH_DAYS = 120         # 前高参考窗口（日K最高价口径）
ZHABAN_BAD = 3               # 一年内炸板 >=3 次 = 基因不合格（"一直炸板"）
KLINE_MIN_BARS = 20          # 日K少于此数视为不可用，退化 history 口径
KLINE_WORKERS = 8            # 候选股日K并发预取线程数

# 各市场涨跌停幅度阈值%（由日K涨跌幅判定涨跌停，略留容差）；
# 无需 5% 档：候选 SQL 已排除 ST（name NOT LIKE '%ST%'），进不来这层
LIMIT_PCT = {"沪主板": 9.8, "深主板": 9.8, "创业板": 19.5,
             "科创板": 19.5, "北交所": 29.5}

# 维度口径说明（随响应下发,前端「判定理由」直接引用,避免前后端阈值漂移）
RULES = {
    "open": "高开 3~6% 最佳（2~8% 可观察）",
    "tov": "名义换手 10~25%（6~30% 可观察；实际换手口径偏宽）",
    "amt": "今日成交额/昨日 0.5~1.5（0.3~2.5 可观察）",
    "main": "主力净流入 > 1 亿",
    "dist": "涨停价突破前高或空间 >20%；距前高 8% 左右坚决不碰（前高=120 日日K最高价）",
    "gene": "近一年无 A杀、炸板 <3 次，最高连板 <3",
}


def _grade(v, good, warn):
    """数值 → good/warn/bad；缺数据 None → warn（交由人工确认）。"""
    if v is None:
        return "warn"
    if good[0] <= v <= good[1]:
        return "good"
    if warn[0] <= v <= warn[1]:
        return "warn"
    return "bad"


def _gene(flags_desc):
    """单票涨停/跌停标记序列（按交易日升序）→ (A杀次数, 最高连板数)。

    A杀：一次 >=2 连板结束后 3 个交易日内出现 >=2 连续跌停。
    """
    max_streak = 0
    kill_a = 0
    n = len(flags_desc)
    i = 0
    while i < n:
        if flags_desc[i][0]:
            j = i
            while j < n and flags_desc[j][0]:
                j += 1
            run = j - i
            max_streak = max(max_streak, run)
            if run >= 2:  # 连板结束后看 3 日内是否连续跌停（A杀）
                downs = 0
                for k in range(j, min(j + 3, n)):
                    if flags_desc[k][1]:
                        downs += 1
                        if downs >= 2:
                            kill_a += 1
                            break
                    else:
                        downs = 0
            i = j
        else:
            i += 1
    return kill_a, max_streak


def _gene_bars(bars, th):
    """日K序列（升序）→ (A杀次数, 最高连板, 炸板次数)。

    涨跌停由日涨跌幅判定（主板 9.8 / 创业科创 19.5 / 北交所 29.5）；
    炸板 = 盘中最高价触及涨停但收盘未封（上影线基因）：
    最高价涨幅用前复权价自算（与收盘同尺度），收盘涨跌幅用官方字段。
    """
    flags = []
    zhaban = 0
    prev_close = None
    for b in bars:
        pct = b["pct"]
        up = pct is not None and pct >= th
        down = pct is not None and pct <= -th
        if prev_close and b["high"] and pct is not None and not up:
            high_pct = (b["high"] / prev_close - 1) * 100
            if high_pct >= th - 0.3 and pct < th - 1.0:
                zhaban += 1
        flags.append((up, down))
        prev_close = b["close"] or prev_close
    kill_a, max_streak = _gene(flags)
    return kill_a, max_streak, zhaban


def _grade_dist(dist):
    """距前高：突破(>=0)或空间足(<=-20%) ✅；阻力区(-12~-4%) ❌；其余 ⚠️。"""
    if dist is None:
        return "warn"
    if dist >= DIST_BREAK or dist <= DIST_ROOM:
        return "good"
    if DIST_DANGER[0] <= dist <= DIST_DANGER[1]:
        return "bad"
    return "warn"


def _prev_close(hd, t0):
    """快照缺昨收(f18)时，用昨日历史收盘价兜底。"""
    for r in hd:
        if r["trade_date"] == t0:
            return r["f2"]
    return None


@router.get("/1to2")
def radar_1to2(user=Depends(current_user)):
    """一进二候选池：昨日首板 ∩ 今日竞价/量能/资金/空间粗筛。"""
    conn = get_conn()
    dates = [r["trade_date"] for r in conn.execute(
        "SELECT DISTINCT trade_date FROM history ORDER BY trade_date DESC LIMIT 2"
    ).fetchall()]
    if len(dates) < 2:
        return {"date": dates[0] if dates else "", "rows": [], "rules": RULES,
                "note": "历史数据不足两天，每交易日 15:06 收盘落库后再看"}
    t0, t1 = dates  # t0=昨日（首板日），t1=前日
    # t0 == 今天 = 收盘落库后的复盘视角:竞价/额比衡量的是"次日早晨",
    # 复盘时它们是首板当天已发生的旧值,降级为待确认、不参与否决;
    # 下个交易日早盘快照刷新后自动恢复实盘口径
    review = datetime.now().date().isoformat() == t0

    yd = conn.execute(
        "SELECT h.code, h.name, h.industry, h.market, h.f6 AS y_amt"
        " FROM history h"
        " WHERE h.trade_date = ? AND h.limit_up = 1 AND h.name NOT LIKE '%ST%'"
        " AND NOT EXISTS(SELECT 1 FROM history p"
        "               WHERE p.trade_date = ? AND p.code = h.code"
        "               AND p.limit_up = 1)",
        (t0, t1),
    ).fetchall()
    if not yd:
        return {"date": t0, "rows": [], "rules": RULES,
                "note": t0 + " 无首板涨停（非 ST）"}

    codes = [r["code"] for r in yd]
    marks = ",".join("?" * len(codes))
    today = {r["code"]: r for r in conn.execute(
        "SELECT * FROM latest WHERE code IN (" + marks + ")", codes).fetchall()}

    # 候选股日K并发预取（缓存命中时只是本地查询，首次约每票一次 HTTP）
    bars_map = {}
    with ThreadPoolExecutor(max_workers=KLINE_WORKERS) as ex:
        for code, bars in zip(codes, ex.map(
                lambda c: kline.get_bars(c, GENE_DAYS), codes)):
            bars_map[code] = bars

    # 退化路径用：history 里的收盘/涨跌停序列（无日K时兜底）
    hist = defaultdict(list)
    for r in conn.execute(
            "SELECT code, trade_date, f2, limit_up, limit_down FROM history"
            " WHERE code IN (" + marks + ") AND trade_date <= ?"
            " ORDER BY code, trade_date DESC",
            (*codes, t0)).fetchall():
        if len(hist[r["code"]]) < GENE_DAYS:
            hist[r["code"]].append(r)

    rows = []
    for y in yd:
        code = y["code"]
        t = today.get(code)
        if not t or t["f2"] is None:
            continue  # 今日停牌/无快照，无法评估
        hd = hist.get(code, [])
        bars = [b for b in bars_map.get(code) or [] if b["date"] <= t0]
        if len(bars) >= KLINE_MIN_BARS:
            # 日K口径：前高 = 区间最高价（前复权，与快照价可比）；基因含炸板
            pre = [b for b in bars if b["date"] < t0][-PREV_HIGH_DAYS:]
            prev_high = max((b["high"] for b in pre if b["high"]), default=None)
            th = LIMIT_PCT.get(t["market"] or y["market"], 9.8)
            kill_a, max_streak, zhaban = _gene_bars(bars, th)
        else:
            # 退化口径：前高 = history 区间收盘最高；基因无炸板维度
            prev = [r["f2"] for r in hd if r["trade_date"] < t0
                    and r["f2"]][:PREV_HIGH_DAYS]
            prev_high = max(prev) if prev else None
            kill_a, max_streak = _gene(
                [(r["limit_up"], r["limit_down"]) for r in reversed(hd)])
            zhaban = None

        f18 = t["f18"] or _prev_close(hd, t0)
        open_pct = ((t["f17"] - f18) / f18 * 100
                    if t["f17"] and f18 else None)
        amt_ratio = (t["f6"] / y["y_amt"] if t["f6"] and y["y_amt"] else None)
        main_net_yi = (t["f62"] / 1e8 if t["f62"] is not None else None)
        ref = t["f350"] or t["f2"]  # 距前高以今日涨停价衡量（打板视角）
        dist = ((ref - prev_high) / prev_high * 100
                if ref and prev_high else None)

        dims = {
            "open": ("warn" if review else _grade(open_pct, OPEN_GOOD, OPEN_WARN)),
            "tov": _grade(t["f8"], TOV_GOOD, TOV_WARN),
            "amt": ("warn" if review else _grade(amt_ratio, AMT_GOOD, AMT_WARN)),
            "main": ("warn" if main_net_yi is None else
                     "good" if main_net_yi > MAIN_NET_GOOD_YI else
                     "warn" if main_net_yi >= 0 else "bad"),
            "dist": _grade_dist(dist),
            "gene": ("bad" if kill_a > 0 or (zhaban or 0) >= ZHABAN_BAD else
                     "warn" if max_streak >= 3 or zhaban else "good"),
        }
        verdict = ("放弃" if "bad" in dims.values() else
                   "观察" if "warn" in dims.values() else "候选")
        rows.append({
            "f12": code, "f14": t["name"] or y["name"],
            "f100": t["industry"] or y["industry"], "market": t["market"],
            "f2": t["f2"], "f3": t["f3"], "limit_up": t["limit_up"],
            "free_cap_yi": round(t["f21"] / 1e8, 1) if t["f21"] else None,
            "open_pct": round(open_pct, 2) if open_pct is not None else None,
            "tov": t["f8"],
            "amt_ratio": round(amt_ratio, 2) if amt_ratio is not None else None,
            "main_net_yi": (round(main_net_yi, 2)
                            if main_net_yi is not None else None),
            "prev_high": prev_high,
            "dist_high": round(dist, 1) if dist is not None else None,
            "kill_a": kill_a, "max_streak": max_streak, "zhaban": zhaban,
            "dims": dims, "verdict": verdict,
        })
    rank = {"候选": 0, "观察": 1, "放弃": 2}
    rows.sort(key=lambda r: (rank[r["verdict"]],
                             -(r["main_net_yi"] or -999)))
    stat = {v: sum(1 for r in rows if r["verdict"] == v) for v in rank}
    return {"date": t0, "rows": rows, "stat": stat, "rules": RULES,
            "review": review}
