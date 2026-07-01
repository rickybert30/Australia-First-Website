'use strict';

const POSITION_LABELS = {
  immigration: 'Immigration',
  faith: 'Faith & religion',
  economic_nationalism: 'Economic nationalism',
  foreign_policy: 'Foreign policy & aid',
  citizenship_eligibility: 'Citizenship (s44 eligibility)',
  abortion: 'Abortion & reproductive policy',
  voluntary_assisted_dying: 'Voluntary assisted dying',
  gender_lgbtq: 'Gender & LGBTQ+ policy',
  religious_freedom: 'Religious freedom',
  drugs_law_order: 'Drugs & law and order',
};

const ISSUE_KEYS = ['faith', 'immigration', 'foreign_policy', 'economic_nationalism', 'citizenship_eligibility',
  'abortion', 'voluntary_assisted_dying', 'gender_lgbtq', 'religious_freedom', 'drugs_law_order'];
const CHIP_LABELS = {
  faith: 'Faith',
  immigration: 'Immigration',
  foreign_policy: 'Foreign policy',
  economic_nationalism: 'Economic nat.',
  citizenship_eligibility: 'Citizenship',
  abortion: 'Abortion',
  voluntary_assisted_dying: 'VAD',
  gender_lgbtq: 'Gender/LGBTQ+',
  religious_freedom: 'Religious freedom',
  drugs_law_order: 'Drugs/law',
};

const state = {
  all: [],
  partyPositions: {},
  sort: 'name',
  view: 'incumbents', // 'incumbents' (in office + former) or 'running' (candidates for an upcoming election)
  filters: { search: '', jurisdiction: '', chamber: '', group: '', party: '', state: '', status: '', issue: '' },
};

// Conventional left->right placement of Australian party groups. Independents
// and minor-party members genuinely vary, so they sit at the centre by default.
const SPECTRUM = {
  'Greens': 1,
  'Labor': 2,
  'Independent': 3,
  'Other / minor party': 3,
  'Coalition': 4,
  'One Nation': 5,
};
const spectrumRank = (c) => (c.party_group in SPECTRUM ? SPECTRUM[c.party_group] : 3);

function hasDirectDonations(c) {
  const d = c.donors;
  return !!(d && ((d.entries && d.entries.length) || (d.total_aud && d.total_aud > 0)));
}

function hasIssue(c, key) {
  if (key === 'donors') return hasDirectDonations(c);
  return !!(c.positions && c.positions[key]);
}

