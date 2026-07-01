// In-browser SQL explorer. Loads the published SQLite database with sql.js
// (WASM) and runs read-only queries entirely client-side — no server.

const EXAMPLES = [
  {
    label: 'Top donors (spellings rolled up)',
    sql: `-- Largest donors to parties, with spelling variants merged via canonical_id
SELECT COALESCE(d.canonical_id, d.name) AS entity,
       printf('$%,d', SUM(pd.amount_aud)) AS total_to_parties,
       COUNT(DISTINCT pd.party)          AS parties
FROM party_donation pd
JOIN donor d ON d.name = pd.donor_name
GROUP BY entity
ORDER BY SUM(pd.amount_aud) DESC
LIMIT 25;`,
  },
  {
    label: 'Cross-party donors + who they are',
    sql: `-- Donors that gave to more than one party, with their description
SELECT COALESCE(d.canonical_id, d.name) AS entity,
       COUNT(DISTINCT pd.party)         AS parties,
       printf('$%,d', SUM(pd.amount_aud)) AS total,
       di.category, di.description
FROM party_donation pd
JOIN donor d ON d.name = pd.donor_name
LEFT JOIN donor_info di ON di.donor_name = COALESCE(d.canonical_id, d.name)
GROUP BY entity
HAVING parties > 1
ORDER BY SUM(pd.amount_aud) DESC
LIMIT 30;`,
  },
  {
    label: 'Spelling variants found',
    sql: `-- Entities the AEC disclosed under several spellings
SELECT canonical_id AS entity, COUNT(*) + 1 AS spellings,
       GROUP_CONCAT(name, '  |  ') AS variants
FROM donor
WHERE canonical_id IS NOT NULL
GROUP BY canonical_id
ORDER BY spellings DESC, entity;`,
  },
  {
    label: 'Positions by issue × jurisdiction',
    sql: `-- How many sourced positions we hold, by issue and parliament
SELECT p.issue, c.jurisdiction, COUNT(*) AS n
FROM position p
JOIN candidate c ON c.id = p.candidate_id
GROUP BY p.issue, c.jurisdiction
ORDER BY p.issue, n DESC;`,
  },
  {
    label: 'Faith positions by party group',
    sql: `SELECT c.party_group, COUNT(*) AS n
FROM position p
JOIN candidate c ON c.id = p.candidate_id
WHERE p.issue = 'faith'
GROUP BY c.party_group
ORDER BY n DESC;`,
  },
  {
    label: "One member's disclosed donors",
    sql: `-- Donations disclosed directly to a member (edit the name)
SELECT c.name AS member, md.donor_name,
       printf('$%,.0f', md.amount_aud) AS amount, md.financial_year
FROM member_donation md
JOIN candidate c ON c.id = md.candidate_id
WHERE c.name LIKE '%Spender%'
ORDER BY md.amount_aud DESC;`,
  },
];

const $ = (id) => document.getElementById(id);
let db = null;

function renderExamples() {
  const box = $('examples');
  EXAMPLES.forEach((ex) => {
    const b = document.createElement('button');
    b.textContent = ex.label;
    b.addEventListener('click', () => { $('sql').value = ex.sql; run(); });
    box.appendChild(b);
  });
}

function showError(msg) {
  const e = $('error');
  e.hidden = false;
  e.textContent = msg;
  $('results').innerHTML = '';
  $('count').textContent = '';
}

const NUM = /^-?\d+(\.\d+)?$/;

function run() {
  if (!db) return;
  $('error').hidden = true;
  const sql = $('sql').value.trim();
  if (!sql) return;
  let res;
  try {
    res = db.exec(sql);
  } catch (err) {
    showError(String(err.message || err));
    return;
  }
  const results = $('results');
  results.innerHTML = '';
  if (!res.length) {
    $('count').textContent = 'No rows returned.';
    return;
  }
  const { columns, values } = res[0];
  const table = document.createElement('table');
  table.className = 'sqlout';
  const thead = document.createElement('thead');
  const htr = document.createElement('tr');
  columns.forEach((col) => {
    const th = document.createElement('th');
    th.textContent = col;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  values.forEach((row) => {
    const tr = document.createElement('tr');
    row.forEach((val) => {
      const td = document.createElement('td');
      const s = val === null ? '' : String(val);
      if (typeof val === 'number' || (NUM.test(s) && s.length < 16)) td.className = 'num';
      td.textContent = s;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  results.appendChild(table);
  $('count').textContent = `${values.length} row${values.length === 1 ? '' : 's'}.`;
}

async function boot() {
  renderExamples();
  $('sql').value = EXAMPLES[0].sql;
  try {
    const SQL = await initSqlJs({ locateFile: (f) => `assets/vendor/sqljs/${f}` });
    const buf = await fetch('data/candidates.db').then((r) => {
      if (!r.ok) throw new Error(`could not load database (${r.status})`);
      return r.arrayBuffer();
    });
    db = new SQL.Database(new Uint8Array(buf));
    $('status').textContent = 'Ready — read-only. Try an example or write your own.';
    $('run').disabled = false;
    $('run').addEventListener('click', run);
    $('sql').addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    });
    run();
  } catch (err) {
    $('status').textContent = '';
    showError('Failed to load the database: ' + (err.message || err) +
      '\n\nThe SQL explorer needs data/candidates.db, which is generated at deploy time.');
    $('run').disabled = true;
  }
}

boot();
