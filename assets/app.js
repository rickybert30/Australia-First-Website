'use strict';

const POSITION_LABELS = {
  immigration: 'Immigration',
  faith: 'Faith & religion',
  economic_nationalism: 'Economic nationalism',
  foreign_policy: 'Foreign policy & aid',
  citizenship_eligibility: 'Citizenship (s44 eligibility)',
};

const state = {
  all: [],
  filters: { search: '', chamber: '', party: '', state: '', status: '' },
};

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
  populatePartyFilter();
  wireControls();
  render();
}

function populatePartyFilter() {
  const sel = document.getElementById('filter-party');
  const parties = [...new Set(state.all.map((c) => c.party).filter(Boolean))].sort();
  parties.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  });
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
  bind('filter-chamber', 'chamber');
  bind('filter-party', 'party');
  bind('filter-state', 'state');
  bind('filter-status', 'status');
}

function matches(c) {
  const f = state.filters;
  if (f.chamber && c.chamber !== f.chamber) return false;
  if (f.party && c.party !== f.party) return false;
  if (f.state && c.state !== f.state) return false;
  if (f.status && c.status !== f.status) return false;
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

function renderPosition(key, pos) {
  const wrap = el('div', 'pos');
  const label = el('div', 'pos-label');
  label.appendChild(el('span', null, POSITION_LABELS[key] || key));
  const verified = pos.verified && pos.sources && pos.sources.length > 0;
  label.appendChild(el('span', `badge ${verified ? 'ok' : 'warn'}`, verified ? 'verified' : 'unverified'));
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
      tr.appendChild(el('td', null, d.donor || '—'));
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
  const metaBits = [
    c.party,
    c.chamber,
    c.electorate ? `${c.electorate} (${c.state || ''})` : c.state,
    c.status,
  ].filter(Boolean);
  const meta = node.querySelector('.c-meta');
  meta.textContent = metaBits.join(' · ');
  if (c.roster_source && c.roster_source.url) {
    meta.appendChild(document.createTextNode(' · '));
    const a = document.createElement('a');
    a.className = 'roster-src';
    a.href = c.roster_source.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = 'roster source';
    a.title = c.roster_source.title || '';
    meta.appendChild(a);
  }

  const dl = node.querySelector('.positions');
  const positions = c.positions || {};
  Object.keys(POSITION_LABELS).forEach((key) => {
    if (positions[key]) dl.appendChild(renderPosition(key, positions[key]));
  });
  if (c.donors) dl.appendChild(renderDonors(c.donors));
  return node;
}

function render() {
  const results = document.getElementById('results');
  const countEl = document.getElementById('count');
  results.innerHTML = '';
  const filtered = state.all.filter(matches);
  countEl.textContent = `${filtered.length} of ${state.all.length} record(s)`;
  if (filtered.length === 0) {
    results.innerHTML = '<p class="empty">No candidates match these filters.</p>';
    return;
  }
  filtered.forEach((c) => results.appendChild(renderCard(c)));
}

load();
