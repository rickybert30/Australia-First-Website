#!/usr/bin/env python3
"""Ingest the committed JSON into a relational SQLite database (data/candidates.db).

This makes SQLite a build-time source of truth without changing the static site:
scripts/db_to_json.py emits byte-for-data-identical candidates.json and
party_donations.json back out. The relational model's main payoff is the `donor`
hub — party donations, member donations, and donor_info now join on a real key
instead of ad-hoc string matching.

Usage: python3 scripts/build_db.py   ->   writes data/candidates.db
"""
import json
import os
import sqlite3

import consolidate_donors

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
SCHEMA = os.path.join(HERE, "..", "db", "schema.sql")
DB = os.path.join(DATA, "candidates.db")
DUMP = os.path.join(HERE, "..", "db", "candidates.sql")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())

    # Deduplicated source rows: (title,url,publisher,date) -> id
    src_cache = {}

    def source_id(s):
        key = (s.get("title"), s.get("url"), s.get("publisher"), s.get("date", ""))
        if key not in src_cache:
            cur = con.execute(
                "INSERT OR IGNORE INTO source(title,url,publisher,date) VALUES (?,?,?,?)", key)
            if cur.lastrowid and con.execute(
                    "SELECT changes()").fetchone()[0]:
                src_cache[key] = cur.lastrowid
            else:
                src_cache[key] = con.execute(
                    "SELECT id FROM source WHERE title IS ? AND url IS ? AND publisher IS ? AND date IS ?",
                    key).fetchone()[0]
        return src_cache[key]

    def ensure_donor(name):
        con.execute("INSERT OR IGNORE INTO donor(name) VALUES (?)", (name,))

    cand = load("candidates.json")
    con.execute("INSERT INTO meta(key,value) VALUES ('candidates', ?)",
                (json.dumps(cand["meta"], ensure_ascii=False),))
    party = load("party_donations.json")
    con.execute("INSERT INTO meta(key,value) VALUES ('party_donations', ?)",
                (json.dumps(party["meta"], ensure_ascii=False),))

    # ---- candidates, positions, member donations ----
    for seq, c in enumerate(cand["candidates"]):
        rs_id = source_id(c["roster_source"]) if c.get("roster_source") else None
        cs_id = source_id(c["candidacy_source"]) if c.get("candidacy_source") else None
        donors = c.get("donors") or {}
        con.execute(
            """INSERT INTO candidate(id,seq,name,party,party_group,jurisdiction,chamber,
                 electorate,state,status,election,poll_date,official_page,photo_url,
                 photo_credit_url,last_updated,roster_source_id,candidacy_source_id,
                 donor_summary,donor_total_aud)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c["id"], seq, c["name"], c.get("party"), c.get("party_group"),
             c.get("jurisdiction"), c.get("chamber"), c.get("electorate"),
             c.get("state"), c.get("status"), c.get("election"), c.get("poll_date"),
             c.get("official_page"), c.get("photo_url"), c.get("photo_credit_url"),
             c.get("last_updated"), rs_id, cs_id,
             donors.get("summary"), donors.get("total_aud")))

        for issue, p in (c.get("positions") or {}).items():
            cur = con.execute(
                "INSERT INTO position(candidate_id,issue,summary,verified) VALUES (?,?,?,?)",
                (c["id"], issue, p.get("summary"), 1 if p.get("verified") else 0))
            pid = cur.lastrowid
            for ord_, s in enumerate(p.get("sources") or []):
                con.execute("INSERT INTO position_source(position_id,source_id,ord) VALUES (?,?,?)",
                            (pid, source_id(s), ord_))

        for ord_, s in enumerate(donors.get("sources") or []):
            con.execute("INSERT INTO member_return_source(candidate_id,source_id,ord) VALUES (?,?,?)",
                        (c["id"], source_id(s), ord_))

        for eseq, e in enumerate(donors.get("entries") or []):
            ensure_donor(e["donor"])
            cur = con.execute(
                """INSERT INTO member_donation(candidate_id,seq,donor_name,amount_aud,
                     financial_year,source_type) VALUES (?,?,?,?,?,?)""",
                (c["id"], eseq, e["donor"], e.get("amount_aud"),
                 e.get("financial_year"), e.get("source_type")))
            mid = cur.lastrowid
            for ord_, s in enumerate(e.get("sources") or []):
                con.execute("INSERT INTO member_donation_source(member_donation_id,source_id,ord) VALUES (?,?,?)",
                            (mid, source_id(s), ord_))
            # e["info"] is derived from donor_info at build time; not stored here.

    # ---- party donations ----
    for pseq, p in enumerate(party["parties"]):
        s = p.get("source") or {}
        con.execute("INSERT INTO party(name,seq,source_title,source_url,source_publisher) VALUES (?,?,?,?,?)",
                    (p["party"], pseq, s.get("title"), s.get("url"), s.get("publisher")))
        for d in p.get("donors") or []:
            ensure_donor(d["donor"])
            for fy, amt in (d.get("by_year") or {}).items():
                con.execute("INSERT INTO party_donation(party,donor_name,financial_year,amount_aud) VALUES (?,?,?,?)",
                            (p["party"], d["donor"], fy, amt))

    # ---- donor_info (keyed by donor; ensure the donor row exists) ----
    info = load("donor_info.json").get("donors", {})
    for name, rec in info.items():
        ensure_donor(name)
        con.execute("INSERT OR REPLACE INTO donor_info(donor_name,link,link_type,description,category) VALUES (?,?,?,?,?)",
                    (name, rec.get("link"), rec.get("link_type"), rec.get("description"), rec.get("category")))
        for ord_, s in enumerate(rec.get("sources") or []):
            con.execute("INSERT INTO donor_info_source(donor_name,source_id,ord) VALUES (?,?,?)",
                        (name, source_id(s), ord_))

    con.commit()

    # group spelling variants of the same donor (adds donor.canonical_id; JSON unchanged)
    consolidate_donors.run(con)

    # write a diffable text dump of the assembled dataset as the canonical serialised form
    with open(DUMP, "w", encoding="utf-8") as f:
        for line in con.iterdump():
            f.write(line + "\n")

    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ("candidate", "position", "donor", "donor_info", "party_donation",
               "member_donation", "source")}
    canon = con.execute("SELECT COUNT(*) FROM donor WHERE canonical_id IS NOT NULL").fetchone()[0]
    con.close()
    print("Wrote", DB)
    for t, n in counts.items():
        print(f"  {t}: {n}")
    print(f"  donor spellings mapped to a canonical entity: {canon}")
    print("Wrote", DUMP)


if __name__ == "__main__":
    main()
