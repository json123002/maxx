"""Provider credentials must never be returned in public error responses."""

from fastapi import HTTPException
from app.routes import settings_routes as sr


def test_public_provider_failure_does_not_expose_credentials(monkeypatch):
    secret = "TEST_PROVIDER_CREDENTIAL_123"
    class Conn:
        def execute(self, *args):
            self.own = "user_id = ?" in args[0]
            return self
        def fetchone(self):
            return None if self.own else {"provider": "mairui", "licence": secret,
                                         "name": "shared", "user_id": 2}
    monkeypatch.setattr(sr, "get_conn", lambda: Conn())
    def fail(*args, **kwargs):
        raise RuntimeError("request failed https://provider/" + secret)
    monkeypatch.setattr(sr._mr, "get", fail)
    try:
        sr.quote_intraday("000001", user={"id": 1})
    except HTTPException as exc:
        assert exc.status_code == 502
        assert secret not in exc.detail
    else:
        raise AssertionError("expected a sanitized upstream failure")


def test_new_install_requires_admin_password(monkeypatch):
    import pytest
    from app import config, db
    class EmptyConn:
        def execute(self, *args):
            return self
        def fetchone(self):
            return {"c": 0}
    monkeypatch.setattr(db, "get_conn", lambda: EmptyConn())
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    with pytest.raises(RuntimeError, match="TS_ADMIN_PASSWORD"):
        db.seed_admin(lambda value: value)
