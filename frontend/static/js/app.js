const stops = window.STOPS;  // injected by Flask template
const stopsByName = {};
stops.forEach(s => { stopsByName[s.name] = s; });

// ── Autocomplete ─────────────────────────────────────────────────
function makeAutocomplete(inputEl, hiddenEl) {
  const wrapper = document.createElement('div');
  wrapper.className = 'autocomplete-wrapper';
  inputEl.parentNode.insertBefore(wrapper, inputEl);
  wrapper.appendChild(inputEl);

  const list = document.createElement('ul');
  list.className = 'autocomplete-list';
  list.style.display = 'none';
  wrapper.appendChild(list);

  let activeIdx = -1;

  function show(matches) {
    list.innerHTML = '';
    activeIdx = -1;
    if (!matches.length) { list.style.display = 'none'; return; }
    matches.forEach((s, i) => {
      const li = document.createElement('li');
      li.textContent = s.name;
      li.addEventListener('mousedown', () => pick(s));
      list.appendChild(li);
    });
    list.style.display = 'block';
  }

  function pick(s) {
    inputEl.value = s.name;
    hiddenEl.value = s.id;
    list.style.display = 'none';
  }

  inputEl.addEventListener('input', () => {
    hiddenEl.value = '';
    const q = inputEl.value.toLowerCase();
    if (!q) { list.style.display = 'none'; return; }
    const matches = stops.filter(s => s.name.toLowerCase().includes(q)).slice(0, 8);
    show(matches);
  });

  inputEl.addEventListener('keydown', (e) => {
    const items = list.querySelectorAll('li');
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
      activeIdx = Math.max(activeIdx - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0) pick(stops.find(s => s.name === items[activeIdx].textContent));
      return;
    } else { return; }
    items.forEach((li, i) => li.classList.toggle('active', i === activeIdx));
  });

  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) list.style.display = 'none';
  });
}

makeAutocomplete(document.getElementById('source-input'), document.getElementById('source-id'));
makeAutocomplete(document.getElementById('dest-input'),   document.getElementById('dest-id'));

// ── Route form ───────────────────────────────────────────────────
const form       = document.getElementById('route-form');
const formError  = document.getElementById('form-error');
const resultsPanel = document.getElementById('results-panel');
const routeTime  = document.getElementById('route-time');
const routeSteps = document.getElementById('route-steps');

function showError(msg) {
  formError.textContent = msg;
  formError.style.display = 'block';
}
function clearError() { formError.style.display = 'none'; }

function lineLabel(line) {
  return line === 'walk' ? '🚶' : line;
}

function renderSteps(steps) {
  routeSteps.innerHTML = '';
  steps.forEach(step => {
    const li = document.createElement('li');
    const cls = `line-${step.line}`;
    li.innerHTML = `
      <div class="step-badge ${cls}">${lineLabel(step.line)}</div>
      <div class="step-text">
        ${step.line === 'walk'
          ? `Walk from <b>${step.from.name}</b> to <b>${step.to.name}</b>`
          : `Take the <b>${step.line}</b> from <b>${step.from.name}</b> to <b>${step.to.name}</b>`
        }
      </div>`;
    routeSteps.appendChild(li);
  });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearError();

  const sourceId = document.getElementById('source-id').value;
  const destId   = document.getElementById('dest-id').value;

  if (!sourceId) { showError('Please select a valid start station from the list.'); return; }
  if (!destId)   { showError('Please select a valid end station from the list.'); return; }
  if (sourceId === destId) { showError('Start and end stations must be different.'); return; }

  const resp = await fetch('/api/routes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: sourceId, destination: destId }),
  });

  const data = await resp.json();

  if (!resp.ok) {
    showError(data.error || 'No route found.');
    resultsPanel.style.display = 'none';
    window.mapHelpers.drawRoute(null);
    return;
  }

  routeTime.textContent = `Estimated travel time: ${data.total_time} min`;
  renderSteps(data.steps);
  resultsPanel.style.display = 'block';
  window.mapHelpers.drawRoute(data);
});

// ── Danger zones list ─────────────────────────────────────────────
const dzList = document.getElementById('danger-zones-list');

async function refreshDangerList(zones) {
  if (!zones) {
    const resp = await fetch('/api/danger-zones');
    zones = await resp.json();
  }
  dzList.innerHTML = '';
  if (!zones.length) {
    dzList.innerHTML = '<p class="hint">No danger zones marked yet.</p>';
    return;
  }
  zones.forEach(z => {
    const div = document.createElement('div');
    div.className = 'dz-item';
    div.innerHTML = `
      <div>
        <div class="dz-name">${z.name}</div>
        <div class="dz-info">radius: ${z.radius_km} km</div>
      </div>
      <button class="dz-remove" data-id="${z.id}" title="Remove">×</button>`;
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

// Expose for map.js click handler
window.refreshDangerList = refreshDangerList;

// ── Init ──────────────────────────────────────────────────────────
(async () => {
  window.mapHelpers.drawStops(stops);
  const zones = await (await fetch('/api/danger-zones')).json();
  window.mapHelpers.drawDangerZones(zones);
  refreshDangerList(zones);
})();
