"""Import everything you own from one Excel workbook (or one CSV).

Each sheet is recognised by its name and headings:

  trades   stocks, ETFs, mutual funds, gold and other commodities, bond trades.
           Same headings as the trade import (Date, Symbol, Exchange, Side,
           Quantity, Price...). Exchange MF / COMMODITY / BOND marks a mutual
           fund (AMFI code), a commodity (GOLD, SILVER...) or a bond id. A sheet
           named like "Mutual funds" or "Gold / commodities" needs no Exchange.
  bonds    bond terms (Coupon, Maturity...), optionally with the Quantity you
           hold, the purchase price and date, which records the purchase too.
  wealth   fixed and recurring deposits, PPF, EPF, NPS, pension, cash and
           insurance policies (Type, Amount, Rate, Start date...).

Importing the same workbook again does not create duplicates: trades keep
their ids, bonds are matched by id, and wealth items by type, name,
institution and start date (those are updated from the file instead)."""
from __future__ import annotations

import difflib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bond, Instrument, WealthItem
from app.ledger import ingest, mapping, table
from app.ledger.upstox import ParsedTrade
from app.market import commodities, symbols
from app.quant import wealth as wealth_kinds

# field -> (label, required, accepted headings, format help)
WEALTH_FIELDS: dict[str, tuple[str, bool, tuple[str, ...], str]] = {
    "kind": ("Type", True, ("type", "kind", "asset type", "category", "account type", "product", "holding type",
                            "investment type", "instrument type", "asset"),
             "FD, RD, PPF, EPF, NPS, Pension, Cash, Savings, Life insurance, ULIP, Term insurance"),
    "name": ("Name", False, ("name", "description", "account", "account name", "policy", "policy name", "plan",
                             "scheme", "details"), "e.g. HDFC FD 2024, LIC Jeevan Anand"),
    "institution": ("Institution", False, ("institution", "bank", "provider", "insurer", "company", "fund manager",
                                           "issuer", "with"), "Bank, insurer or fund manager"),
    "amount": ("Amount", True, ("amount", "balance", "principal", "value", "current value", "fund value",
                                "deposit amount", "invested", "corpus", "surrender value", "amount inr", "amount rs"),
               "Balance or fund value in ₹; for an FD the principal"),
    "rate": ("Rate %", False, ("rate", "rate %", "interest", "interest rate", "interest %", "roi", "return",
                               "return %", "growth %"), "Annual %; blank uses the usual rate for the type"),
    "start_date": ("Start date", False, ("start date", "start", "opened", "opening date", "date", "deposit date",
                                         "since", "invested on", "policy start"), "Needed for an FD"),
    "maturity_date": ("Maturity date", False, ("maturity date", "maturity", "matures", "end date", "maturity on"),
                      "When it matures or the policy ends"),
    "monthly_contribution": ("Monthly contribution", False, ("monthly contribution", "monthly", "contribution",
                                                             "instalment", "installment", "monthly sip", "sip"),
                             "₹ added each month (RD, PPF, EPF, NPS)"),
    "cover": ("Cover", False, ("cover", "sum assured", "sum insured", "life cover", "coverage"),
              "Insurance sum assured"),
    "premium": ("Premium", False, ("premium", "annual premium", "yearly premium", "premium per year"),
                "Insurance premium per year"),
    "notes": ("Notes", False, ("notes", "note", "remarks", "comment", "comments"), "Anything else"),
}

