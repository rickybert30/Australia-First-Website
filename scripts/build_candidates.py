#!/usr/bin/env python3
"""Build data/candidates.json for the current (48th) federal parliament.

Merges three public sources, all committed under data/sources/:

  * aec_house_members_elected_2025.csv  — AEC Tally Room "Members Elected"
        (House: division, state, party, member). The authoritative roster of
        the 150 House members elected at the 2025 federal election.
  * openaustralia_senators.csv          — OpenAustralia.org current Senate roster
        (76 senators, with party and state encoded in the profile URI).
  * aec_mp_returns.csv / aec_mp_detailed_receipts.csv — AEC Member-of-Parliament
        annual donor returns (totals + itemised receipts).

Output: every current member as an `incumbent` record with party / electorate /
state, plus any donor data the AEC discloses for them. Members who appear in the
donor returns but are NOT in the current roster (e.g. lost their seat in 2025)
are retained as `former` so their disclosed donor data is not lost.

Policy positions are left empty — they are added separately with their own
sources (Hansard / voting records), never inferred here.

Usage:
    python3 scripts/build_candidates.py
"""

import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "sources")
POS_DIR = os.path.join(HERE, "..", "data", "positions")
DEST = os.path.join(HERE, "..", "data", "candidates.json")
BUILD_DATE = "2026-06-26"

# Policy-position issue keys, in display priority order. Each may have a file
# data/positions/<issue>.json mapping candidate id -> {summary, sources, verified}.
ISSUES = ["faith", "immigration", "foreign_policy", "economic_nationalism", "citizenship_eligibility"]

AEC_HOUSE_URL = "https://results.aec.gov.au/31496/Website/HouseDownloadsMenu-31496-Csv.htm"
AEC_DONOR_URL = "https://transparency.aec.gov.au/MemberOfParliament"

STATE_MAP = {
    "nsw": "NSW", "new_south_wales": "NSW",
    "victoria": "VIC", "vic": "VIC",
    "queensland": "QLD", "qld": "QLD",
    "wa": "WA", "western_australia": "WA",
    "sa": "SA", "south_australia": "SA",
    "tasmania": "TAS", "tas": "TAS",
    "act": "ACT", "australian_capital_territory": "ACT",
    "nt": "NT", "northern_territory": "NT",
}

TITLES = re.compile(r"\b(senator|hon|dr|mr|mrs|ms|miss|the|am|ao|oam|qc|kc|sc|mp)\b", re.IGNORECASE)

# Donor returns occasionally use a member's formal given name while the roster
# uses the common one. Map donor-return norm_key -> roster norm_key.
ALIASES = {
    "antony pasin": "tony pasin",
    "robert katter": "bob katter",
    "antonio zappia": "tony zappia",
}

# OpenAustralia lists a couple of Senate officeholders with a blank "-" party.
# Correct them from the public record, keyed by candidate id.
PARTY_FIX = {
    "slade-brockman-wa": "Liberal Party",
    "sue-lines-wa": "Australian Labor Party",
}

# Normalised party groupings for clean filtering. The exact party (as the source
# reported it) is preserved; party_group collapses source-labelling variants
# (e.g. "Liberal"/"Liberal Party", "The Nationals"/"National Party") and the
# Coalition partners into one filterable group.
PARTY_GROUP = {
    "Australian Labor Party": "Labor",
    "Liberal": "Coalition",
    "Liberal Party": "Coalition",
    "Liberal National Party of Queensland": "Coalition",
    "Liberal National Party": "Coalition",
    "The Nationals": "Coalition",
    "National Party": "Coalition",
    "Country Liberal Party": "Coalition",
    "Australian Greens": "Greens",
    "The Greens": "Greens",
    "Pauline Hanson's One Nation Party": "One Nation",
    "Independent": "Independent",
    "Katter's Australian Party (KAP)": "Other / minor party",
    "Centre Alliance": "Other / minor party",
    "Jacqui Lambie Network": "Other / minor party",
    "United Australia Party": "Other / minor party",
    "Australia's Voice": "Other / minor party",
}


def party_group(party):
    if party in PARTY_GROUP:
        return PARTY_GROUP[party]
    return "" if party in ("", "-") else "Other / minor party"


def proper_case(surname):
    """Convert an all-caps AEC surname to proper case, preserving Mc, apostrophes
    and hyphens (ALBANESE->Albanese, McBAIN->McBain, O'BRIEN->O'Brien)."""
    def cap(w):
        if not w:
            return w
        if w[:2].lower() == "mc" and len(w) > 2:
            return "Mc" + w[2].upper() + w[3:].lower()
        return w[:1].upper() + w[1:].lower()
    parts = re.split(r"([-' ])", surname)
    return "".join(p if p in "-' " else cap(p) for p in parts)


