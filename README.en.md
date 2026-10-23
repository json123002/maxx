# maxx · Turnover Screener

A self-hosted Chinese A-share market-data screening and visualization application built with FastAPI, SQLite, and Vue 3.

[中文文档](README.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Roadmap](ROADMAP.md)

## Features

- Scheduled market snapshots, turnover filters, watchlists, and historical screening results.
- Stock detail views with explainable daily candlestick phase annotations.
- Limit-up radar and ladder views.
- Login, revocable sessions, administrator user management, and per-user data-source settings.
- Data-source fallback and stale-data indicators when collection fails.

## Local development

Requirements: Python 3.11+, Node.js 22.13+, and pnpm. Use pnpm for frontend dependencies; retain the existing lockfile.

From `backend/`:

```sh
pip install -r requirements.txt
python -m pytest tests/ -q
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal, from `web/`:

```sh
pnpm install
pnpm dev
```

Run frontend checks from `web/`:

```sh
pnpm test
pnpm build
```

The development frontend proxies `/api` to the local backend. The frontend build is written to `frontend/`; do not edit generated output manually. See the Chinese README for deployment details.

Set the `TS_ADMIN_PASSWORD` environment variable before first startup. New installations have no default password; existing account passwords are unchanged. Use a strong unique password. Never commit credentials, databases, or production logs.

## Data and interpretation

Market data is obtained from external providers. Availability, accuracy, access rights, and redistribution conditions are governed by those providers. The software license does not grant rights to third-party market data or services.

Candlestick phases are explainable heuristics, not calibrated predictions. Historical phase starting points are not signals available at that historical moment. Unclosed candles and adjusted data can change annotations. The application supports data exploration and does not constitute investment advice.

## Project status and maintenance

maxx is an early-stage project. It does not claim broad adoption or verified download figures. Public commits, tests, and workflow definitions provide evidence of development; a workflow definition alone does not prove a successful run.

Changes must go through pull requests and the checks described in CONTRIBUTING.md. Security concerns should follow SECURITY.md rather than a public issue.

## License

Project-owned code is licensed under the [MIT License](LICENSE). Dependencies and third-party materials retain their respective licenses and terms.