BOND_FIELDS: dict[str, tuple[str, bool, tuple[str, ...], str]] = {
    "bond_id": ("Bond ID", False, ("bond id", "id", "symbol", "code", "bond code", "ticker"),
                "Short id, e.g. GOI2033 (blank: made from the ISIN or name)"),
    "name": ("Name", False, ("name", "bond", "bond name", "security", "description", "issuer"),
             "e.g. 7.18% GS 2033"),
    "isin": ("ISIN", False, ("isin", "isin code"), "IN0020230010"),
    "face_value": ("Face value", False, ("face value", "face", "par", "par value", "fv", "denomination"),
                   "Per bond; blank means 1000"),
    "coupon_rate": ("Coupon %", True, ("coupon", "coupon %", "coupon rate", "rate", "interest", "interest rate"),
                    "Annual %, e.g. 7.18 (0 for a zero-coupon bond)"),
    "frequency": ("Frequency", False, ("frequency", "coupon frequency", "payments per year", "payout", "interest payout"),
                  "Yearly, Half-yearly, Quarterly, Monthly or Zero (blank: half-yearly)"),
    "maturity": ("Maturity", True, ("maturity", "maturity date", "matures", "redemption date"), "Maturity date"),
    "price": ("Valuation price", False, ("valuation price", "market price", "current price", "ltp", "valuation"),
              "Today's price per bond; blank uses the face value"),
    "quantity": ("Quantity", False, ("quantity", "qty", "units", "number of bonds", "holding", "bonds held"),
                 "How many you hold (records the purchase)"),
    "buy_price": ("Purchase price", False, ("purchase price", "buy price", "cost", "avg price", "average price",
                                            "price", "cost price"), "Price paid per bond; blank means face value"),
    "buy_date": ("Purchase date", False, ("purchase date", "buy date", "bought on", "date", "trade date",
                                          "allotment date"), "Needed when Quantity is given"),
}

KIND_WORDS = {
    "cash": ("cash", "savings", "savings account", "bank", "bank balance", "wallet", "current account", "sb", "sa",
             "liquid cash"),
    "fixed_deposit": ("fd", "fixed deposit", "term deposit", "tax saver fd", "corporate fd", "bank fd", "fdr",
                      "post office td", "td"),
    "recurring_deposit": ("rd", "recurring deposit"),
    "ppf": ("ppf", "public provident fund"),
    "epf": ("epf", "pf", "provident fund", "vpf", "employee provident fund", "uan"),
    "nps": ("nps", "national pension system", "national pension scheme", "tier 1", "tier i"),
    "pension": ("pension", "pension fund", "annuity", "superannuation", "gratuity", "retirement fund", "apy",
                "atal pension"),
    "life_insurance": ("life insurance", "lic", "endowment", "ulip", "money back", "moneyback", "savings plan",
                       "whole life", "insurance savings", "life policy", "traditional plan"),
    "term_insurance": ("term", "term insurance", "term plan", "term life", "pure term"),
}
FUZZY_ORDER = ("fixed_deposit", "recurring_deposit", "ppf", "epf", "nps", "pension", "term_insurance",
               "life_insurance", "cash")
FREQ_WORDS = {0: ("0", "zero", "zero coupon", "cumulative", "none", "at maturity"),
              1: ("1", "yearly", "annual", "annually", "once a year"),
              2: ("2", "half yearly", "half-yearly", "semi annual", "semi-annual", "semiannual", "twice a year"),
              4: ("4", "quarterly", "quarter"), 12: ("12", "monthly", "month")}
NAMESPACE_EXCHANGES = {"MF": "MF", "AMFI": "MF", "MUTUAL FUND": "MF", "MUTUAL FUNDS": "MF", "FUND": "MF",
                       "COMMODITY": "CMDTY", "COMMODITIES": "CMDTY", "CMDTY": "CMDTY", "PHYSICAL": "CMDTY",
                       "BULLION": "CMDTY", "GOLD": "CMDTY", "BOND": "BOND", "BONDS": "BOND"}
