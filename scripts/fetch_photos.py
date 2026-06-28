#!/usr/bin/env python3
"""Fetch member portrait URLs from Wikipedia (Wikimedia Commons, freely licensed).

For each incumbent, searches Wikipedia, validates the top hit is actually an
Australian politician (via its short description), and records the lead-image
thumbnail URL plus the source page for attribution. Hotlinks the Wikimedia CDN
(upload.wikimedia.org), which is stable and permits reasonable hotlinking.

Output: data/photos.json  ->  { "<candidate id>": {"photo_url","page_url","page_title"} }
Unresolved members (no confident match) are listed but left without a photo.

Usage: python3 scripts/fetch_photos.py
"""

import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = os.path.join(HERE, "..", "data", "candidates.json")
DEST = os.path.join(HERE, "..", "data", "photos.json")
UA = "AUFirstTransparencyDB/1.0 (Wikipedia portrait lookup; +https://github.com/RigbyGroyp/Australia-First-Website)"
POLITICAL = ("politician", "senator", "member of", "mp,", "parliament", "minister")


def api(params):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def query_title(title):
    """Look up an exact page title; return (thumb, resolved_title, description)."""
    d = api({
        "action": "query",
        "titles": title,
        "prop": "pageimages|description",
        "piprop": "thumbnail",
        "pithumbsize": 320,
        "format": "json",
        "redirects": 1,
    })
    pages = d.get("query", {}).get("pages", {})
    for p in pages.values():
        if "missing" in p:
            return None, None, None
        return (p.get("thumbnail", {}).get("source"), p.get("title"), (p.get("description") or ""))
    return None, None, None


def lookup(name, context):
    """Resolve a member's portrait by EXACT title (with disambiguation fallbacks),
    validating both that it's a politician and that the member's surname appears
    in the resolved page title — so we never attach the wrong person's photo."""
    surname = name.split()[-1].lower()
    for title in (name, f"{name} (Australian politician)", f"{name} (politician)"):
        thumb, rtitle, desc = query_title(title)
        if not rtitle:
            continue
        is_pol = any(k in (desc or "").lower() for k in POLITICAL)
        name_ok = surname in rtitle.lower()
        if thumb and is_pol and name_ok:
            return thumb, rtitle, desc
    return None, None, None


def main():
    data = json.load(open(CANDIDATES))
    incumbents = [c for c in data["candidates"] if c.get("status") == "incumbent"]
    results, unresolved = {}, []

    for c in incumbents:
        context = c.get("electorate") or c.get("state") or ""
        try:
            thumb, title, desc = lookup(c["name"], context)
        except Exception as e:
            unresolved.append((c["id"], f"error: {e}"))
            continue
        is_pol = any(k in (desc or "").lower() for k in POLITICAL)
        if thumb and title and is_pol:
            results[c["id"]] = {
                "photo_url": thumb,
                "page_title": title,
                "page_url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            }
        else:
            unresolved.append((c["id"], f"title={title!r} desc={desc!r} thumb={bool(thumb)}"))
        time.sleep(0.1)

    json.dump(dict(sorted(results.items())), open(DEST, "w"), indent=2, ensure_ascii=False)
    print(f"Resolved photos: {len(results)}/{len(incumbents)}")
    print(f"Unresolved: {len(unresolved)}")
    for uid, why in unresolved:
        print(f"  - {uid}: {why}")


if __name__ == "__main__":
    main()
