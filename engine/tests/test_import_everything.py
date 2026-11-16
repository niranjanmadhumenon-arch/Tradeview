"""One-file import of everything: trades, mutual funds, commodities, bonds and wealth. No network."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.ledger import workbook
from app.main import create_app
from app.market import history
from tests.test_tracking import market


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "fetch", market)
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'w.sqlite3').as_posix()}", token="")
    with TestClient(app) as c:
        yield c


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        ws = book.create_sheet(title)
        for r in rows:
            ws.append(r)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def upload(client, content: bytes, name="holdings.xlsx", path="/api/import/everything"):
    return client.post(path, files={"file": (name, content)})


def test_the_template_imports_everything_in_one_go(client):
    content = client.get("/api/import/everything/template").content
    preview = upload(client, content, path="/api/import/everything/preview").json()
    kinds = {s["sheet"]: s["kind"] for s in preview["sheets"]}
    assert kinds == {"Read me": "skip", "Stocks & funds": "trades", "Bonds": "bonds", "Wealth": "wealth"}
    assert all(not s.get("missing") for s in preview["sheets"])
    stocks = next(s for s in preview["sheets"] if s["sheet"] == "Stocks & funds")
    assert stocks["default_exchange"] == ""                 # "funds" in the name must not make stocks funds

    r = upload(client, content).json()
    assert r["skipped"] == []
    assert r["totals"] == {"trades": 5, "trade_duplicates": 0, "bonds": 2, "wealth": 7}
    symbols = {t["symbol"] for t in client.get("/api/ledger/trades").json()}
    assert symbols == {"INFY.NS", "AAPL", "MF:122639", "CMDTY:GOLD", "BOND:GOI2033"}
    bonds = {b["symbol"]: b for b in client.get("/api/bonds").json()}
    assert bonds["BOND:GOI2033"]["coupon_rate"] == 7.18 and bonds["BOND:GOI2033"]["frequency"] == 2
    assert bonds["BOND:NHAI2031"]["frequency"] == 1 and bonds["BOND:NHAI2031"]["price"] == 1012
    items = {i["kind"]: i for i in client.get("/api/wealth").json()["items"]}
    assert set(items) == {"fixed_deposit", "ppf", "epf", "nps", "cash", "life_insurance", "term_insurance"}
    assert items["fixed_deposit"]["start_date"] == "2024-04-01" and items["fixed_deposit"]["rate"] == 7.25
    assert items["term_insurance"]["cover"] == 10_000_000 and items["term_insurance"]["amount"] == 0
    assert items["ppf"]["monthly_contribution"] == 12500

    # Importing the same file again adds nothing.
    again = upload(client, content).json()
    assert again["totals"]["trades"] == 0 and again["totals"]["trade_duplicates"] == 5
    assert again["totals"]["bonds"] == 0 and again["totals"]["wealth"] == 0
    assert len(client.get("/api/wealth").json()["items"]) == 7


def test_loose_headings_sheet_names_and_updates(client):
    content = xlsx({
        "My gold": [["Date", "Item", "Qty", "Rate", "Buy/Sell"],
                    ["2025-01-10", "Gold", 10, 8000, "B"], ["2025-01-11", "Unobtainium", 1, 5, "B"]],
        "Mutual funds": [["Txn Date", "Scheme Code", "Units", "NAV", "Type"], ["2025-02-01", "122639", 50.5, 80, "BUY"]],
        "Deposits & insurance": [["Category", "Bank", "Balance", "Interest %", "Opened", "Sum assured"],
                                 ["Fixed Deposit", "SBI", "2 lakh", "7%", "01/04/2024", ""],
                                 ["SBI FD", "SBI", "50,000", "", "", ""],                 # FD without a start date
                                 ["LIC Jeevan Anand", "LIC", "1.5 lakh", "", "", "10,00,000"],
                                 ["Crypto", "", "1000", "", "", ""]],
    })
    pv = upload(client, content, path="/api/import/everything/preview").json()["sheets"]
    assert [s["kind"] for s in pv] == ["trades", "trades", "wealth"]
    r = upload(client, content).json()
    assert r["totals"]["trades"] == 2 and r["totals"]["wealth"] == 2
    joined = " | ".join(r["skipped"])
    assert "Unobtainium" in joined and "needs its start date" in joined and "unknown type 'Crypto'" in joined
    held = {t["symbol"]: t for t in client.get("/api/ledger/trades").json()}
    assert held["CMDTY:GOLD"]["quantity"] == 10 and held["MF:122639"]["quantity"] == 50.5
    items = client.get("/api/wealth").json()["items"]
    fd = next(i for i in items if i["kind"] == "fixed_deposit")
    assert fd["amount"] == 200_000 and fd["rate"] == 7 and fd["institution"] == "SBI"
    lic = next(i for i in items if i["kind"] == "life_insurance")
    assert lic["cover"] == 1_000_000 and lic["amount"] == 150_000

    # A corrected balance in the file updates the item instead of adding a second one.
    fixed = xlsx({"Wealth": [["Type", "Institution", "Amount", "Rate", "Start date"],
                             ["Fixed Deposit", "SBI", 250000, 7, "2024-04-01"]]})
    r2 = upload(client, fixed).json()
    assert r2["sheets"][0]["updated"] == 1 and r2["sheets"][0]["added"] == 0
    fds = [i for i in client.get("/api/wealth").json()["items"] if i["kind"] == "fixed_deposit"]
    assert len(fds) == 1 and fds[0]["amount"] == 250_000


def test_a_csv_of_wealth_items_and_missing_columns(client):
    csv = b"Type,Amount\nPPF,100000\nEPF,250000\nCash,40000\n"
    r = upload(client, csv, name="wealth.csv").json()
    assert r["totals"]["wealth"] == 3
    bad = b"Coupon,Name\n7.1,Some bond\n"
    r = upload(client, bad, name="bonds.csv").json()
    assert r["totals"]["bonds"] == 0 and "Maturity" in r["skipped"][0]


@pytest.mark.parametrize("raw, kind", [("FD", "fixed_deposit"), ("HDFC Bank FD", "fixed_deposit"),
                                       ("Recurring Deposit", "recurring_deposit"), ("VPF", "epf"),
                                       ("NPS Tier I", "nps"), ("ULIP", "life_insurance"),
                                       ("SBI Term Plan", "term_insurance"), ("Savings account", "cash"),
                                       ("Atal Pension", "pension"), ("Shares", None)])
def test_kind_words(raw, kind):
    assert workbook.kind_of(raw) == kind
