// ── Data-view case toggle ─────────────────────────────────────────
let activeCase = 'nypd';   // 'nypd' | 'reviews' — scopes both the map layer and route search

document.querySelectorAll('.case-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.case-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCase = btn.dataset.case;
    window.mapHelpers.setActiveCase(activeCase);
  });
});

// ── Address autocomplete ──────────────────────────────────────────
function makeAutocomplete(inputEl, onSelect) {
  const wrapper = document.createElement('div');
  wrapper.className = 'autocomplete-wrapper';
  inputEl.parentNode.insertBefore(wrapper, inputEl);
  wrapper.appendChild(inputEl);

  const list = document.createElement('ul');
  list.className = 'autocomplete-list';
  list.style.display = 'none';
  wrapper.appendChild(list);

  let activeIdx = -1;
  let timer = null;
  let suggestions = [];

  function hide() { list.style.display = 'none'; activeIdx = -1; }

  function choose(s) {
    inputEl.value = s.label;
    hide();
    if (onSelect) onSelect(s);
  }

  function show(items) {
    suggestions = items;
    list.innerHTML = '';
    activeIdx = -1;
    if (!items.length) { hide(); return; }
    items.forEach(s => {
      const li = document.createElement('li');
      li.textContent = s.label;
      li.title = s.full;
      li.addEventListener('mousedown', e => {
        e.preventDefault();
        choose(s);
      });
      list.appendChild(li);
    });
    list.style.display = 'block';
  }

  inputEl.addEventListener('input', () => {
    clearTimeout(timer);
    const q = inputEl.value.trim();
    if (q.length < 3) { hide(); return; }
    timer = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/autocomplete?q=${encodeURIComponent(q)}`);
        show(await resp.json());
      } catch { hide(); }
    }, 350);
  });

  inputEl.addEventListener('keydown', e => {
    const items = list.querySelectorAll('li');
    if (!items.length || list.style.display === 'none') return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      choose(suggestions[activeIdx]);
      return;
    } else if (e.key === 'Escape') {
      hide(); return;
    } else { return; }
    items.forEach((li, i) => li.classList.toggle('active', i === activeIdx));
  });

  document.addEventListener('click', e => { if (!wrapper.contains(e.target)) hide(); });
}

makeAutocomplete(document.getElementById('source-input'), s => {
  window.mapHelpers.setPreviewMarker('source', s.lat, s.lng, 'Start');
});
makeAutocomplete(document.getElementById('dest-input'), s => {
  window.mapHelpers.setPreviewMarker('dest', s.lat, s.lng, 'Destination');
});

// ── Step icon helper ──────────────────────────────────────────────
function stepIcon(instruction) {
  const t = instruction.toLowerCase();
  if (t.startsWith('head') || t.startsWith('depart')) return '↑';
  if (t.includes('u-turn'))        return '↩';
  if (t.includes('sharp left'))    return '↰';
  if (t.includes('sharp right'))   return '↱';
  if (t.includes('turn left') || t.includes('keep left'))  return '←';
  if (t.includes('turn right') || t.includes('keep right')) return '→';
  if (t.includes('arrive'))        return '📍';
  if (t.includes('roundabout'))    return '↻';
  return '↑';
}

// ── DOM refs ──────────────────────────────────────────────────────
const form         = document.getElementById('route-form');
const formError    = document.getElementById('form-error');
const resultsPanel = document.getElementById('results-panel');
const routeCards   = document.getElementById('route-cards');
const searchBtn    = document.getElementById('search-btn');

function showError(msg) { formError.textContent = msg; formError.style.display = 'block'; }
function clearError()   { formError.style.display = 'none'; }

// ── Build one route card ──────────────────────────────────────────
const ROUTE_LABELS = {
  green: { badge: '✓ Green Route — Avoids Flagged Zones' },
  red:   { badge: '⚠ Red Route — Absolute Shortest' },
  only:  { badge: '➜ Only Route Available' },
};

function buildCard(route, type) {
  const card = document.createElement('div');
  card.className = `route-card route-card--${type}`;

  // Header
  const hdr = document.createElement('div');
  hdr.className = 'route-card__header';
  hdr.innerHTML = `
    <span class="route-badge route-badge--${type}">${ROUTE_LABELS[type].badge}</span>
    <span class="route-card__time">${Math.round(route.total_time)} min</span>`;
  card.appendChild(hdr);

  if (type === 'red') {
    const w = document.createElement('div');
    w.className = 'route-card__warning';
    const source = activeCase === 'reviews' ? 'tourist-review warning' : 'NYPD danger';
    w.textContent = `This route may pass through marked ${source} zones!`;
    card.appendChild(w);
  }

  if (type === 'only' && route.coords.some(c => c.unsafe)) {
    const w = document.createElement('div');
    w.className = 'route-card__warning';
    w.textContent = 'The stretch right by your start/end point (shown in red on the map) sits inside a flagged zone and can\'t be avoided — the rest of this route avoids all others.';
    card.appendChild(w);
  }

  // Summary line
  const summary = document.createElement('div');
  summary.className = 'route-summary';
  summary.textContent = `${route.distance_km} km · ~${Math.round(route.total_time)} min walking`;
  card.appendChild(summary);

  // Turn-by-turn steps
  if (route.steps && route.steps.length) {
    const ol = document.createElement('ol');
    ol.className = 'route-steps';
    route.steps.forEach(s => {
      const li = document.createElement('li');
      const distText = s.distance_m >= 1000
        ? `${(s.distance_m / 1000).toFixed(1)} km`
        : s.distance_m > 0 ? `${s.distance_m} m` : '';
      li.innerHTML = `
        <div class="step-badge line-walk">${stepIcon(s.instruction)}</div>
        <div class="step-text">
          ${s.instruction}${distText ? `<span class="step-dist"> — ${distText}</span>` : ''}
        </div>`;
      ol.appendChild(li);
    });
    card.appendChild(ol);
  }

  return card;
}

// Same physical path either way (walking distance/time aside, every
// coordinate lines up) — happens when the shortest path already avoids
// every avoidable zone, so there's no real green-vs-red choice to show.
function sameRoute(a, b) {
  if (!a || !b || a.coords.length !== b.coords.length) return false;
  return a.coords.every((c, i) => c.lat === b.coords[i].lat && c.lng === b.coords[i].lng);
}

// ── Render results ────────────────────────────────────────────────
function renderResults(data) {
  routeCards.innerHTML = '';

  const { green_route, red_route } = data;

  if (!green_route) {
    const warn = document.createElement('div');
    warn.className = 'no-green-warning';
    const zoneKind = activeCase === 'reviews' ? 'review-flagged' : 'danger';
    warn.innerHTML = `⚠ No route avoiding all ${zoneKind} zones was found. Showing the shortest route instead.`;
    routeCards.appendChild(warn);
    if (red_route) routeCards.appendChild(buildCard(red_route, 'red'));
  } else if (sameRoute(green_route, red_route)) {
    routeCards.appendChild(buildCard(green_route, 'only'));
  } else {
    routeCards.appendChild(buildCard(green_route, 'green'));
    routeCards.appendChild(buildCard(red_route,   'red'));
  }

  resultsPanel.style.display = 'block';
}

// ── Shared route search (used by the form and by map click-picking) ──
async function performSearch(payload) {
  clearError();
  searchBtn.textContent = 'Searching…';
  searchBtn.disabled = true;
  resultsPanel.style.display = 'none';
  window.mapHelpers.drawRoute(null);

  try {
    const resp = await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) { showError(data.error || 'No route found.'); return; }
    renderResults(data);
    window.mapHelpers.drawRoute(data);
  } catch {
    showError('Network error — is the server running?');
  } finally {
    searchBtn.textContent = 'Find Safe Walking Route';
    searchBtn.disabled = false;
  }
}

// ── Form submit ───────────────────────────────────────────────────
form.addEventListener('submit', (e) => {
  e.preventDefault();
  clearError();

  const srcAddr = document.getElementById('source-input').value.trim();
  const dstAddr = document.getElementById('dest-input').value.trim();
  if (!srcAddr || !dstAddr) { showError('Please enter both a start and end address.'); return; }

  performSearch({ source_address: srcAddr, destination_address: dstAddr, case: activeCase });
});

// ── Map click-to-pick source/destination ──────────────────────────
// Called by map.js once the user has clicked two points on the map.
window.searchByCoords = (source, dest) => {
  document.getElementById('source-input').value = `Pinned (${source.lat.toFixed(5)}, ${source.lng.toFixed(5)})`;
  document.getElementById('dest-input').value = `Pinned (${dest.lat.toFixed(5)}, ${dest.lng.toFixed(5)})`;
  performSearch({
    source_lat: source.lat, source_lng: source.lng,
    dest_lat: dest.lat, dest_lng: dest.lng,
    case: activeCase,
  });
};

// ── Init ──────────────────────────────────────────────────────────
(async () => {
  const zones = await (await fetch('/api/danger-zones')).json();
  window.mapHelpers.drawDangerZones(zones);

  const riskPoints = await (await fetch('/api/review-risk-points')).json();
  window.mapHelpers.drawReviewRiskPoints(riskPoints);

  const warningZones = await (await fetch('/api/warning-zones')).json();
  window.mapHelpers.drawWarningZones(warningZones);
})();