def norm_key(name):
    """Normalise a personal name to 'first last' lowercase, titles stripped."""
    n = TITLES.sub(" ", name)
    n = re.sub(r"[^a-zA-Z\s'-]", " ", n)
    tokens = [t for t in re.split(r"\s+", n.strip().lower()) if t]
    if not tokens:
        return ""
    # Use first + last token only — robust to middle names / honorific noise.
    return f"{tokens[0]} {tokens[-1]}" if len(tokens) > 1 else tokens[0]


def slugify(name, suffix=""):
    def clean(s):
        return re.sub(r"[^a-zA-Z0-9]+", "-", TITLES.sub(" ", s)).strip("-").lower()
    base = clean(name)
    return f"{base}-{clean(suffix)}".strip("-") if suffix else base


def read_csv(path, skip=0):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for _ in range(skip):
            next(f)
        return list(csv.DictReader(f))


def aec_donor_source(name, fy):
    return {
        "title": f"AEC Member of Parliament annual return — {name} ({fy})".strip(),
        "url": AEC_DONOR_URL,
        "publisher": "Australian Electoral Commission",
        "date": "",
    }


def build_donors():
    """Return {norm_key: (display_name, chamber, donor_block)} from AEC returns."""
    totals = defaultdict(list)   # name -> [(fy, total, count)]
    items = defaultdict(list)    # name -> [(fy, donor, amount)]
    chamber_of = {}

    for row in read_csv(os.path.join(SRC, "aec_mp_returns.csv")):
        name = re.sub(r"\s+", " ", row["Name"]).strip()
        chamber_of[name] = "Senate" if "Senator" in row["Return Type"] else "House of Representatives"
        totals[name].append((row["Financial Year"], int(row["Total Donations Received"] or 0),
                             int(row["Number of Donors"] or 0)))

    for row in read_csv(os.path.join(SRC, "aec_mp_detailed_receipts.csv")):
        if row["Return Type"] != "Member of HOR Return":
            continue
        name = re.sub(r"\s+", " ", row["Recipient Name"]).strip()
        try:
            amount = float(row["Value"] or 0)
        except ValueError:
            amount = None
        items[name].append((row["Financial Year"], re.sub(r"\s+", " ", row["Received From"]).strip(), amount))

    donors = {}
    for name in totals:
        yt = sorted(totals[name], reverse=True)
        grand_total = sum(total for _, total, _ in yt)
        parts = [f"{fy}: ${total:,} across {cnt} donor(s)" for fy, total, cnt in yt if total or cnt]
        summary = (
            "Donations disclosed directly to this member in AEC Member of Parliament returns. "
            + ("; ".join(parts) + ". " if parts else "")
            + "Note: member returns capture only donations made directly to the member, "
            "not money received via a party; figures are partial."
        )
        entries = [
            {"donor": donor, "amount_aud": amount, "financial_year": fy,
             "source_type": "unknown", "sources": [aec_donor_source(name, fy)]}
            for fy, donor, amount in sorted(items.get(name, []), reverse=True)
        ]
        latest_fy = yt[0][0] if yt else ""
        key = norm_key(name)
        key = ALIASES.get(key, key)
        donors[key] = (name, chamber_of.get(name, "House of Representatives"), {
            "summary": summary,
            "total_aud": grand_total,
            "entries": entries,
            "sources": [aec_donor_source(name, latest_fy)] if latest_fy else [],
        })
    return donors


def build_roster():
    """Return list of incumbent records and the set of norm_keys present."""
    records, keys = [], set()

    # House — AEC Members Elected (authoritative). File has a 1-line metadata
    # banner above the header row.
    for row in read_csv(os.path.join(SRC, "aec_house_members_elected_2025.csv"), skip=1):
        given, surname = row["GivenNm"].strip(), proper_case(row["Surname"].strip())
        name = f"{given} {surname}".strip()
        key = norm_key(name)
        keys.add(key)
        records.append({
            "id": slugify(name, row["DivisionNm"].lower()),
            "name": name,
            "party": row["PartyNm"].strip(),
            "chamber": "House of Representatives",
            "electorate": row["DivisionNm"].strip(),
            "state": row["StateAb"].strip(),
            "status": "incumbent",
            "official_page": "",
            "last_updated": BUILD_DATE,
            "positions": {},
            "_key": key,
            "_source": {
                "title": f"AEC 2025 Federal Election — Members Elected ({row['DivisionNm']}, {row['StateAb']})",
                "url": AEC_HOUSE_URL,
                "publisher": "Australian Electoral Commission",
                "date": "2025-06-16",
            },
        })

    # Senate — OpenAustralia current roster (state encoded in URI tail).
    for row in read_csv(os.path.join(SRC, "openaustralia_senators.csv")):
        name = re.sub(r"\s+", " ", row["Name"]).strip()
        state_tail = row["URI"].rstrip("/").rsplit("/", 1)[-1].lower()
        state = STATE_MAP.get(state_tail, "")
        key = norm_key(name)
        keys.add(key)
        rec = {
            "id": slugify(name, state.lower()),
            "name": name,
            "party": row["Party"].strip(),
            "chamber": "Senate",
            "status": "incumbent",
            "official_page": row["URI"].strip(),
            "last_updated": BUILD_DATE,
            "positions": {},
            "_key": key,
            "_source": {
                "title": f"OpenAustralia.org — Senator profile ({name})",
                "url": row["URI"].strip(),
                "publisher": "OpenAustralia.org",
                "date": "",
            },
        }
        if state:
            rec["state"] = state
        records.append(rec)

    return records, keys


