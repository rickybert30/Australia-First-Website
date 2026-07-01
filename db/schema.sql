-- Relational schema for the Australia candidate-transparency dataset.
--
-- This is a build-time source-of-truth layer: scripts/build_db.py ingests the
-- committed JSON into data/candidates.db, and scripts/db_to_json.py emits the
-- exact same data/candidates.json and data/party_donations.json the static
-- site already consumes. Nothing on the site changes; the win is relational
-- integrity — especially the `donor` hub, which ends the fragile string
-- matching between party donations, member donations, and donor_info.
--
-- Aggregates (party totals, donor counts, totals-by-year) are NOT stored; they
-- are derived on emit with SQL, so they can never drift from the underlying rows.

PRAGMA foreign_keys = ON;

-- Free-form metadata blocks, stored verbatim as JSON so the emitted files keep
-- their exact `meta` sections. key = 'candidates' | 'party_donations'.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL            -- JSON object
);

-- A citation. Deduplicated by its content so the same source is one row even
-- when referenced by many positions/donations.
CREATE TABLE source (
    id        INTEGER PRIMARY KEY,
    title     TEXT,
    url       TEXT,
    publisher TEXT,
    date      TEXT,
    UNIQUE (title, url, publisher, date)
);

-- One elected member (federal or state/territory).
CREATE TABLE candidate (
    id               TEXT PRIMARY KEY,      -- e.g. victoria-jacinta-allan-bendigo-east
    seq              INTEGER NOT NULL,      -- preserves array order on emit
    name             TEXT NOT NULL,
    party            TEXT,
    party_group      TEXT,
    jurisdiction     TEXT,
    chamber          TEXT,
    electorate       TEXT,
    state            TEXT,
    status           TEXT,             -- incumbent | former | candidate
    election         TEXT,             -- running candidates only, e.g. 'Victoria 2026'
    poll_date        TEXT,             -- running candidates only
    official_page    TEXT,
    photo_url        TEXT,
    photo_credit_url TEXT,
    last_updated     TEXT,
    roster_source_id     INTEGER REFERENCES source(id),
    candidacy_source_id  INTEGER REFERENCES source(id),
    -- the member-return "donors" block header (nullable; only members with AEC returns)
    donor_summary    TEXT,
    donor_total_aud  INTEGER
);
CREATE INDEX idx_candidate_jur   ON candidate(jurisdiction);
CREATE INDEX idx_candidate_group ON candidate(party_group);

-- A member's recorded position on one issue (issue in the fixed ISSUES vocab).
CREATE TABLE position (
    id           INTEGER PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidate(id),
    issue        TEXT NOT NULL,
    summary      TEXT,
    verified     INTEGER,                   -- 0/1
    UNIQUE (candidate_id, issue)
);
CREATE INDEX idx_position_issue ON position(issue);

CREATE TABLE position_source (
    position_id INTEGER NOT NULL REFERENCES position(id),
    source_id   INTEGER NOT NULL REFERENCES source(id),
    ord         INTEGER NOT NULL,
    PRIMARY KEY (position_id, ord)
);

-- ---- Donors: the hub that used to be string-matched across files ----

-- One row per donor name exactly as disclosed to the AEC. (The same real-world
-- entity may still appear under several spellings; canonical_id is reserved for
-- a future consolidation pass and is null for now, so emitted JSON is unchanged.)
CREATE TABLE donor (
    name         TEXT PRIMARY KEY,
    canonical_id TEXT REFERENCES donor(name)
);

-- Background on a donor (link + description). Joins cleanly to donor now.
CREATE TABLE donor_info (
    donor_name  TEXT PRIMARY KEY REFERENCES donor(name),
    link        TEXT,
    link_type   TEXT,
    description TEXT,
    category    TEXT
);
CREATE TABLE donor_info_source (
    donor_name TEXT NOT NULL REFERENCES donor_info(donor_name),
    source_id  INTEGER NOT NULL REFERENCES source(id),
    ord        INTEGER NOT NULL,
    PRIMARY KEY (donor_name, ord)
);

-- A disclosed donation TO a political party, per (party, donor, financial year).
CREATE TABLE party_donation (
    id             INTEGER PRIMARY KEY,
    party          TEXT NOT NULL,
    donor_name     TEXT NOT NULL REFERENCES donor(name),
    financial_year TEXT NOT NULL,
    amount_aud     INTEGER NOT NULL
);
CREATE INDEX idx_party_donation_party ON party_donation(party);
CREATE INDEX idx_party_donation_donor ON party_donation(donor_name);

-- Per-party citation for the party-donations view (one row per party family).
CREATE TABLE party (
    name             TEXT PRIMARY KEY,
    seq              INTEGER NOT NULL,     -- emit order (by total desc at build time)
    source_title     TEXT,
    source_url       TEXT,
    source_publisher TEXT
);

-- A donation disclosed directly to a member (AEC member-of-parliament return).
CREATE TABLE member_donation (
    id             INTEGER PRIMARY KEY,
    candidate_id   TEXT NOT NULL REFERENCES candidate(id),
    seq            INTEGER NOT NULL,       -- preserves entry order on emit
    donor_name     TEXT NOT NULL REFERENCES donor(name),
    amount_aud     REAL,
    financial_year TEXT,
    source_type    TEXT
);
CREATE INDEX idx_member_donation_cand ON member_donation(candidate_id);

CREATE TABLE member_donation_source (
    member_donation_id INTEGER NOT NULL REFERENCES member_donation(id),
    source_id          INTEGER NOT NULL REFERENCES source(id),
    ord                INTEGER NOT NULL,
    PRIMARY KEY (member_donation_id, ord)
);

-- The header-level sources on a member's "donors" block.
CREATE TABLE member_return_source (
    candidate_id TEXT NOT NULL REFERENCES candidate(id),
    source_id    INTEGER NOT NULL REFERENCES source(id),
    ord          INTEGER NOT NULL,
    PRIMARY KEY (candidate_id, ord)
);
