#!/usr/bin/env python3
"""Populate donor.canonical_id by grouping spelling variants of the same donor.

The AEC discloses the same entity under many spellings — "Cormack Foundation",
"Cormack Foundation Pty Ltd", "Cormack Foundation Pty Limited"; ALLCAPS vs
title-case; HTML-entity artifacts. This groups them by a normalised key and
points every variant at one canonical name (the highest-disclosing spelling),
leaving the canonical row's own canonical_id NULL. Emitted JSON is unchanged —
donors are still keyed by their exact disclosed name; this only adds a link that
queries can COALESCE(canonical_id, name) to roll spellings together.

Conservative by design: it strips only well-known corporate/trust boilerplate,
and never merges on a normalised key shorter than 4 characters.

Callable as run(con) from build_db.py, or standalone against data/candidates.db.
"""
import html
import os
import re
import sqlite3

# trailing legal/structural boilerplate stripped when forming the match key
_SUFFIX = re.compile(
    r"\b("
    r"pty\.?\s*ltd\.?|pty\.?\s*limited|p/?l|proprietary|limited|ltd\.?|"
    r"inc\.?|incorporated|llc|llp|"
    r"nominees|holdings?|investments?|"
    r"no\.?\s*\d+|"
    r"the\s+trustee\s+for|as\s+trustee\s+for|a\.?t\.?f\.?|atf|"
    r"unit\s+trust|family\s+trust|discretionary\s+trust|trust|"
    r"t/?as|trading\s+as"
    r")\b", re.I)


def norm(name):
    s = html.unescape(name or "")               # &amp;#39; -> ', &amp; -> &
    s = s.replace("&", " and ")
    s = s.lower()
    s = re.sub(r"[.\-,'`\"()/]", " ", s)
    for _ in range(4):                            # peel repeated trailing boilerplate
        new = _SUFFIX.sub(" ", s)
        if new == s:
            break
        s = new
    s = re.sub(r"\bthe\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def run(con, verbose=False):
    con.execute("UPDATE donor SET canonical_id = NULL")
    # weight each donor by total disclosed (party + member) to pick the canonical spelling
    weight = {r[0]: r[1] for r in con.execute(
        "SELECT donor_name, SUM(amount_aud) FROM party_donation GROUP BY donor_name")}
    for r in con.execute("SELECT donor_name, SUM(amount_aud) FROM member_donation GROUP BY donor_name"):
        weight[r[0]] = weight.get(r[0], 0) + (r[1] or 0)

    groups = {}
    for (name,) in con.execute("SELECT name FROM donor"):
        k = norm(name)
        if len(k) < 4:                            # too short to match on safely
            continue
        groups.setdefault(k, []).append(name)

    merged_groups = 0
    merged_names = 0
    for k, names in groups.items():
        if len(names) < 2:
            continue
        canonical = max(names, key=lambda n: (weight.get(n, 0), len(n)))
        for n in names:
            if n != canonical:
                con.execute("UPDATE donor SET canonical_id=? WHERE name=?", (canonical, n))
                merged_names += 1
        merged_groups += 1
        if verbose:
            print(f"  [{canonical}] <- " + " | ".join(n for n in names if n != canonical))
    con.commit()
    print(f"Consolidated {merged_names} donor spelling(s) into {merged_groups} canonical entities.")
    return merged_groups, merged_names


if __name__ == "__main__":
    db = os.path.join(os.path.dirname(__file__), "..", "data", "candidates.db")
    c = sqlite3.connect(db)
    run(c, verbose=True)
    c.close()