def load_photos():
    """Load member portrait URLs (Wikipedia/Wikimedia Commons) keyed by id."""
    path = os.path.join(HERE, "..", "data", "photos.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_positions():
    """Load hand-sourced positions, merged by candidate id. Rebuild-safe:
    positions live in data/positions/<issue>.json, never in candidates.json."""
    positions = defaultdict(dict)  # candidate id -> {issue: position}
    if not os.path.isdir(POS_DIR):
        return positions
    for issue in ISSUES:
        path = os.path.join(POS_DIR, f"{issue}.json")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for cand_id, pos in data.items():
            positions[cand_id][issue] = pos
    return positions


def attach_positions(records, positions):
    matched = 0
    for rec in records:
        pos = positions.get(rec["id"])
        if not pos:
            continue
        # Preserve ISSUES display order.
        rec["positions"] = {k: pos[k] for k in ISSUES if k in pos}
        matched += 1
    return matched


def main():
    donors = build_donors()
    roster, roster_keys = build_roster()

    matched = 0
    for rec in roster:
        key = rec.pop("_key")
        roster_source = rec.pop("_source")
        # Attach a roster source on the record's donors block if no donor data,
        # so even members with no disclosed donations carry a citation for the
        # roster fact (party/electorate/state).
        if key in donors:
            _, _, donor_block = donors[key]
            rec["donors"] = donor_block
            matched += 1
        else:
            rec["donors"] = {
                "summary": "No donations disclosed directly to this member in AEC "
                           "Member of Parliament returns (money received via a party "
                           "is not attributed to individuals).",
                "total_aud": 0,
                "entries": [],
                "sources": [],
            }
        rec["roster_source"] = roster_source

    # Donor-only people not in the current roster -> retain as former.
    former = []
    for key, (name, chamber, donor_block) in donors.items():
        if key in roster_keys:
            continue
        former.append({
            "id": slugify(name),
            "name": name,
            "party": "",
            "chamber": chamber,
            "status": "former",
            "last_updated": BUILD_DATE,
            "positions": {},
            "donors": donor_block,
        })

    all_records = sorted(roster, key=lambda r: (r["chamber"], r.get("state", ""), r["name"])) + \
        sorted(former, key=lambda r: r["name"])

    # Correct blank party values, then tag each record with a normalised group.
    for rec in all_records:
        if rec["id"] in PARTY_FIX:
            rec["party"] = PARTY_FIX[rec["id"]]
        if rec.get("party") == "-":
            rec["party"] = ""
        rec["party_group"] = party_group(rec.get("party", ""))

    photos = load_photos()
    for rec in all_records:
        ph = photos.get(rec["id"])
        if ph:
            rec["photo_url"] = ph["photo_url"]
            rec["photo_credit_url"] = ph.get("page_url", "")

    positions = load_positions()
    pos_matched = attach_positions(all_records, positions)

    out = {
        "meta": {
            "description": "Australian federal candidate transparency dataset (48th Parliament). "
                           "Roster from AEC Members Elected (House) and OpenAustralia (Senate); "
                           "donor data from AEC Member of Parliament returns. Policy positions are "
                           "added separately with their own sources. See ../CONTRIBUTING.md.",
            "house_source": AEC_HOUSE_URL,
            "senate_source": "https://www.openaustralia.org.au/senators/",
            "donor_source": AEC_DONOR_URL,
            "last_updated": BUILD_DATE,
        },
        "candidates": all_records,
    }
    with open(DEST, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(all_records)} records "
          f"({len(roster)} incumbents, {len(former)} former).")
    print(f"Donor records matched to current members: {matched}/{len(donors)}.")
    print(f"Records with hand-sourced positions: {pos_matched}.")
    print(f"Records with a portrait: {sum(1 for r in all_records if r.get('photo_url'))}.")
    if former:
        print("Retained as former (donor data, not in current roster):")
        for r in former:
            print(f"  - {r['name']} ({r['chamber']})")


if __name__ == "__main__":
    main()
