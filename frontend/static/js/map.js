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
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

// Only one "case" is shown at a time: NYPD (danger zones) by default, or
// Tourist Review (warning zones + flagged points) — see setActiveCase().
const dangerLayer     = L.layerGroup().addTo(map);
const warningLayer    = L.layerGroup();
const routeLayer      = L.layerGroup().addTo(map);
const previewLayer    = L.layerGroup().addTo(map);
const reviewRiskLayer = L.layerGroup();

function setActiveCase(caseName) {
  if (caseName === 'reviews') {
    map.removeLayer(dangerLayer);
    map.addLayer(warningLayer);
    map.addLayer(reviewRiskLayer);
  } else {
    map.removeLayer(warningLayer);
    map.removeLayer(reviewRiskLayer);
    map.addLayer(dangerLayer);
  }
}

// ── Danger zones ─────────────────────────────────────────────────
function drawDangerZones(zones) {
  dangerLayer.clearLayers();
  zones.forEach(z => {
    if (z.polygon && z.polygon.length >= 3) {
      // Polygon zone (imported from CSV boundary points)
      L.polygon(z.polygon, {
        color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.2, weight: 2,
      }).bindPopup(`<b>${z.name}</b>`).addTo(dangerLayer);
    } else {
      // Circle zone (manually added via map click)
      L.circle([z.lat, z.lng], {
        radius: z.radius_km * 1000,
        color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.18, weight: 2,
      }).bindPopup(`<b>${z.name}</b><br>radius: ${z.radius_km} km`)
        .addTo(dangerLayer);
    }
  });
}

// ── Warning zones (review-based, buffer-and-dissolve around flagged hotels) ──
function drawWarningZones(zones) {
  warningLayer.clearLayers();
  zones.forEach(z => {
    if (z.polygon && z.polygon.length >= 3) {
      L.polygon(z.polygon, {
        color: '#eab308', fillColor: '#eab308', fillOpacity: 0.25, weight: 2,
      }).bindPopup(`<b>${z.name}</b>`).addTo(warningLayer);
    } else {
      L.circle([z.lat, z.lng], {
        radius: z.radius_km * 1000,
        color: '#eab308', fillColor: '#eab308', fillOpacity: 0.2, weight: 2,
      }).bindPopup(`<b>${z.name}</b><br>radius: ${z.radius_km} km`)
        .addTo(warningLayer);
    }
  });
}

// ── Hotels flagged in reviews for tourist safety concerns ──────────
// (text-mining output: points only, no per-hotel names/details)
function drawReviewRiskPoints(points) {
  reviewRiskLayer.clearLayers();
  points.forEach(p => {
    L.circleMarker([p.lat, p.lng], {
      radius: 5,
      color: '#9333ea',
      fillColor: '#9333ea',
      fillOpacity: 0.6,
      weight: 1,
    }).bindPopup('Hotel flagged in reviews for tourist safety concerns')
      .addTo(reviewRiskLayer);
  });
}

// ── Address pin ───────────────────────────────────────────────────
function addressMarker(lat, lng, color, label) {
  const icon = L.divIcon({
    className: '',
    html: `<div style="background:${color};width:16px;height:16px;border-radius:50%;
                       border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.45)"></div>`,
    iconSize: [16, 16], iconAnchor: [8, 8],
  });
  return L.marker([lat, lng], { icon })
          .bindTooltip(label, { direction: 'top', offset: [0, -10] });
}

// ── Draw one route polyline ───────────────────────────────────────
function drawPolyline(coords, color, dashed) {
  if (!coords || coords.length < 2) return;
  const latlngs = coords.map(c => [c.lat, c.lng]);
  L.polyline(latlngs, {
    color,
    weight: 5,
    opacity: 0.85,
    dashArray: dashed ? '10 7' : null,
  }).addTo(routeLayer);
}

// ── Source/destination preview pins ────────────────────────────────
// Shown as soon as the user picks an address, before a route is searched.
const previewMarkers = { source: null, dest: null };

function setPreviewMarker(type, lat, lng, label) {
  if (previewMarkers[type]) previewLayer.removeLayer(previewMarkers[type]);
  const color = type === 'source' ? '#22c55e' : '#ef4444';
  const marker = addressMarker(lat, lng, color, label).addTo(previewLayer);
  previewMarkers[type] = marker;
  marker.openTooltip();

  const pts = Object.values(previewMarkers).filter(Boolean).map(m => m.getLatLng());
  if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [80, 80] });
  else map.setView([lat, lng], 15);
}

function clearPreviewMarker(type) {
  if (previewMarkers[type]) {
    previewLayer.removeLayer(previewMarkers[type]);
    previewMarkers[type] = null;
  }
}

// ── Main drawRoute ────────────────────────────────────────────────
function drawRoute(result) {
  routeLayer.clearLayers();
  previewLayer.clearLayers();
  previewMarkers.source = null;
  previewMarkers.dest = null;
  if (!result) return;

  const { green_route, red_route, source_geo, dest_geo } = result;

  // Address markers
  if (source_geo)
    addressMarker(source_geo.lat, source_geo.lng, '#22c55e', 'Start').addTo(routeLayer);
  if (dest_geo)
    addressMarker(dest_geo.lat, dest_geo.lng, '#ef4444', 'Destination').addTo(routeLayer);

  // Red drawn first (underneath), green on top
  if (red_route)   drawPolyline(red_route.coords,   '#ef4444', true);
  if (green_route) drawPolyline(green_route.coords, '#16a34a', false);

  // Fit map to all route points
  const pts = [];
  if (source_geo) pts.push([source_geo.lat, source_geo.lng]);
  if (dest_geo)   pts.push([dest_geo.lat,   dest_geo.lng]);
  [green_route, red_route].forEach(r => {
    if (r) r.coords.forEach(c => pts.push([c.lat, c.lng]));
  });
  if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [50, 50] });
}

// ── Click → danger zone ───────────────────────────────────────────
map.on('click', async (e) => {
  const name = prompt('Name this danger zone (or Cancel to skip):');
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

window.mapHelpers = { drawRoute, drawDangerZones, drawWarningZones, setPreviewMarker, clearPreviewMarker, drawReviewRiskPoints, setActiveCase };
