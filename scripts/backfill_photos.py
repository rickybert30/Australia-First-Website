#!/usr/bin/env python3
"""Backfill member portraits missing from Wikipedia using OpenAustralia.

For each incumbent without a photo in data/photos.json, looks up their
OpenAustralia person id (from the committed rosters in data/sources/) and fetches
the portrait at /images/mpsL/<id>.jpg. Placeholder/blank images are rejected two
ways: any image whose bytes repeat across members (OpenAustralia's shared 'no
photo' silhouette) and any image below a small byte threshold (blank/broken).

Run after fetch_photos.py; merges results into data/photos.json with source
"OpenAustralia" and the member's OA profile page for attribution.

Usage: python3 scripts/backfill_photos.py
"""
import csv
import hashlib
import json
import os
import re
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "sources")
PHOTOS = os.path.join(HERE, "..", "data", "photos.json")
CANDS = os.path.join(HERE, "..", "data", "candidates.json")
UA = "AUFirstTransparencyDB/1.0 (portrait backfill; +https://github.com/rickybert30/Australia-First-Website)"
MIN_BYTES = 2500  # below this an OA image is treated as blank/broken


def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def load_oa():
    oa = {}
    with open(os.path.join(SRC, "openaustralia_mps.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            oa[norm(r["First name"]) + "|" + norm(r["Last name"])] = (r["Person ID"], r["URI"])
    with open(os.path.join(SRC, "openaustralia_senators.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p = r["Name"].split()
            oa[norm(p[0]) + "|" + norm(p[-1])] = (r["Person ID"], r["URI"])
    return oa


def main():
    oa = load_oa()
    photos = json.load(open(PHOTOS))
    cands = json.load(open(CANDS))["candidates"]
    missing = [c for c in cands if c.get("status") == "incumbent" and c["id"] not in photos]

    fetched = {}
    for c in missing:
        p = c["name"].split()
        key = norm(p[0]) + "|" + norm(p[-1])
        if key not in oa:
            continue
        pid, uri = oa[key]
        url = f"https://www.openaustralia.org.au/images/mpsL/{pid}.jpg"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                blob = r.read()
        except Exception:
            continue
        fetched[c["id"]] = (pid, uri, blob, hashlib.md5(blob).hexdigest())

    counts = defaultdict(int)
    for *_, h in fetched.values():
        counts[h] += 1
    shared = {h for h, n in counts.items() if n > 1}

    added, rejected = 0, []
    for cid, (pid, uri, blob, h) in fetched.items():
        if h in shared or len(blob) < MIN_BYTES:
            rejected.append(cid)
            continue
        photos[cid] = {
            "photo_url": f"https://www.openaustralia.org.au/images/mpsL/{pid}.jpg",
            "page_url": uri,
            "page_title": "OpenAustralia.org",
            "source": "OpenAustralia",
        }
        added += 1

    json.dump(dict(sorted(photos.items())), open(PHOTOS, "w"), indent=2, ensure_ascii=False)
    print(f"Backfilled {added} portraits from OpenAustralia; rejected {len(rejected)} placeholder/blank: {rejected}")


if __name__ == "__main__":
    main()
