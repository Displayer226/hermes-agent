"""Transient token endpoint failures retain safe retry guidance on native refresh."""
import httpx
import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_cli.dashboard_auth import clear_providers, register_provider
from hermes_cli.dashboard_auth.routes import router
from hermes_cli.dashboard_auth.base import ProviderError
from plugins.dashboard_auth import _shared
from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider


@pytest.mark.parametrize(("status", "header", "expected"), [
    (429, "12", "12"), (503, "7200", "7200"), (503, "Wed, 21 Oct 2015 07:30:00 GMT", "120"),
    (429, "garbage", "60"), (503, "NaN", "60"), (503, "inf", "60"),
    (503, None, "60"), (503, "0", "1"), (503, "0.1", "1"),
    (503, "-2", "1"), (503, "Wed, 21 Oct 2015 07:27:00 GMT", "1"),
])
def test_native_refresh_retry_after(monkeypatch, status, header, expected):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2015, 10, 21, 7, 28, tzinfo=timezone.utc)

    monkeypatch.setattr(_shared, "datetime", Clock)
    class Provider(StubAuthProvider):
        name = "retry-test"

        def refresh_session(self, *, refresh_token):
            _shared.exchange_token("https://idp.invalid/token", {}, bad_request_exc=ValueError,
                                   idp="test", endpoint="token", token_key="access_token", missing_msg="missing")

    monkeypatch.setattr(_shared, "_request_limited_response", lambda *a, **kw: httpx.Response(
        status, headers={"Retry-After": header} if header is not None else {}, text="sensitive-provider-detail"))
    clear_providers()
    register_provider(Provider())
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as client:
            response = client.post("/auth/native/refresh", json={"refresh_token": "synthetic", "provider": "retry-test"})
        assert response.status_code == 503
        assert response.headers.get("Retry-After") == expected
        assert "sensitive-provider-detail" not in response.text
        assert "retry-test" not in response.text
    finally:
        clear_providers()


@pytest.mark.parametrize("hint", ["", "first", "second", "stale"])
@pytest.mark.parametrize("first_retry", [None, 12])
def test_native_refresh_uses_longest_provider_retry(hint, first_retry):
    class Provider(StubAuthProvider):
        def __init__(self, name, retry):
            super().__init__()
            self.name, self.retry = name, retry

        def refresh_session(self, *, refresh_token):
            raise ProviderError("private", retry_after=self.retry)

    clear_providers()
    register_provider(Provider("first", first_retry))
    register_provider(Provider("second", 7200))
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as client:
            response = client.post("/auth/native/refresh", json={"refresh_token": "synthetic", "provider": hint})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "7200"
        assert "private" not in response.text
    finally:
        clear_providers()
