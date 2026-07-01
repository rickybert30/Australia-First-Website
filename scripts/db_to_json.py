#!/usr/bin/env python3
"""Emit candidates.json and party_donations.json from data/candidates.db.

Proves the SQLite layer is a faithful source of truth: the output is the same
data the static site already consumes. Party/donor aggregates are DERIVED here
with SQL (sums, counts, per-year totals) rather than stored, so they can't drift.

Usage:
  python3 scripts/db_to_json.py            # write data/*.json from the DB
  python3 scripts/db_to_json.py --check    # emit in-memory and diff vs committed
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
DB = os.path.join(DATA, "candidates.db")


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def sources_for(c, table, id_col, id_val):
    rows = c.execute(
        f"""SELECT s.title,s.url,s.publisher,s.date FROM {table} t
            JOIN source s ON s.id=t.source_id WHERE t.{id_col}=? ORDER BY t.ord""",
        (id_val,)).fetchall()
    return [{"title": r["title"], "url": r["url"], "publisher": r["publisher"],
             "date": r["date"]} for r in rows]


def donor_info_map(c):
    m = {}
    for r in c.execute("SELECT * FROM donor_info").fetchall():
        info = {k: r[k] for k in ("link", "link_type", "description", "category") if r[k]}
        if info:
            m[r["donor_name"]] = info
    return m


def emit_candidates(c):
    info = donor_info_map(c)
    meta = json.loads(c.execute("SELECT value FROM meta WHERE key='candidates'").fetchone()[0])
    out = []
    for cand in c.execute("SELECT * FROM candidate ORDER BY seq").fetchall():
        rec = {"id": cand["id"], "name": cand["name"]}
        for k in ("official_page", "party", "party_group", "jurisdiction", "chamber",
                  "electorate", "state", "status", "election", "poll_date",
                  "photo_url", "photo_credit_url", "last_updated"):
            if cand[k] is not None:
                rec[k] = cand[k]

        positions = {}
        for p in c.execute("SELECT * FROM position WHERE candidate_id=? ORDER BY id", (cand["id"],)):
            positions[p["issue"]] = {"summary": p["summary"],
                                     "sources": sources_for(c, "position_source", "position_id", p["id"]),
                                     "verified": bool(p["verified"])}
        rec["positions"] = positions

        if cand["roster_source_id"] is not None:
            s = c.execute("SELECT title,url,publisher,date FROM source WHERE id=?",
                          (cand["roster_source_id"],)).fetchone()
            rec["roster_source"] = {"title": s["title"], "url": s["url"],
                                    "publisher": s["publisher"], "date": s["date"]}
        if cand["candidacy_source_id"] is not None:
            s = c.execute("SELECT title,url,publisher,date FROM source WHERE id=?",
                          (cand["candidacy_source_id"],)).fetchone()
            rec["candidacy_source"] = {"title": s["title"], "url": s["url"],
                                       "publisher": s["publisher"], "date": s["date"]}

        if cand["donor_summary"] is not None:
            entries = []
            for e in c.execute("SELECT * FROM member_donation WHERE candidate_id=? ORDER BY seq", (cand["id"],)):
                ent = {"donor": e["donor_name"], "amount_aud": e["amount_aud"],
                       "financial_year": e["financial_year"], "source_type": e["source_type"],
                       "sources": sources_for(c, "member_donation_source", "member_donation_id", e["id"])}
                if e["donor_name"] in info:
                    ent["info"] = info[e["donor_name"]]
                entries.append(ent)
            rec["donors"] = {"summary": cand["donor_summary"],
                             "total_aud": cand["donor_total_aud"],
                             "entries": entries,
                             "sources": sources_for(c, "member_return_source", "candidate_id", cand["id"])}
        out.append(rec)
    return {"meta": meta, "candidates": out}


def emit_party_donations(c):
    info = donor_info_map(c)
    meta = json.loads(c.execute("SELECT value FROM meta WHERE key='party_donations'").fetchone()[0])
    parties = []
    for p in c.execute("SELECT * FROM party ORDER BY seq").fetchall():
        name = p["name"]
        # derive donor rows: total + by_year, sorted by total desc
        donors = []
        for d in c.execute(
                """SELECT donor_name, SUM(amount_aud) AS total FROM party_donation
                   WHERE party=? GROUP BY donor_name""", (name,)).fetchall():
            by_year = {r["financial_year"]: r["amount_aud"] for r in c.execute(
                "SELECT financial_year,amount_aud FROM party_donation WHERE party=? AND donor_name=? ORDER BY financial_year",
                (name, d["donor_name"]))}
            row = {"donor": d["donor_name"], "total_aud": d["total"], "by_year": by_year}
            if d["donor_name"] in info:
                row["info"] = info[d["donor_name"]]
            donors.append(row)
        donors.sort(key=lambda r: (-r["total_aud"], r["donor"]))

        years = [r["financial_year"] for r in c.execute(
            "SELECT DISTINCT financial_year FROM party_donation WHERE party=? ORDER BY financial_year", (name,))]
        totals_by_year = {r["financial_year"]: r["t"] for r in c.execute(
            "SELECT financial_year, SUM(amount_aud) AS t FROM party_donation WHERE party=? GROUP BY financial_year ORDER BY financial_year",
            (name,))}
        parties.append({
            "party": name,
            "total_aud": sum(d["total_aud"] for d in donors),
            "donor_count": len(donors),
            "financial_years": years,
            "totals_by_year": totals_by_year,
            "donors": donors,
            "source": {"title": p["source_title"], "url": p["source_url"], "publisher": p["source_publisher"]},
        })
    parties.sort(key=lambda p: (-p["total_aud"], p["party"]))
    return {"meta": meta, "parties": parties}


# ---- semantic comparison (dict keys order-insensitive; party donor lists sorted) ----
def canon(x, sort_lists=False):
    if isinstance(x, dict):
        return {k: canon(v, sort_lists) for k, v in sorted(x.items())}
    if isinstance(x, list):
        items = [canon(v, sort_lists) for v in x]
        if sort_lists:
            items = sorted(items, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
        return items
    return x


def diff_report(label, emitted, committed_path, sort_lists=False):
    committed = json.load(open(committed_path, encoding="utf-8"))
    a = canon(emitted, sort_lists)
    b = canon(committed, sort_lists)
    if a == b:
        print(f"  {label}: MATCH")
        return True
    # locate first difference for candidates by id
    print(f"  {label}: DIFFERENCES")
    if label == "candidates.json":
        ea = {c["id"]: c for c in emitted["candidates"]}
        eb = {c["id"]: c for c in committed["candidates"]}
        only_a = set(ea) - set(eb)
        only_b = set(eb) - set(ea)
        if only_a: print("    only in emitted:", list(only_a)[:5])
        if only_b: print("    only in committed:", list(only_b)[:5])
        for cid in ea:
            if cid in eb and canon(ea[cid]) != canon(eb[cid]):
                print("    first differing candidate:", cid)
                break
    return False


def main():
    check = "--check" in sys.argv
    c = con()
    cand = emit_candidates(c)
    party = emit_party_donations(c)
    c.close()
    if check:
        print("Round-trip parity vs committed JSON:")
        ok1 = diff_report("candidates.json", cand, os.path.join(DATA, "candidates.json"))
        ok2 = diff_report("party_donations.json", party, os.path.join(DATA, "party_donations.json"), sort_lists=True)
        sys.exit(0 if (ok1 and ok2) else 1)
    json.dump(cand, open(os.path.join(DATA, "candidates.json"), "w"), indent=2, ensure_ascii=False)
    json.dump(party, open(os.path.join(DATA, "party_donations.json"), "w"), indent=2, ensure_ascii=False)
    print("Emitted candidates.json and party_donations.json from", DB)


if __name__ == "__main__":
    main()
