// ── Address autocomplete ──────────────────────────────────────────
function makeAutocomplete(inputEl) {
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

  function hide() { list.style.display = 'none'; activeIdx = -1; }

  function show(suggestions) {
    list.innerHTML = '';
    activeIdx = -1;
    if (!suggestions.length) { hide(); return; }
    suggestions.forEach(s => {
      const li = document.createElement('li');
      li.textContent = s.label;
      li.title = s.full;
      li.addEventListener('mousedown', e => {
        e.preventDefault();
        inputEl.value = s.label;
        hide();
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
      inputEl.value = items[activeIdx].textContent;
      hide(); return;
    } else if (e.key === 'Escape') {
      hide(); return;
    } else { return; }
    items.forEach((li, i) => li.classList.toggle('active', i === activeIdx));
  });

  document.addEventListener('click', e => { if (!wrapper.contains(e.target)) hide(); });
}

makeAutocomplete(document.getElementById('source-input'));
makeAutocomplete(document.getElementById('dest-input'));

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
function buildCard(route, type) {
  const card = document.createElement('div');
  card.className = `route-card route-card--${type}`;

  // Header
  const hdr = document.createElement('div');
  hdr.className = 'route-card__header';
  hdr.innerHTML = type === 'safe'
    ? `<span class="route-badge route-badge--safe">✓ Safe Walking Route</span>
       <span class="route-card__time">${Math.round(route.total_time)} min</span>`
    : `<span class="route-badge route-badge--unsafe">⚠ Unsafe Route</span>
       <span class="route-card__time">${Math.round(route.total_time)} min</span>`;
  card.appendChild(hdr);

  // Unsafe warning
  if (type === 'unsafe') {
    const w = document.createElement('div');
    w.className = 'route-card__warning';
    w.textContent = 'This route passes through marked danger zones!';
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

// ── Render results ────────────────────────────────────────────────
function renderResults(data) {
  routeCards.innerHTML = '';

  const { safe_route, unsafe_route } = data;

  if (!safe_route && unsafe_route) {
    const warn = document.createElement('div');
    warn.className = 'no-safe-warning';
    warn.innerHTML = '⚠ No safe route could be found. Only the unsafe route is available.';
    routeCards.appendChild(warn);
  }

  if (safe_route)   routeCards.appendChild(buildCard(safe_route,   'safe'));
  if (unsafe_route) routeCards.appendChild(buildCard(unsafe_route, 'unsafe'));

  resultsPanel.style.display = 'block';
}

// ── Form submit ───────────────────────────────────────────────────
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearError();

  const srcAddr = document.getElementById('source-input').value.trim();
  const dstAddr = document.getElementById('dest-input').value.trim();
  if (!srcAddr || !dstAddr) { showError('Please enter both a start and end address.'); return; }

  searchBtn.textContent = 'Searching…';
  searchBtn.disabled = true;
  resultsPanel.style.display = 'none';
  window.mapHelpers.drawRoute(null);

  try {
    const resp = await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_address: srcAddr, destination_address: dstAddr }),
    });
    const data = await resp.json();
    if (!resp.ok) { showError(data.error || 'No route found.'); return; }
    renderResults(data);
    window.mapHelpers.drawRoute(data);
  } catch {
    showError('Network error — is the server running?');
  } finally {
    searchBtn.textContent = 'Find Safe Route';
    searchBtn.disabled = false;
  }
});

// ── Danger zone list ──────────────────────────────────────────────
const dzList   = document.getElementById('danger-zones-list');
const csvUpload = document.getElementById('csv-upload');
const csvStatus = document.getElementById('csv-status');

async function refreshDangerList(zones) {
  if (!zones) zones = await (await fetch('/api/danger-zones')).json();
  dzList.innerHTML = '';
  if (!zones.length) { dzList.innerHTML = '<p class="hint">No danger zones marked yet.</p>'; return; }
  zones.forEach(z => {
    const div = document.createElement('div');
    div.className = 'dz-item';
    const detail = z.polygon && z.polygon.length >= 3
      ? `${z.polygon.length} boundary points`
      : `radius: ${z.radius_km} km`;
    div.innerHTML = `
      <div><div class="dz-name">${z.name}</div><div class="dz-info">${detail}</div></div>
      <button class="dz-remove" data-id="${z.id}" title="Remove">&#215;</button>`;
    dzList.appendChild(div);
  });
  dzList.querySelectorAll('.dz-remove').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch(`/api/danger-zones/${btn.dataset.id}`, { method: 'DELETE' });
      const updated = await (await fetch('/api/danger-zones')).json();
      window.mapHelpers.drawDangerZones(updated);
      refreshDangerList(updated);
    });
  });
}

csvUpload.addEventListener('change', async () => {
  const file = csvUpload.files[0];
  if (!file) return;
  csvStatus.className = '';
  csvStatus.textContent = 'Importing…';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const resp = await fetch('/api/danger-zones/import', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      csvStatus.className = 'err';
      csvStatus.textContent = data.error || 'Import failed.';
    } else {
      csvStatus.className = 'ok';
      csvStatus.textContent = `Imported ${data.imported} zone${data.imported !== 1 ? 's' : ''}.`;
      window.mapHelpers.drawDangerZones(data.zones);
      refreshDangerList(data.zones);
    }
  } catch {
    csvStatus.className = 'err';
    csvStatus.textContent = 'Upload error.';
  }
  csvUpload.value = '';
});

window.refreshDangerList = refreshDangerList;

// ── Init ──────────────────────────────────────────────────────────
(async () => {
  const zones = await (await fetch('/api/danger-zones')).json();
  window.mapHelpers.drawDangerZones(zones);
  refreshDangerList(zones);
})();
