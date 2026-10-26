import re

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import funds
from ..db import get_conn
from ..security import current_user

router = APIRouter(prefix="/api/desk", tags=["funds"])


@router.get("/funds/{code}")
def stock_funds(code: str, minimum: float = Query(default=0, ge=0, le=1e12),
                side: str = Query(default="all", pattern="^(all|buy|sell|neutral)$"),
                page: int = Query(default=1, ge=1, le=100000),
                page_size: int = Query(default=100, ge=1, le=200),
                all_rows: bool = False, user=Depends(current_user)):
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400, "股票代码须为6位数字")
    # 资金接口仅使用本人私有配置，绝不将他人的证书或额度隐式用于大数据量查询。
    source = get_conn().execute(
        "SELECT id,user_id,licence FROM quote_source WHERE user_id=?"
        " AND provider='mairui' AND enabled=1 ORDER BY id LIMIT 1", (user["id"],)).fetchone()
    if not source:
        raise HTTPException(400, "请先在行情设置中启用自己的麦蕊智数接口")
    if code.startswith(("4", "8", "9")):
        raise HTTPException(400, "当前盘口资金接口仅支持沪深股票，北交所尚未接入")
    try:
        data = funds.get_dataset(code, dict(source))
        return funds.select_trades(data, minimum, side, page, page_size, all_rows)
    except Exception:
        raise HTTPException(502, "资金数据请求失败，请检查接口权限或稍后重试") from None
