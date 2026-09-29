"""操作日志：前端行为埋点上报（所有登录用户） + 日志查询（仅隐藏 root）。

/api/logs 对非 root 一律返回 404——不暴露该功能的存在。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import client_ip, enrich_regions, log_op, user_agent
from ..security import current_user, require_root

router = APIRouter(tags=["logs"])

# 前端可上报的动作白名单（防刷库）；登录/自选/管理员操作等由服务端自行记录
TRACK_ACTIONS = {"screener_run", "stock_view", "analysis_view", "history_view",
                 "radar_view", "ladder_view", "flow_view", "sector_view", "desk_view", "f10_view",
                 "page_view", "setting_change", "setting_modal_open",
                 "neural_stock_analysis", "neural_inference_run", "neural_backtest_run"}


class TrackIn(BaseModel):
    action: str = Field(max_length=32)
    detail: str = Field(default="", max_length=300)


@router.post("/api/track")
def track(body: TrackIn, request: Request, user=Depends(current_user)):
    """前端行为埋点（条件筛选/看个股/开分析弹窗），fire-and-forget。"""
    if body.action not in TRACK_ACTIONS:
        raise HTTPException(400, "unknown action")
    log_op(user, body.action, body.detail,
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.get("/api/logs")
def list_logs(username: str = Query(default="", max_length=32),
              action: str = Query(default="", max_length=32),
              kw: str = Query(default="", max_length=64),
              page: int = Query(default=1, ge=1),
              size: int = Query(default=20, ge=1, le=100),
              user=Depends(require_root)):
    """操作日志查询（仅隐藏 root）。按时间倒序，支持用户/动作/关键词过滤。"""
    where, params = [], []
    if username.strip():
        where.append("username = ?")
        params.append(username.strip())
    if action.strip():
        where.append("action = ?")
        params.append(action.strip())
    if kw.strip():
        where.append("(detail LIKE ? OR username LIKE ?)")
        like = "%" + kw.strip() + "%"
        params += [like, like]
    w = (" WHERE " + " AND ".join(where)) if where else ""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM op_logs" + w, params).fetchone()["c"]
    rows = conn.execute(
        "SELECT id, ts, user_id, username, action, detail, ip, ua"
        " FROM op_logs" + w +
        " ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, size, (page - 1) * size)).fetchall()
    actions = [r["action"] for r in conn.execute(
        "SELECT DISTINCT action FROM op_logs ORDER BY action").fetchall()]
    rows = [dict(r) for r in rows]
    enrich_regions(rows)
    return {"rows": rows, "total": total, "actions": actions}