async function load() {
  try {
    const res = await fetch('data/candidates.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.all = Array.isArray(data.candidates) ? data.candidates : [];
  } catch (err) {
    document.getElementById('results').innerHTML =
      `<p class="empty">Could not load data (${err.message}). If opening the file directly, serve the folder instead: <code>python3 -m http.server</code>.</p>`;
    return;
  }
  try {
    const r = await fetch('data/party_positions.json');
    if (r.ok) state.partyPositions = await r.json();
  } catch (e) { /* party fallback is optional */ }
  populatePartyFilter();
  renderCoverage();
  wireControls();
  wireTabs();
  wireDonorSearch();
  render();
  loadPartyDonations();
}

function wireDonorSearch() {
  const input = document.getElementById('donor-search');
  if (input) input.addEventListener('input', () => renderDonorSearch(input.value));
}

async function loadPartyDonations() {
  try {
    const res = await fetch('data/party_donations.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderParties(data);
  } catch (err) {
    document.getElementById('party-results').innerHTML =
      `<p class="empty">Could not load party donations (${err.message}).</p>`;
  }
}

const fmtAud = (n) => `$${Number(n).toLocaleString()}`;
const shortFy = (fy) => `FY${fy.replace('20', "'").replace('-', '–')}`;
const TOP_SHOWN = 25;
const partyState = { parties: [], donorIndex: [] };

function byYearLine(byYear) {
  return Object.entries(byYear || {})
    .map(([fy, amt]) => `${shortFy(fy)} ${fmtAud(amt)}`)
    .join(' · ');
}

// Renders a donor's name, linking it to the donor's own website/social when a
// donor_info record exists, plus a short sourced description and a category tag.
function donorNameCell(name, info) {
  const box = el('div', 'donor-name');
  if (info && info.link) {
    const a = document.createElement('a');
    a.href = info.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.className = 'donor-link';
    a.textContent = name;
    box.appendChild(a);
    if (info.link_type) {
      const tag = el('span', 'donor-linktype', info.link_type);
      box.appendChild(tag);
    }
  } else {
    box.appendChild(document.createTextNode(name));
  }
  if (info && info.category) box.appendChild(el('span', 'donor-cat', info.category));
  if (info && info.description) box.appendChild(el('div', 'donor-desc', info.description));
  return box;
}

function donorRow(donor, amount, byYear, info) {
  const tr = document.createElement('tr');
  const nameTd = el('td');
  nameTd.appendChild(donorNameCell(donor, info));
  const yl = byYearLine(byYear);
  if (yl) nameTd.appendChild(el('div', 'donor-years', yl));
  tr.appendChild(nameTd);
  tr.appendChild(el('td', 'num', fmtAud(amount)));
  return tr;
}

function renderParties(data) {
  const m = data.meta || {};
  document.getElementById('parties-intro').textContent =
    `Disclosed donations TO political parties (AEC detailed receipts, ${m.window || ''}). ${m.note || ''} ` +
    'Donor names appear exactly as disclosed to the AEC and the same entity may be listed under several spellings.';
  partyState.parties = data.parties || [];

  // Build a flat donor index for cross-party search.
  partyState.donorIndex = [];
  partyState.parties.forEach((p) => {
    (p.donors || []).forEach((d) => {
      partyState.donorIndex.push({ donor: d.donor, party: p.party, total_aud: d.total_aud, by_year: d.by_year, info: d.info });
    });
  });

  const tpl = document.getElementById('party-template');
  const out = document.getElementById('party-results');
  out.innerHTML = '';
  partyState.parties.forEach((p) => {
    const node = tpl.content.cloneNode(true);
    node.querySelector('.c-name').textContent = p.party;
    node.querySelector('.c-meta').textContent =
      `${fmtAud(p.total_aud)} total disclosed · ${p.donor_count} donor(s)`;
    node.querySelector('.party-years').textContent =
      'By year: ' + Object.entries(p.totals_by_year || {}).map(([fy, a]) => `${shortFy(fy)} ${fmtAud(a)}`).join(' · ');
    const tbody = node.querySelector('.party-donors');
    (p.donors || []).slice(0, TOP_SHOWN).forEach((d) => tbody.appendChild(donorRow(d.donor, d.total_aud, d.by_year, d.info)));
    const more = (p.donors || []).length - TOP_SHOWN;
    node.querySelector('.party-more').textContent = more > 0 ? `+ ${more} more disclosed donor(s) — use donor search to find them.` : '';
    const srcP = node.querySelector('.party-source');
    if (p.source && p.source.url) {
      const a = document.createElement('a');
      a.href = p.source.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.textContent = 'Source: AEC Transparency Register';
      srcP.appendChild(a);
    }
    out.appendChild(node);
  });
}

function renderDonorSearch(query) {
  const partyResults = document.getElementById('party-results');
  const donorResults = document.getElementById('donor-results');
  const q = query.trim().toLowerCase();
  if (!q) {
    partyResults.hidden = false;
    donorResults.hidden = true;
    return;
  }
  partyResults.hidden = true;
  donorResults.hidden = false;
  donorResults.innerHTML = '';

  // Group matching (party,donor) rows by donor name.
  const groups = new Map();
  partyState.donorIndex
    .filter((r) => r.donor.toLowerCase().includes(q))
    .forEach((r) => {
      if (!groups.has(r.donor)) groups.set(r.donor, { donor: r.donor, total: 0, rows: [], info: r.info });
      const g = groups.get(r.donor);
      g.total += r.total_aud;
      g.rows.push(r);
    });
  const sorted = [...groups.values()].sort((a, b) => b.total - a.total).slice(0, 80);

  if (sorted.length === 0) {
    donorResults.innerHTML = `<p class="empty">No disclosed donor matches “${query}”.</p>`;
    return;
  }
  sorted.forEach((g) => {
    const card = el('article', 'card');
    const head = el('header', 'card-head');
    const ht = el('div', 'c-headtext');
    const h2 = el('h2', 'c-name');
    if (g.info && g.info.link) {
      const a = document.createElement('a');
      a.href = g.info.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.className = 'donor-link';
      a.textContent = g.donor;
      h2.appendChild(a);
      if (g.info.link_type) h2.appendChild(el('span', 'donor-linktype', g.info.link_type));
    } else {
      h2.textContent = g.donor;
    }
    ht.appendChild(h2);
    if (g.info && g.info.category) ht.appendChild(el('span', 'donor-cat', g.info.category));
    ht.appendChild(el('p', 'c-meta', `${fmtAud(g.total)} disclosed across ${g.rows.length} party/parties`));
    if (g.info && g.info.description) ht.appendChild(el('p', 'donor-desc', g.info.description));
    head.appendChild(ht);
    card.appendChild(head);
    const table = el('table', 'donor-table');
    table.innerHTML = '<thead><tr><th>Recipient party</th><th>Total (AUD)</th></tr></thead>';
    const tbody = document.createElement('tbody');
    g.rows.sort((a, b) => b.total_aud - a.total_aud).forEach((r) => {
      const tr = document.createElement('tr');
      const td = el('td');
      td.appendChild(el('div', 'donor-name', r.party));
      const yl = byYearLine(r.by_year);
      if (yl) td.appendChild(el('div', 'donor-years', yl));
      tr.appendChild(td);
      tr.appendChild(el('td', 'num', fmtAud(r.total_aud)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);
    donorResults.appendChild(card);
  });
}

function wireTabs() {
  const vc = document.getElementById('view-candidates');
  const vp = document.getElementById('view-parties');
  // Only wire button tabs (the Explore link navigates away on its own).
  document.querySelectorAll('button.tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('active', b === btn));
      const v = btn.dataset.view;
      if (v === 'parties') {
        vc.hidden = true;
        vp.hidden = false;
      } else {
        vp.hidden = true;
        vc.hidden = false;
        state.view = v === 'running' ? 'running' : 'incumbents';
        render();
      }
    });
  });
}

function renderCoverage() {
  const inc = state.all.filter((c) => c.status === 'incumbent');
  const withAny = inc.filter((c) => c.positions && Object.keys(c.positions).length);
  const counts = ISSUE_KEYS
    .map((k) => ({ k, n: state.all.filter((c) => hasIssue(c, k)).length }))
    .filter((x) => x.n > 0)
    .map((x) => `${CHIP_LABELS[x.k]} ${x.n}`);
  const elc = document.getElementById('coverage');
  if (elc) {
    elc.textContent =
      `${inc.length} incumbents · ${withAny.length} with ≥1 sourced position — ` + counts.join(' · ');
  }
}

const GROUP_ORDER = ['Labor', 'Coalition', 'Greens', 'One Nation', 'Independent', 'Other / minor party'];

function populatePartyFilter() {
  const fill = (id, values) => {
    const sel = document.getElementById(id);
    values.forEach((v) => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  };
  const groups = [...new Set(state.all.map((c) => c.party_group).filter(Boolean))]
    .sort((a, b) => GROUP_ORDER.indexOf(a) - GROUP_ORDER.indexOf(b));
  fill('filter-group', groups);
  fill('filter-party', [...new Set(state.all.map((c) => c.party).filter(Boolean))].sort());
  // Jurisdictions: Federal first, then states alphabetically.
  const jurs = [...new Set(state.all.map((c) => c.jurisdiction).filter(Boolean))]
    .sort((a, b) => (a === 'Federal' ? -1 : b === 'Federal' ? 1 : a.localeCompare(b)));
  fill('filter-jurisdiction', jurs);
}

function wireControls() {
  const bind = (id, key) => {
    const el = document.getElementById(id);
    el.addEventListener('input', () => {
      state.filters[key] = el.value.trim();
      render();
    });
  };
  bind('search', 'search');
  bind('filter-jurisdiction', 'jurisdiction');
  bind('filter-chamber', 'chamber');
  bind('filter-group', 'group');
  bind('filter-party', 'party');
  bind('filter-state', 'state');
  bind('filter-status', 'status');
  bind('filter-issue', 'issue');
  const sortEl = document.getElementById('sort');
  sortEl.addEventListener('input', () => { state.sort = sortEl.value; render(); });
}

function sortCandidates(list) {
  const byName = (a, b) => a.name.localeCompare(b.name);
  if (state.sort === 'lr') return list.sort((a, b) => spectrumRank(a) - spectrumRank(b) || byName(a, b));
  if (state.sort === 'rl') return list.sort((a, b) => spectrumRank(b) - spectrumRank(a) || byName(a, b));
  return list.sort(byName);
}

function matches(c) {
  const f = state.filters;
  // Base split: the "Running candidates" view shows only upcoming-election
  // candidates; every other view shows people in (or formerly in) office.
  const isCandidate = c.status === 'candidate';
  if (state.view === 'running' ? !isCandidate : isCandidate) return false;
  if (f.jurisdiction && c.jurisdiction !== f.jurisdiction) return false;
  if (f.chamber && c.chamber !== f.chamber) return false;
  if (f.group && c.party_group !== f.group) return false;
  if (f.party && c.party !== f.party) return false;
  if (f.state && c.state !== f.state) return false;
  if (f.status && c.status !== f.status) return false;
  if (f.issue && !hasIssue(c, f.issue)) return false;
  if (f.search) {
    const hay = [c.name, c.party, c.electorate, c.state, c.chamber]
      .filter(Boolean).join(' ').toLowerCase();
    if (!hay.includes(f.search.toLowerCase())) return false;
  }
  return true;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function renderSources(sources) {
  if (!sources || sources.length === 0) {
    const span = el('span', 'no-source', 'No source on file — unverified');
    return span;
  }
  const ul = el('ul', 'sources');
  sources.forEach((s) => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = s.url || '#';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = s.publisher || s.title || 'source';
    a.title = [s.title, s.date].filter(Boolean).join(' — ');
    li.appendChild(a);
    ul.appendChild(li);
  });
  return ul;
}

function renderPosition(key, pos, isParty) {
  const wrap = el('div', isParty ? 'pos pos-party' : 'pos');
  const label = el('div', 'pos-label');
  label.appendChild(el('span', null, POSITION_LABELS[key] || key));
  if (isParty) {
    label.appendChild(el('span', 'badge party', 'party platform'));
  } else {
    const verified = pos.verified && pos.sources && pos.sources.length > 0;
    label.appendChild(el('span', `badge ${verified ? 'ok' : 'warn'}`, verified ? 'verified' : 'unverified'));
  }
  wrap.appendChild(label);
  wrap.appendChild(el('p', 'pos-summary', pos.summary || '—'));
  wrap.appendChild(renderSources(pos.sources));
  return wrap;
}

function renderDonors(donors) {
  const wrap = el('div', 'pos');
  const label = el('div', 'pos-label');
  label.appendChild(el('span', null, 'Donors (AEC disclosures)'));
  wrap.appendChild(label);
  if (donors.summary) wrap.appendChild(el('p', 'pos-summary', donors.summary));

  if (donors.entries && donors.entries.length) {
    const table = el('table', 'donor-table');
    table.innerHTML =
      '<thead><tr><th>Donor</th><th>Amount (AUD)</th><th>FY</th><th>Source type</th><th>Ref</th></tr></thead>';
    const tbody = document.createElement('tbody');
    donors.entries.forEach((d) => {
      const tr = document.createElement('tr');
      const nameTd = el('td');
      nameTd.appendChild(donorNameCell(d.donor || '—', d.info));
      tr.appendChild(nameTd);
      tr.appendChild(el('td', null, d.amount_aud != null ? `$${Number(d.amount_aud).toLocaleString()}` : '—'));
      tr.appendChild(el('td', null, d.financial_year || '—'));
      tr.appendChild(el('td', null, d.source_type || 'unknown'));
      const ref = document.createElement('td');
      ref.appendChild(renderSources(d.sources));
      tr.appendChild(ref);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
  }
  return wrap;
}

function renderCard(c) {
  const tpl = document.getElementById('card-template');
  const node = tpl.content.cloneNode(true);
  node.querySelector('.c-name').textContent = c.name;

  // Portrait (Wikimedia Commons via Wikipedia), linked to its source page.
  if (c.photo_url) {
    const link = node.querySelector('.c-photo-link');
    const img = node.querySelector('.c-photo');
    img.src = c.photo_url;
    img.alt = `Portrait of ${c.name}`;
    if (c.photo_credit_url) link.href = c.photo_credit_url;
    else link.removeAttribute('href');
    link.hidden = false;
    // If the image fails to load, hide the broken element.
    img.addEventListener('error', () => { link.hidden = true; });
  }
  const isCandidate = c.status === 'candidate';
  const metaBits = [
    c.party,
    c.jurisdiction && c.jurisdiction !== 'Federal' ? c.jurisdiction : null,
    c.chamber,
    c.electorate ? `${c.electorate} (${c.state || ''})` : c.state,
    isCandidate ? (c.election ? `candidate · ${c.election}` : 'candidate') : c.status,
  ].filter(Boolean);
  const meta = node.querySelector('.c-meta');
  meta.textContent = metaBits.join(' · ');
  const sourceLink = (src, label) => {
    if (!src || !src.url) return;
    meta.appendChild(document.createTextNode(' · '));
    const a = document.createElement('a');
    a.className = 'roster-src';
    a.href = src.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = label;
    a.title = src.title || '';
    meta.appendChild(a);
  };
  sourceLink(c.roster_source, 'roster source');
  sourceLink(c.candidacy_source, 'candidacy source');

  // At-a-glance chips: which issues this member has data for.
  const chipRow = el('div', 'chips');
  ISSUE_KEYS.forEach((key) => {
    if (hasIssue(c, key)) chipRow.appendChild(el('span', 'chip', CHIP_LABELS[key]));
  });
  if (hasIssue(c, 'donors')) chipRow.appendChild(el('span', 'chip chip-donor', 'Donors'));
  if (chipRow.children.length === 0) chipRow.appendChild(el('span', 'chip chip-empty', 'No positions on record'));
  node.querySelector('.c-headtext').appendChild(chipRow);

  const dl = node.querySelector('.positions');
  const positions = c.positions || {};
  Object.keys(POSITION_LABELS).forEach((key) => {
    if (positions[key]) {
      dl.appendChild(renderPosition(key, positions[key], false));
    } else if (c.jurisdiction === 'Federal') {
      // Party-platform fallback applies to federal issues only — state/territory
      // parliaments don't legislate on immigration, foreign policy, etc.
      const partyPos = (state.partyPositions[key] || {})[c.party_group];
      if (partyPos) dl.appendChild(renderPosition(key, partyPos, true));
    }
  });
  // Only show the per-member donations block when the member actually has
  // disclosed direct donations. For everyone else, party-level money is covered
  // in the Party donations tab, so the empty "no donations" notice is omitted.
  if (hasDirectDonations(c)) dl.appendChild(renderDonors(c.donors));
  return node;
}

function render() {
  const results = document.getElementById('results');
  const countEl = document.getElementById('count');
  results.innerHTML = '';
  const filtered = sortCandidates(state.all.filter(matches));
  const viewTotal = state.all.filter((c) =>
    state.view === 'running' ? c.status === 'candidate' : c.status !== 'candidate').length;
  const noun = state.view === 'running' ? 'candidate(s)' : 'record(s)';
  countEl.textContent = `${filtered.length} of ${viewTotal} ${noun}`;
  const note = document.getElementById('sort-note');
  if (note) {
    const isSpectrum = state.sort === 'lr' || state.sort === 'rl';
    note.hidden = !isSpectrum;
    note.textContent = isSpectrum
      ? 'Ordered by each member’s party along the conventional left–right spectrum (Greens → Labor → Coalition → One Nation). This reflects party, not a personal ideology score; independents and minor-party members vary and are placed at the centre.'
      : '';
  }
  if (filtered.length === 0) {
    results.innerHTML = '<p class="empty">No candidates match these filters.</p>';
    return;
  }
  filtered.forEach((c) => results.appendChild(renderCard(c)));
}

load();
