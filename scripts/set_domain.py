#!/usr/bin/env python3
"""Point the site at a custom domain in one step.

Rewrites the canonical/OpenGraph URLs in the HTML pages, the sitemap and
robots.txt, fixes the absolute paths in 404.html (a project-page site lives
under /<repo>/, an apex domain at /), and writes the CNAME file GitHub Pages
needs. Idempotent — it reads the current base URL from index.html's canonical
tag, so it can be re-run or used to change domains later.

Usage: python3 scripts/set_domain.py yourdomain.au
Then:  see DEPLOYMENT.md for the DNS records and repo settings.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PAGES = ["index.html", "explore.html", "about.html"]


def main():
    if len(sys.argv) != 2 or "." not in sys.argv[1]:
        sys.exit("usage: python3 scripts/set_domain.py <domain>   e.g. candidatewatch.au")
    domain = sys.argv[1].strip().rstrip("/").replace("https://", "").replace("http://", "")
    new_base = f"https://{domain}"

    index = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    m = re.search(r'<link rel="canonical" href="(https://[^"]+?)/?"', index)
    if not m:
        sys.exit("could not find the canonical tag in index.html")
    old_base = m.group(1).rstrip("/")
    old_path = re.sub(r"https://[^/]+", "", old_base) + "/"   # '/Australia-First/' or '/'

    for name in PAGES + ["sitemap.xml", "robots.txt"]:
        path = os.path.join(ROOT, name)
        s = open(path, encoding="utf-8").read()
        s = s.replace(old_base + "/", new_base + "/").replace(old_base, new_base)
        open(path, "w", encoding="utf-8").write(s)

    # 404.html uses absolute paths (it is served for ANY missing URL, so
    # relative links would break); rebase them onto the new root.
    p404 = os.path.join(ROOT, "404.html")
    s = open(p404, encoding="utf-8").read()
    if old_path != "/":
        s = s.replace(f'href="{old_path}', 'href="/')
    open(p404, "w", encoding="utf-8").write(s)

    with open(os.path.join(ROOT, "CNAME"), "w", encoding="utf-8") as f:
        f.write(domain + "\n")

    print(f"Rebased site URLs: {old_base} -> {new_base}")
    print("Wrote CNAME. Next: DNS records + repo Settings -> Pages (see DEPLOYMENT.md).")


if __name__ == "__main__":
    main()
