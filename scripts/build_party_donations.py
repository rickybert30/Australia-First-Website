#!/usr/bin/env python3
"""Aggregate disclosed donations TO political parties from AEC data.

Source: AEC Transparency Register detailed receipts (political party returns),
filtered to Receipt Type = "Donation Received" for the four most recent
financial years, committed at data/sources/aec_party_donations.csv.

Branch-level recipients (e.g. "Australian Labor Party (N.S.W. Branch)",
"Liberal Party of Australia, NSW Division") are grouped into party families, and
donations are summed per (party, donor). Only "Donation Received" receipts are
included, so public funding and electoral-commission payments are excluded.

Output: data/party_donations.json

Usage: python3 scripts/build_party_donations.py
"""

import csv
import json
import os
from collections import defaultdict

import donor_info as donor_info_mod

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "sources", "aec_party_donations.csv")
DEST = os.path.join(HERE, "..", "data", "party_donations.json")
BUILD_DATE = "2026-06-26"
REGISTER_URL = "https://transparency.aec.gov.au/AnnualDetailedReceipts"
TOP_N = 20
MIN_PARTY_TOTAL = 20000  # don't list parties with trivial disclosed donations


def family(name):
    n = name.lower()
    if "labor" in n:
        return "Labor (ALP)"
    if "liberal national party" in n:
        return "Liberal National Party (Qld)"
    if "country liberal" in n:
        return "Country Liberal Party (NT)"
    if "liberal" in n:
        return "Liberal Party"
    if "national" in n:
        return "The Nationals"
    if "greens" in n:
        return "The Greens"
    if "one nation" in n or "hanson" in n:
        return "Pauline Hanson's One Nation"
    if "united australia" in n or "palmer" in n:
        return "United Australia Party"
    if "katter" in n:
        return "Katter's Australian Party"
    if "lambie" in n:
        return "Jacqui Lambie Network"
    if "animal justice" in n:
        return "Animal Justice Party"
    if "legalise cannabis" in n:
        return "Legalise Cannabis Australia"
    if "sustainable australia" in n:
        return "Sustainable Australia Party"
    if "centre alliance" in n or "xenophon" in n:
        return "Centre Alliance"
    if "democrats" in n:
        return "Australian Democrats"
    if "shooters" in n or "fishers" in n:
        return "Shooters, Fishers and Farmers Party"
    return name.strip()


def main():
    registry = donor_info_mod.load()
    # party -> donor -> {fy: amount}
    donors = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    fys = defaultdict(set)
    with open(SRC, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            party = family(row["Recipient Name"])
            donor = " ".join(row["Received From"].split()).strip() or "(unspecified)"
            fy = row["Financial Year"]
            try:
                amount = float(row["Value"] or 0)
            except ValueError:
                amount = 0.0
            donors[party][donor][fy] += amount
            fys[party].add(fy)

    parties = []
    for party, dmap in donors.items():
        total = sum(sum(years.values()) for years in dmap.values())
        if total < MIN_PARTY_TOTAL:
            continue
        totals_by_year = defaultdict(float)
        donor_list = []
        for donor, years in dmap.items():
            dtotal = sum(years.values())
            for fy, amt in years.items():
                totals_by_year[fy] += amt
            entry = {
                "donor": donor,
                "total_aud": round(dtotal),
                "by_year": {fy: round(amt) for fy, amt in sorted(years.items())},
            }
            info = donor_info_mod.info_for(donor, registry)
            if info:
                entry["info"] = info
            donor_list.append(entry)
        donor_list.sort(key=lambda d: d["total_aud"], reverse=True)
        parties.append({
            "party": party,
            "total_aud": round(total),
            "donor_count": len(dmap),
            "financial_years": sorted(fys[party]),
            "totals_by_year": {fy: round(totals_by_year[fy]) for fy in sorted(totals_by_year)},
            "donors": donor_list,
            "source": {
                "title": f"AEC Transparency Register — detailed receipts, {party}",
                "url": REGISTER_URL,
                "publisher": "Australian Electoral Commission",
            },
        })
    parties.sort(key=lambda p: p["total_aud"], reverse=True)

    out = {
        "meta": {
            "description": "Disclosed donations to political parties (AEC detailed receipts, "
                           "Donation Received only), summed per donor across the four most recent "
                           "financial years. Branch returns are grouped into party families.",
            "source_url": REGISTER_URL,
            "window": "2021-22 to 2024-25",
            "note": "Excludes public funding and electoral-commission payments. Only donations "
                    "above the disclosure threshold are itemised in AEC returns.",
            "last_updated": BUILD_DATE,
        },
        "parties": parties,
    }
    with open(DEST, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(parties)} parties.")
    for p in parties[:8]:
        print(f"  {p['party']:38} ${p['total_aud']:>12,}  ({p['donor_count']} donors)")


if __name__ == "__main__":
    main()