COMMODITY_WORDS = {"GOLD24K": "GOLD", "GOLD22K": "GOLD", "PHYSICALGOLD": "GOLD", "DIGITALGOLD": "GOLD",
                   "WTI": "CRUDE", "CRUDEOIL": "CRUDE", "NATURALGAS": "NATGAS", "GAS": "NATGAS"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _matcher(fields: dict) -> dict[str, set[str]]:
    return {f: {_key(a) for a in spec[2]} | {_key(spec[0])} for f, spec in fields.items()}


_WEALTH_KEYS, _BOND_KEYS = _matcher(WEALTH_FIELDS), _matcher(BOND_FIELDS)


def _match(heading: str, keys: dict[str, set[str]]) -> str | None:
    k = _key(heading)
    if not k:
        return None
    for f, ks in keys.items():
        if k in ks:
            return f
    best, score = None, 0.0
    for f, ks in keys.items():
        for a in ks:
            r = difflib.SequenceMatcher(None, k, a).ratio()
            if r > score:
                best, score = f, r
    return best if score >= 0.86 else None


def _guess(rows: list[list[str]], keys: dict[str, set[str]]) -> tuple[int, dict[str, str | None], int]:
    """(header row, {field: heading}, number of fields matched) for the best row of the first 30."""
    best = (0, {f: None for f in keys}, 0)
    for i, row in enumerate(rows[:30]):
        found: dict[str, str | None] = {f: None for f in keys}
        for cell in row:
            f = _match(cell, keys)
            if f and found[f] is None:
                found[f] = cell.strip()
        hits = sum(1 for v in found.values() if v)
        if hits > best[2]:
            best = (i, found, hits)
    return best


# ---------------------------------------------------------------- reading the file

def read_sheets(content: bytes) -> list[tuple[str, list[list[str]]]]:
    """[(sheet name, rows)] for every non-empty sheet; a CSV is one unnamed sheet."""
    if content[:2] != b"PK":
        return [("", table.read_rows(content))]
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    out = []
    for sheet in book.worksheets:
        rows = [[table._cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c for c in r)]
        if rows:
            out.append((sheet.title, rows))
    book.close()
    return out


def _name_hint(name: str) -> tuple[str | None, str]:
    """(sheet kind suggested by its name, default exchange for a trade sheet)."""
    n = name.lower()
    if re.search(r"read ?me|instruction|guide|help|notes", n):
        return "skip", ""
    if "bond" in n:
        return "bonds", ""
    if re.search(r"\b(fd|rd)s?\b|deposit|wealth|pension|insurance|policy|polic|cash|ppf|epf|nps|savings|other", n):
        return "wealth", ""
    if re.search(r"trade|stock|share|equit|holding|etf|portfolio", n):
        return "trades", ""                     # mixed sheets: a blank Exchange still means NSE
    if re.search(r"commod|gold|silver|bullion|metal", n):
        return "trades", "COMMODITY"
    if re.search(r"mutual|\bmfs?\b|fund", n):
        return "trades", "MF"
    return None, ""


def classify(name: str, rows: list[list[str]]) -> dict:
    """What a sheet holds, where its headings are and how its columns map."""
    hint, default_exchange = _name_hint(name)
    if hint == "skip":
        return {"kind": "skip", "reason": "instructions"}
    t_head = mapping.find_header(rows)
    t_guess = mapping.guess(rows, t_head)
    t_hits = sum(1 for v in t_guess["mapping"].values() if v)
    w_head, w_map, w_hits = _guess(rows, _WEALTH_KEYS)
    b_head, b_map, b_hits = _guess(rows, _BOND_KEYS)
    scores = {
        "bonds": b_hits + (3 if b_map["coupon_rate"] and b_map["maturity"] else 0) + (5 if hint == "bonds" else 0),
        "wealth": w_hits + (3 if w_map["kind"] and w_map["amount"] else 0) + (5 if hint == "wealth" else 0)
        - (2 if t_guess["mapping"]["quantity"] else 0),
        "trades": t_hits + (2 if not mapping.missing(t_guess["mapping"]) else 0) + (5 if hint == "trades" else 0),
    }
    kind = max(scores, key=scores.get)
    if scores[kind] < 2:
        return {"kind": "skip", "reason": "headings not recognised"}
    if kind == "trades":
        missing = mapping.missing(t_guess["mapping"])
        return {"kind": "trades", "header_row": t_head, "headings": t_guess["headings"],
                "mapping": t_guess["mapping"], "missing": [mapping.FIELDS[f][0] for f in missing],
                "default_exchange": default_exchange, "samples": t_guess["samples"]}
    fields, head, found = (BOND_FIELDS, b_head, b_map) if kind == "bonds" else (WEALTH_FIELDS, w_head, w_map)
    missing = [spec[0] for f, spec in fields.items() if spec[1] and not found[f]]
    if kind == "wealth" and "Amount" in missing and found["cover"]:
        missing.remove("Amount")                    # a term-insurance-only sheet
    return {"kind": kind, "header_row": head, "headings": [c.strip() for c in rows[head]], "mapping": found,
            "missing": missing, "samples": [r[:len(rows[head])] for r in rows[head + 1: head + 6]]}


# ---------------------------------------------------------------- parsing rows

def _num(raw: str, default: float = 0.0) -> float:
    s = str(raw).replace("%", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "")
    s = s.replace(",", "").strip()
    if not s or s in ("-", "—"):
        return default
    mult = 1.0
    low = s.lower()
    for word, m in (("lakhs", 1e5), ("lakh", 1e5), ("lac", 1e5), ("crores", 1e7), ("crore", 1e7), ("cr", 1e7)):
        if low.endswith(word):
            s, mult = s[: -len(word)].strip(), m
            break
    return float(s) * mult


def _date(raw: str) -> date | None:
    s = str(raw).strip()
    if not s:
        return None
    d = pd.to_datetime(s, dayfirst=not s[:4].isdigit())
    return d.date()


def kind_of(raw: str) -> str | None:
    k = " ".join(re.sub(r"[^a-z0-9 ]", " ", raw.lower()).split())
    if not k:
        return None
    if k.replace(" ", "_") in wealth_kinds.KINDS:
        return k.replace(" ", "_")
    for kind, words in KIND_WORDS.items():
        if k in words:
            return kind
    # Words inside a longer label ("HDFC Bank FD", "LIC Jeevan Anand", "SBI Term Plan"): the
    # specific kinds first, so a bank's name does not make a deposit look like cash.
    for kind in FUZZY_ORDER:
        words = ("savings", "cash", "wallet", "current account") if kind == "cash" else KIND_WORDS[kind]
        if any(re.search(rf"\b{re.escape(w)}\b", k) for w in words if len(w) > 2 or w in ("fd", "rd", "pf")):
            return kind
    return None


def _frequency(raw: str) -> int | None:
    k = " ".join(raw.lower().replace("-", " ").split())
    if not k:
        return 2
    for n, words in FREQ_WORDS.items():
        if k in (w.replace("-", " ") for w in words):
            return n
    return None


def _getter(rows, header, found):
    headings = [table.norm(h) for h in rows[header]]
    index = {f: headings.index(table.norm(col)) for f, col in found.items()
             if col and table.norm(col) in headings}

    def get(row, f):
        return row[index[f]].strip() if f in index and index[f] < len(row) else ""

    return get


@dataclass
class SheetResult:
    sheet: str
    kind: str
    added: int = 0
    updated: int = 0
    duplicates: int = 0
    skipped: list[str] = field(default_factory=list)


def import_wealth(session: Session, name: str, rows, info: dict) -> SheetResult:
    res = SheetResult(name, "wealth")
    get = _getter(rows, info["header_row"], info["mapping"])
    existing = session.scalars(select(WealthItem)).all()
    now = datetime.now().replace(microsecond=0)
    for n, row in enumerate(rows[info["header_row"] + 1:], start=info["header_row"] + 2):
        where = f"{name or 'file'} line {n}"
        try:
            raw_kind = get(row, "kind")
            kind = kind_of(raw_kind) or kind_of(get(row, "name"))
            if not kind:
                if raw_kind or get(row, "amount"):
                    res.skipped.append(f"{where}: unknown type '{raw_kind}'")
                continue
            vals = {"kind": kind, "name": get(row, "name") or raw_kind, "institution": get(row, "institution"),
                    "amount": _num(get(row, "amount")), "rate": _num(get(row, "rate")),
                    "start_date": _date(get(row, "start_date")), "maturity_date": _date(get(row, "maturity_date")),
                    "monthly_contribution": _num(get(row, "monthly_contribution")),
                    "cover": _num(get(row, "cover")), "premium": _num(get(row, "premium")),
                    "notes": get(row, "notes")[:400]}
            if kind == "term_insurance" and not vals["cover"] and vals["amount"]:
                vals["cover"], vals["amount"] = vals["amount"], 0.0     # the only figure given is the cover
            if min(vals["amount"], vals["rate"], vals["cover"], vals["premium"], vals["monthly_contribution"]) < 0:
                res.skipped.append(f"{where}: negative amount")
                continue
            if not (vals["amount"] or vals["cover"]):
                res.skipped.append(f"{where}: no amount")
                continue
            if kind == "fixed_deposit" and not vals["start_date"]:
                res.skipped.append(f"{where}: a fixed deposit needs its start date")
                continue
            if vals["maturity_date"] and vals["start_date"] and vals["maturity_date"] < vals["start_date"]:
                res.skipped.append(f"{where}: maturity is before the start date")
                continue
            ident = (kind, vals["name"].lower(), vals["institution"].lower(), vals["start_date"])
            item = next((w for w in existing
                         if (w.kind, (w.name or "").lower(), (w.institution or "").lower(), w.start_date) == ident),
                        None)
            if item is not None:
                if all(getattr(item, k) == v for k, v in vals.items()):
                    res.duplicates += 1
                    continue
                res.updated += 1
            else:
                item = WealthItem()
                session.add(item)
                existing.append(item)
                res.added += 1
            for k, v in vals.items():
                setattr(item, k, v)
            item.updated_at = now
        except Exception as exc:
            res.skipped.append(f"{where}: {exc}")
    return res


def _bond_id(raw_id: str, isin: str, name: str) -> str:
    base = raw_id or isin or name
    return "BOND:" + re.sub(r"[^A-Z0-9-]", "", base.upper().replace(" ", "-").replace("%", ""))[:30].strip("-")


def import_bonds(session: Session, name: str, rows, info: dict) -> tuple[SheetResult, list[ParsedTrade]]:
    res = SheetResult(name, "bonds")
    get = _getter(rows, info["header_row"], info["mapping"])
    trades: list[ParsedTrade] = []
    for n, row in enumerate(rows[info["header_row"] + 1:], start=info["header_row"] + 2):
        where = f"{name or 'file'} line {n}"
        try:
            raw_id, isin, title = get(row, "bond_id"), get(row, "isin").upper(), get(row, "name")
            if not (raw_id or isin or title):
                continue
            symbol = _bond_id(raw_id, isin, title)
            if not symbols.is_namespaced(symbol):
                res.skipped.append(f"{where}: cannot make a bond id from '{raw_id or isin or title}'")
                continue
            maturity = _date(get(row, "maturity"))
            if maturity is None:
                res.skipped.append(f"{where}: no maturity date")
                continue
            freq = _frequency(get(row, "frequency"))
            if freq is None:
                res.skipped.append(f"{where}: unknown coupon frequency '{get(row, 'frequency')}'")
                continue
            face = _num(get(row, "face_value"), 1000.0) or 1000.0
            terms = {"name": title, "isin": isin, "face_value": face, "coupon_rate": _num(get(row, "coupon_rate")),
                     "frequency": freq, "maturity": maturity, "price": _num(get(row, "price"))}
            bond = session.get(Bond, symbol)
            if bond is None:
                session.add(Bond(symbol=symbol, **terms))
                res.added += 1
            elif any(getattr(bond, k) != v for k, v in terms.items()):
                for k, v in terms.items():
                    setattr(bond, k, v)
                res.updated += 1
            else:
                res.duplicates += 1
            ingest.remember_instrument(session, symbol, title, isin)
            inst = session.get(Instrument, symbol)
            if inst is not None and title:
                inst.name = title
            qty = _num(get(row, "quantity"))
            if qty:
                bought = _date(get(row, "buy_date"))
                if bought is None:
                    res.skipped.append(f"{where}: bond saved, but the holding needs a purchase date")
                    continue
                price = _num(get(row, "buy_price"), face) or face
                trades.append(ParsedTrade(
                    trade_id=table.fallback_id("wb:", symbol, bought, qty, price), symbol=symbol, name=title,
                    exchange="BOND", scrip_code=symbol.partition(":")[2], side="BUY", quantity=qty, price=price,
                    traded_at=datetime.combine(bought, datetime.min.time()).replace(hour=10),
                    broker="manual", isin=isin))
        except Exception as exc:
            res.skipped.append(f"{where}: {exc}")
    return res, trades


def _namespaced_symbol(raw: str, ns: str) -> str | None:
    s = raw.strip().upper()
    if symbols.is_namespaced(s):
        return s
    if ns == "MF":
        digits = re.sub(r"\D", "", s)
        return f"MF:{digits}" if 3 <= len(digits) <= 8 and digits == s.replace(" ", "") else None
    if ns == "CMDTY":
        k = re.sub(r"[^A-Z0-9]", "", s)
        k = COMMODITY_WORDS.get(k, k)
        return f"CMDTY:{k}" if k in commodities.COMMODITIES else None
    k = re.sub(r"[^A-Z0-9-]", "", s)[:30]
    return f"BOND:{k}" if k else None


def parse_trades(name: str, rows, info: dict) -> tuple[list[ParsedTrade], list[str]]:
    """Trade rows, with MF / commodity / bond exchanges turned into their namespaced symbols."""
    head, cols = info["header_row"], info["mapping"]
    default = info.get("default_exchange", "")
    headings = [table.norm(h) for h in rows[head]]
    ex_i = headings.index(table.norm(cols["exchange"])) if cols.get("exchange") else None
    sym_i = headings.index(table.norm(cols["symbol"])) if cols.get("symbol") else None
    skipped: list[str] = []
    bad: set[int] = set()
    fixed = [list(r) for r in rows]
    for n, row in enumerate(fixed[head + 1:], start=head + 2):
        ex = (row[ex_i].strip().upper() if ex_i is not None and ex_i < len(row) else "") or default
        ns = NAMESPACE_EXCHANGES.get(ex)
        if ns and sym_i is not None and sym_i < len(row) and row[sym_i].strip():
            sym = _namespaced_symbol(row[sym_i], ns)
            if sym is None:
                what = {"MF": "an AMFI scheme code (digits)", "CMDTY": "one of " + ", ".join(commodities.COMMODITIES),
                        "BOND": "a bond id"}[ns]
                skipped.append(f"{name or 'file'} line {n}: '{row[sym_i]}' is not {what}")
                bad.add(n)
                row[sym_i] = ""
                continue
            row[sym_i] = sym
            if ex_i is not None and ex_i < len(row):
                row[ex_i] = ""
    parsed = mapping.parse(fixed, cols, head)
    skipped += [f"{name or 'file'} {s}" for s in parsed.skipped
                if not any(s.startswith(f"line {n}:") for n in bad)]
    return parsed.trades, skipped


# ---------------------------------------------------------------- the two entry points

def preview(content: bytes) -> dict:
    sheets = []
    for name, rows in read_sheets(content):
        info = classify(name, rows)
        data_rows = len(rows) - info.get("header_row", 0) - 1 if info["kind"] != "skip" else 0
        sheets.append({"sheet": name, "rows": max(data_rows, 0),
                       **{k: v for k, v in info.items() if k != "samples"}, "samples": info.get("samples", [])})
    if not sheets:
        raise ValueError("The file is empty")
    return {"sheets": sheets, "workbook": content[:2] == b"PK"}


def import_all(session: Session, content: bytes) -> dict:
    results: list[SheetResult] = []
    trades: list[ParsedTrade] = []
    trade_sheets: list[SheetResult] = []
    for name, rows in read_sheets(content):
        info = classify(name, rows)
        if info["kind"] == "skip":
            if info["reason"] != "instructions":
                r = SheetResult(name, "skip")
                r.skipped.append(f"{name or 'file'}: headings not recognised, nothing imported from it")
                results.append(r)
            continue
        if info["missing"]:
            r = SheetResult(name, info["kind"])
            r.skipped.append(f"{name or 'file'}: missing columns for {', '.join(info['missing'])}")
            results.append(r)
            continue
        if info["kind"] == "wealth":
            results.append(import_wealth(session, name, rows, info))
        elif info["kind"] == "bonds":
            res, bond_trades = import_bonds(session, name, rows, info)
            session.flush()
            results.append(res)
            trades += bond_trades
        else:
            got, skipped = parse_trades(name, rows, info)
            r = SheetResult(name, "trades", skipped=skipped)
            r.added = len(got)                          # corrected below, after duplicates are known
            trade_sheets.append(r)
            results.append(r)
            trades += got
    stored = ingest.store_trades(session, trades)
    if trade_sheets:
        trade_sheets[0].added, trade_sheets[0].duplicates, trade_sheets[0].updated = (
            stored.imported, stored.duplicates, stored.updated)
        for r in trade_sheets[1:]:
            r.added = 0
    session.commit()
    totals = {"trades": stored.imported, "trade_duplicates": stored.duplicates,
              "bonds": sum(r.added + r.updated for r in results if r.kind == "bonds"),
              "wealth": sum(r.added + r.updated for r in results if r.kind == "wealth")}
    return {"sheets": [r.__dict__ for r in results], "totals": totals,
            "skipped": [s for r in results for s in r.skipped]}


# ---------------------------------------------------------------- template

TEMPLATE_README = [
    ["Quant Terminal: everything you own, in one workbook"],
    [""],
    ["Fill in the sheets you need and delete the example rows. Sheets can be renamed or removed;"],
    ["each is recognised by its headings. Extra columns are ignored, and columns can be in any order."],
    [""],
    ["Stocks & funds", "Every buy and sell: stocks, ETFs, mutual funds, gold. Exchange: NSE, BSE, NASDAQ, NYSE, LSE..."],
    ["", "Mutual fund: Exchange = MF and Symbol = the AMFI scheme code (search the fund in the app to find it)."],
    ["", "Gold, silver: Exchange = COMMODITY, Symbol = GOLD (grams), SILVER (kg), PLATINUM, CRUDE, COPPER..."],
    ["Bonds", "Bond terms. Give Quantity, Purchase price and Purchase date to record the holding too."],
    ["Wealth", "FD, RD, PPF, EPF, NPS, Pension, Cash, Life insurance / ULIP (fund value), Term insurance (cover)."],
    ["", "A fixed deposit needs its Start date; its value then grows at its Rate until Maturity."],
    [""],
    ["Importing the same file again does not create duplicates; changed rows are updated."],
]


def template_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    readme = book.active
    readme.title = "Read me"
    for r in TEMPLATE_README:
        readme.append(r)
    readme["A1"].font = Font(bold=True, size=13)
    readme.column_dimensions["A"].width = 18
    readme.column_dimensions["B"].width = 110
    sheets = {
        "Stocks & funds": [list(mapping.TEMPLATE_HEADINGS),
                           ["15-01-2025", "10:15:00", "INFY", "NSE", "BUY", 10, 1850.5, "T1001", "INE009A01021", "Infosys"],
                           ["03-02-2025", "", "AAPL", "NASDAQ", "BUY", 5, 228.4, "T1002", "", "Apple Inc."],
                           ["10-02-2025", "", "122639", "MF", "BUY", 120.512, 82.97, "", "",
                            "Parag Parikh Flexi Cap Fund - Direct Growth"],
                           ["01-03-2025", "", "GOLD", "COMMODITY", "BUY", 20, 8450, "", "", "Gold coins, 20 g"]],
        "Bonds": [[BOND_FIELDS[f][0] for f in BOND_FIELDS],
                  ["GOI2033", "7.18% GS 2033", "IN0020230010", 100, 7.18, "Half-yearly", "14-08-2033", "", 50, 101.25,
                   "05-04-2024"],
                  ["NHAI2031", "NHAI 7.35% 2031", "", 1000, 7.35, "Yearly", "11-01-2031", 1012, "", "", ""]],
        "Wealth": [[WEALTH_FIELDS[f][0] for f in WEALTH_FIELDS],
                   ["FD", "HDFC FD", "HDFC Bank", 200000, 7.25, "01-04-2024", "01-04-2027", "", "", "", ""],
                   ["PPF", "PPF account", "SBI", 450000, 7.1, "", "", 12500, "", "", ""],
                   ["EPF", "EPF", "EPFO", 820000, 8.25, "", "", 7200, "", "", ""],
                   ["NPS", "NPS Tier I", "", 310000, "", "", "", 5000, "", "", ""],
                   ["Cash", "Savings account", "ICICI Bank", 150000, 3, "", "", "", "", "", ""],
                   ["Life insurance", "LIC Jeevan Anand", "LIC", 180000, "", "15-06-2015", "15-06-2040", "",
                    1000000, 24000, "surrender value"],
                   ["Term insurance", "Term plan", "HDFC Life", "", "", "01-01-2022", "01-01-2052", "", 10000000,
                    15000, ""]],
    }
    for title, data in sheets.items():
        ws = book.create_sheet(title)
        for r in data:
            ws.append(r)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(12, min(40, max(len(str(c.value or "")) for c in col) + 2))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
