# Relational layer (SQLite)

A build-time source-of-truth database for the transparency dataset. It exists to
give the data **relational integrity** — proper keys and joins — without changing
anything the static site serves. The committed JSON stays authoritative for now;
the database is a parallel, reproducible view that can emit that exact JSON back.

## Why

The site's data lives in several JSON files that are stitched together by
string-matching, most fragilely on **donor names** — the same entity shows up as
`Cormack Foundation`, `Cormack Foundation Pty Ltd`, and `Cormack Foundation Pty
Limited`. A relational model turns those implicit links into real foreign keys,
so cross-cutting questions become one line of SQL instead of a bespoke script.

A server database (Postgres/MySQL) is deliberately **not** used: the site is
static, read-only, free to host on GitHub Pages, and tiny (~850 members). SQLite
fits that model — one file, no server, lives in git-adjacent tooling.

## Files

| File | Role |
|---|---|
| `db/schema.sql` | The schema: `candidate`, `position`, `donor`, `donor_info`, `party_donation`, `member_donation`, plus deduplicated `source` and join tables. |
| `scripts/build_db.py` | Ingest the committed JSON → `data/candidates.db`. |
| `scripts/db_to_json.py` | Emit `candidates.json` + `party_donations.json` from the DB. `--check` diffs against the committed files. |

`data/candidates.db` is git-ignored — it's derived. Regenerate any time:

```sh
python3 scripts/build_db.py           # JSON  -> SQLite
python3 scripts/db_to_json.py --check # SQLite -> JSON, verify identical
```

Round-trip parity is verified: the emitted `candidates.json` and
`party_donations.json` are data-identical to the committed files. Party and
donor **aggregates (totals, counts, per-year sums) are derived on emit with SQL**,
never stored, so they cannot drift from the underlying rows.

## The donor hub

`donor(name PRIMARY KEY, canonical_id)` holds one row per donor name exactly as
disclosed to the AEC. `donor_info`, `party_donation`, and `member_donation` all
reference it. `canonical_id` is reserved (null today) for a future consolidation
pass that would map spelling variants to a single entity **without changing
emitted output** — the point where the "Cormack" problem gets fixed for good.

## Example queries

```sql
-- Cross-party donors (gave to more than one party), with their description
SELECT pd.donor_name, COUNT(DISTINCT pd.party) AS parties,
       SUM(pd.amount_aud) AS total, di.category
FROM party_donation pd
LEFT JOIN donor_info di ON di.donor_name = pd.donor_name
GROUP BY pd.donor_name HAVING parties > 1
ORDER BY total DESC;

-- Faith positions by party grouping (positions joined to candidates)
SELECT c.party_group, COUNT(*) AS n
FROM position p JOIN candidate c ON c.id = p.candidate_id
WHERE p.issue = 'faith'
GROUP BY c.party_group ORDER BY n DESC;

-- Donors that appear in BOTH party and member-return disclosures
SELECT name FROM donor
WHERE name IN (SELECT donor_name FROM party_donation)
  AND name IN (SELECT donor_name FROM member_donation);
```

## Donor consolidation

`scripts/consolidate_donors.py` (run automatically by `build_db.py`) populates
`donor.canonical_id`, mapping spelling variants of the same entity to one
canonical name — 152 spellings folded into 112 entities. Roll spellings up with
`COALESCE(canonical_id, name)`. It's conservative (strips only known corporate/
trust boilerplate, never merges on a key under 4 characters) and does not change
emitted JSON — donors keep their exact disclosed names.

## Diffable serialised form

`build_db.py` also writes **`db/candidates.sql`**, a deterministic text dump of
the whole assembled dataset (`sqlite3 .dump`). That file is committed as the
canonical, reviewable serialisation — schema changes and data edits show up as
readable diffs, and the database can be rebuilt from it with
`sqlite3 data/candidates.db < db/candidates.sql`. The binary `.db` stays
git-ignored.

## In-browser SQL explorer

`explore.html` (+ `assets/explore.js`) runs these queries **client-side** with
sql.js (WASM, vendored under `assets/vendor/sqljs/` — no third-party requests).
It fetches `data/candidates.db`, which the GitHub Pages workflow builds at deploy
time via `python3 scripts/build_db.py`. Nothing is sent to a server; readers get
real ad-hoc SQL over the whole dataset. Linked from the main page's nav.

## Possible next steps (not done here)

- **Flip authoring fully into the DB:** today the DB is assembled from the
  committed JSON/CSV inputs; a full flip would author positions and donor_info
  directly in the DB and generate all JSON from it.
- **Surface consolidated donor totals in the main UI** (currently only the SQL
  explorer rolls spellings up via `canonical_id`).
