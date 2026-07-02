# Serving the site publicly

The site is static and deploys to **GitHub Pages** automatically on every push to
`main` (`.github/workflows/deploy-pages.yml`). This document covers the steps that
happen **outside the repo**: putting it on your own domain, analytics, a CDN, and
monitoring. Everything here is either free or costs only the domain registration.

## 1. Custom domain

1. **Register a domain** (~AU$15–30/yr) at any registrar (e.g. VentraIP, Cloudflare
   Registrar, Namecheap). Notes for Australian TLDs: `.au` and `.com.au` require an
   Australian presence (an Australian resident individual qualifies; `.com.au` also
   accepts an ABN/ACN). `.org`/`.info`/`.com` have no such requirement.
2. **Add DNS records** at the registrar:
   - Apex (`yourdomain.au`): four **A records** to GitHub Pages —
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - `www`: a **CNAME record** to `rigbygroyp.github.io`
3. **Wire the repo to the domain** (one command, then commit):
   ```
   python3 scripts/set_domain.py yourdomain.au
   git add -A && git commit -m "Point site at yourdomain.au" && git push
   ```
   This rewrites the canonical/OpenGraph URLs, sitemap, robots.txt and 404 links,
   and creates the `CNAME` file.
4. **Repo settings**: GitHub → Settings → Pages → Custom domain → enter the domain,
   wait for the DNS check, then tick **Enforce HTTPS** (the certificate is issued
   automatically; can take up to an hour after DNS propagates).

## 2. Analytics (GoatCounter — free, no cookies)

1. Create a free account at [goatcounter.com](https://www.goatcounter.com) and pick a
   site code.
2. In `index.html`, `explore.html` and `about.html`, find the commented GoatCounter
   block near `</body>`, replace `YOURCODE` with your site code, and uncomment it.
3. Update the privacy note in `about.html` (it promises the notice will change when
   analytics are enabled).

GoatCounter sets no cookies and stores no personal data — page counts only.

## 3. Optional: Cloudflare in front (free)

Adds a global CDN, brotli compression and DDoS protection — worthwhile because the
dataset JSON is a couple of MB:

1. Add the site to a free Cloudflare account and move the domain's nameservers to
   Cloudflare (the registrar step above then lives in Cloudflare DNS instead).
2. Recreate the A/CNAME records from step 1.2 with the proxy (orange cloud) ON.
3. SSL/TLS mode: **Full**. Enable Brotli (Speed → Optimization).
4. Cloudflare's built-in Web Analytics can be enabled from the dashboard with no
   code change, as an alternative to GoatCounter.

## 4. Uptime monitoring (free)

[UptimeRobot](https://uptimerobot.com) free tier: add an HTTPS monitor for the
homepage (5-minute checks, email alerts). GitHub Pages outages are rare but this
tells you before a reader does.

## 5. What the deploy publishes

The workflow stages a `_site/` directory containing only the public site —
`index.html`, `explore.html`, `about.html`, `404.html`, `robots.txt`,
`sitemap.xml`, `.nojekyll`, `CNAME` (once created), `assets/`, and `data/`
(the dataset is deliberately published in full, including `candidates.db` for the
in-browser SQL explorer). Build scripts, the `db/` dump and repo docs stay on
GitHub and are linked from the About page instead of being served.
