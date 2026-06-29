// MTA line colors (matches CSS)
const LINE_COLORS = {
  '1':'#EE352E','2':'#EE352E','3':'#EE352E',
  '4':'#00933C','5':'#00933C','6':'#6CBE45',
  '7':'#B933AD',
  'A':'#2850AD','C':'#2850AD','E':'#2850AD',
  'B':'#FF6319','D':'#FF6319','F':'#FF6319','M':'#FF6319',
  'G':'#6CBE45',
  'J':'#996633','Z':'#996633',
  'L':'#A7A9AC',
  'N':'#FCCC0A','Q':'#FCCC0A','R':'#FCCC0A','W':'#FCCC0A',
  'S':'#808183',
  'walk':'#6b7280',
};

const map = L.map('map').setView([40.73, -73.97], 12);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

// Layers
const stopLayer     = L.layerGroup().addTo(map);
const dangerLayer   = L.layerGroup().addTo(map);
const routeLayer    = L.layerGroup().addTo(map);

// ── Draw all stops ──────────────────────────────────────────────
function drawStops(stops) {
  stopLayer.clearLayers();
  stops.forEach(s => {
    L.circleMarker([s.lat, s.lng], {
      radius: 4,
      color: '#003883',
      fillColor: '#fff',
      fillOpacity: 1,
      weight: 1.5,
    }).bindTooltip(s.name, { direction: 'top', offset: [0, -4] })
      .addTo(stopLayer);
  });
}

// ── Draw danger zones ───────────────────────────────────────────
function drawDangerZones(zones) {
  dangerLayer.clearLayers();
  zones.forEach(z => {
    L.circle([z.lat, z.lng], {
      radius: z.radius_km * 1000,
      color: '#ef4444',
      fillColor: '#ef4444',
      fillOpacity: 0.18,
      weight: 2,
    }).bindPopup(`<b>${z.name}</b><br>radius: ${z.radius_km} km`)
      .addTo(dangerLayer);
  });
}

// ── Draw route ──────────────────────────────────────────────────
function drawRoute(result) {
  routeLayer.clearLayers();
  if (!result || !result.coords.length) return;

  const latlngs = result.coords.map(c => [c.lat, c.lng]);

  // Polyline — colour by first line used
  const firstLine = result.steps.length ? result.steps[0].line : 'S';
  L.polyline(latlngs, {
    color: LINE_COLORS[firstLine] || '#003883',
    weight: 5,
    opacity: 0.85,
  }).addTo(routeLayer);

  // Markers for each stop in the path
  result.coords.forEach((c, i) => {
    const isEndpoint = i === 0 || i === result.coords.length - 1;
    L.circleMarker([c.lat, c.lng], {
      radius: isEndpoint ? 8 : 5,
      color: isEndpoint ? '#003883' : '#6b7280',
      fillColor: isEndpoint ? '#003883' : '#e5e7eb',
      fillOpacity: 1,
      weight: 2,
    }).bindTooltip(c.name, { direction: 'top', offset: [0, -4] })
      .addTo(routeLayer);
  });

  // Fit map to route
  map.fitBounds(L.latLngBounds(latlngs), { padding: [40, 40] });
}

// ── Click to add danger zone ────────────────────────────────────
map.on('click', async (e) => {
  const name = prompt('Name this danger zone (or cancel to skip):');
  if (!name) return;

  const radius_km = parseFloat(prompt('Radius in km (e.g. 0.5):', '0.5')) || 0.5;

  const resp = await fetch('/api/danger-zones', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, lat: e.latlng.lat, lng: e.latlng.lng, radius_km }),
  });

  if (resp.ok) {
    const zones = await (await fetch('/api/danger-zones')).json();
    drawDangerZones(zones);
    window.refreshDangerList && window.refreshDangerList(zones);
  }
});

// Expose helpers to app.js
window.mapHelpers = { drawRoute, drawDangerZones, drawStops };
