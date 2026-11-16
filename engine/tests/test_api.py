import re

import pytest

from app.market import history
from tests.conftest import fake_fetch


def upload(client, data):
    return client.post("/api/ledger/import", files={"file": ("tradebook.csv", data, "text/csv")})


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_import_is_idempotent(client, upstox_csv):
    first = upload(client, upstox_csv).json()
    assert (first["imported"], first["duplicates"], len(first["skipped"])) == (3, 0, 1)
    second = upload(client, upstox_csv).json()
    assert (second["imported"], second["duplicates"]) == (0, 3)
    assert len(client.get("/api/ledger/trades").json()) == 3


def test_holdings_without_prices_still_lists_positions(client, upstox_csv):
    upload(client, upstox_csv)
    data = client.get("/api/portfolio/holdings").json()
    rel = next(h for h in data["holdings"] if h["symbol"] == "RELIANCE.NS")
    assert rel["quantity"] == 6 and rel["avg_cost"] == 1250.0 and rel["last"] is None
    assert data["realized_pnl"] == pytest.approx(4 * 50.0)


def test_metrics_end_to_end_and_recalculation(client, upstox_csv, monkeypatch):
    monkeypatch.setattr(history, "fetch", fake_fetch)
    upload(client, upstox_csv)

    base = client.get("/api/metrics").json()
    m = base["metrics"]
    assert base["observations"] == 252 and base["warnings"] == []
    assert all(m[k] is not None for k in ("beta", "jensens_alpha_annualized", "sharpe",
                                          "sortino", "max_drawdown", "var"))
    assert 0.8 < m["beta"] < 1.6  # assets are built as 1.2x market plus noise
    assert sum(h["weight"] for h in base["holdings"]) == pytest.approx(1.0)
    assert sum(h["component_var"] for h in base["holdings"]) == pytest.approx(m["var"])

    # 99% VaR = 95% VaR * z99/z95
    v99 = client.get("/api/metrics", params={"confidence": 0.99}).json()["metrics"]["var"]
    assert v99 == pytest.approx(m["var"] * 2.3263479 / 1.6448536, rel=1e-6)

    # benchmark swap persists through settings and changes the params used
    assert client.put("/api/settings", json={"benchmark": "^BSESN"}).json()["benchmark"] == "^BSESN"
    assert client.get("/api/metrics").json()["params"]["benchmark"] == "^BSESN"
    assert client.put("/api/settings", json={"benchmark": "^GSPC"}).status_code == 400
    assert client.get("/api/metrics", params={"confidence": 1.5}).status_code == 400


def test_manual_bonus_adjusts_position_and_blocks_double_entry(client, upstox_csv):
    upload(client, upstox_csv)
    body = {"symbol": "TCS.NS", "ex_date": "2025-06-01", "kind": "bonus", "value": 2.0}
    assert client.post("/api/corporate-actions", json=body).status_code == 201
    assert client.post("/api/corporate-actions", json={**body, "kind": "split"}).status_code == 409
    tcs = next(h for h in client.get("/api/portfolio/holdings").json()["holdings"]
               if h["symbol"] == "TCS.NS")
    assert tcs["quantity"] == 10 and tcs["avg_cost"] == 2000.0


def test_token_is_enforced(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(db_url=f"sqlite:///{(tmp_path / 't.sqlite3').as_posix()}", token="secret")
    with TestClient(app) as c:
        assert c.get("/api/settings").status_code == 401
        assert c.get("/api/settings", headers={"x-qt-token": "secret"}).status_code == 200


def test_no_execution_surface(client):
    """Zero-execution guarantee: no route may look like order routing."""
    banned = re.compile(r"order|execut|place|buy|sell|webhook", re.I)
    paths = list(client.get("/openapi.json").json()["paths"])
    assert "/api/metrics" in paths
    assert not [p for p in paths if banned.search(p)]


def test_search_finds_stocks_by_name_and_ticker(client, upstox_csv, monkeypatch):
    from app.market import search

    calls = []

    def fake_lookup(query, limit):
        calls.append(query)
        return [
            {"symbol": "TATAMOTORS.NS", "longname": "Tata Motors Limited", "quoteType": "EQUITY"},
            {"symbol": "TATAMOTORS.BO", "shortname": "TATA MOTORS LTD", "quoteType": "EQUITY"},
            {"symbol": "TTM", "longname": "Tata Motors ADR", "quoteType": "EQUITY"},
            {"symbol": "TATAGOLD.NS", "longname": "Tata Gold ETF", "quoteType": "ETF"},
        ]

    search._CACHE.clear()
    monkeypatch.setattr(search, "yahoo_lookup", fake_lookup)
    upload(client, upstox_csv)

    data = client.get("/api/search", params={"q": "tata motors"}).json()
    assert data["online"] is True
    assert [r["symbol"] for r in data["results"]] == ["TATAMOTORS.NS", "TATAMOTORS.BO"]
    assert data["results"][0] == {"symbol": "TATAMOTORS.NS", "name": "Tata Motors Limited",
                                  "exchange": "NSE", "held": False}

    client.get("/api/search", params={"q": "Tata  Motors"})
    assert calls == ["tata motors"]  # repeated query is served from the cache

    assert client.get("/api/search", params={"q": "  "}).json()["results"] == []


def test_search_works_offline_from_the_ledger(client, upstox_csv, monkeypatch):
    from app.market import search

    def offline(query, limit):
        raise ConnectionError("no network")

    search._CACHE.clear()
    monkeypatch.setattr(search, "yahoo_lookup", offline)
    upload(client, upstox_csv)

    data = client.get("/api/search", params={"q": "relia"}).json()
    assert data["online"] is False
    assert data["results"][0]["symbol"] == "RELIANCE.NS" and data["results"][0]["held"] is True
