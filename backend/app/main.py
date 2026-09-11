"""FastAPI 入口：挂路由、建库、启动调度；本地开发时顺便托管前端静态目录。"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db, scheduler
from .routes import (admin_routes, auth_routes, log_routes, quote_routes,
                     radar_routes, watchlist_routes)
from .security import hash_password

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.seed_admin(hash_password)
    db.seed_root(hash_password)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Turnover Screener API", lifespan=lifespan)
# 直连 8000 端口(本地开发 dev:local)时也压缩 JSON;生产 nginx 已有一层 gzip
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(quote_routes.router)
app.include_router(watchlist_routes.router)
app.include_router(radar_routes.router)
app.include_router(log_routes.router)

# 本地开发：uvicorn 直接托管前端（生产由 nginx 托管 / 并反代 /api）
if os.path.isdir(config.FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True),
              name="frontend")
