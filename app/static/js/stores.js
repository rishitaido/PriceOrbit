// stores.js — Ticket #41: Store Map Display
// Fetches stores from GET /api/stores, renders Leaflet map + sidebar list

const STORES_API = "/api/stores";
const NEARBY_API = "/api/stores/nearby";

// ─── STATE ────────────────────────────────────────────────────────────────────
let map = null;
let markersMap = {};     // store.id → L.marker
let allStores = [];
let activeStoreId = null;

// ─── MOCK FALLBACK (used when backend is not running) ─────────────────────────
const MOCK_STORES = [
  { id: 1, name: "Kroger Marketplace", address: "4880 Lower Roswell Rd",     city: "Marietta",      state: "GA", zip_code: "30068", latitude: 33.9526, longitude: -84.4477, phone: "(770) 565-5530", hours: "6am–11pm" },
  { id: 2, name: "Kroger",             address: "11695 Haynes Bridge Rd",    city: "Alpharetta",    state: "GA", zip_code: "30009", latitude: 34.0798, longitude: -84.2749, phone: "(770) 740-9564", hours: "6am–12am" },
  { id: 3, name: "Kroger",             address: "2685 Peachtree Rd NE",      city: "Atlanta",       state: "GA", zip_code: "30305", latitude: 33.8340, longitude: -84.3680, phone: "(404) 816-4100", hours: "6am–11pm" },
  { id: 4, name: "Kroger",             address: "5600 Roswell Rd NE",        city: "Sandy Springs", state: "GA", zip_code: "30342", latitude: 33.9030, longitude: -84.3742, phone: "(404) 252-2650", hours: "6am–11pm" },
  { id: 5, name: "Kroger",             address: "3330 Piedmont Rd NE",       city: "Atlanta",       state: "GA", zip_code: "30305", latitude: 33.8468, longitude: -84.3618, phone: "(404) 261-3550", hours: "7am–11pm" },
  { id: 6, name: "Kroger Marketplace", address: "2250 Ernest W Barrett Pkwy", city: "Kennesaw",    state: "GA", zip_code: "30144", latitude: 34.0219, longitude: -84.5985, phone: "(770) 499-9500", hours: "6am–12am" },
  { id: 7, name: "Kroger",             address: "1100 Cobb Pkwy SE",         city: "Marietta",      state: "GA", zip_code: "30060", latitude: 33.9274, longitude: -84.5219, phone: "(770) 428-2831", hours: "6am–11pm" },
  { id: 8, name: "Kroger",             address: "6000 Medlock Bridge Pkwy",  city: "Johns Creek",   state: "GA", zip_code: "30022", latitude: 34.0187, longitude: -84.1998, phone: "(770) 813-9015", hours: "6am–11pm" },
];

// ─── MAP INIT ─────────────────────────────────────────────────────────────────
function initMap() {
  map = L.map("map", { zoomControl: false }).setView([33.9526, -84.3533], 11);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  L.control.zoom({ position: "bottomright" }).addTo(map);
}

// ─── CUSTOM ICONS ─────────────────────────────────────────────────────────────
function makeIcon(selected = false) {
  const color = selected ? "#f59e0b" : "#5dd1ab";
  const shadow = selected ? "rgba(245,158,11,0.4)" : "rgba(93,209,171,0.4)";
  return L.divIcon({
    className: "",
    html: `<div style="
      width:28px; height:28px;
      background:${color};
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      border:2px solid white;
      box-shadow:0 3px 10px ${shadow};
    "></div>`,
    iconSize:    [28, 28],
    iconAnchor:  [14, 28],
    popupAnchor: [0, -32],
  });
}

// ─── POPUP CONTENT ────────────────────────────────────────────────────────────
function buildPopupHTML(store) {
  const mapsUrl = buildGoogleMapsUrl(store);
  return `
    <div class="store-popup">
      <div class="store-popup-name">
        <i class="fa-solid fa-store"></i> ${store.name}
      </div>
      <div class="store-popup-row">
        <i class="fa-solid fa-location-dot"></i>
        <span>${store.address}, ${store.city}, ${store.state} ${store.zip_code}</span>
      </div>
      ${store.phone ? `
      <div class="store-popup-row">
        <i class="fa-solid fa-phone"></i>
        <span>${store.phone}</span>
      </div>` : ""}
      ${store.hours ? `
      <div class="store-popup-row">
        <i class="fa-solid fa-clock"></i>
        <span>${store.hours}</span>
      </div>` : ""}
      <a class="store-popup-btn" href="${mapsUrl}" target="_blank" rel="noopener noreferrer">
        <i class="fa-solid fa-diamond-turn-right"></i> Open in Google Maps
      </a>
    </div>
  `;
}

function buildGoogleMapsUrl(store) {
  const address = [store.address, store.city, store.state, store.zip_code]
    .filter(Boolean)
    .join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}

// ─── MARKER MANAGEMENT ────────────────────────────────────────────────────────
function addMarkers(stores) {
  stores.forEach((store) => {
    const marker = L.marker([store.latitude, store.longitude], {
      icon: makeIcon(false),
    })
      .addTo(map)
      .bindPopup(buildPopupHTML(store), { maxWidth: 260 });

    marker.on("click", () => selectStore(store.id));
    markersMap[store.id] = marker;
  });
}

function clearMarkers() {
  Object.values(markersMap).forEach((m) => map.removeLayer(m));
  markersMap = {};
}

// ─── SELECT A STORE ───────────────────────────────────────────────────────────
function selectStore(id) {
  // Deselect previous
  if (activeStoreId && markersMap[activeStoreId]) {
    markersMap[activeStoreId].setIcon(makeIcon(false));
  }

  activeStoreId = id;

  // Highlight new marker
  if (markersMap[id]) {
    markersMap[id].setIcon(makeIcon(true));
    markersMap[id].openPopup();
  }

  // Highlight sidebar card
  document.querySelectorAll(".store-card").forEach((c) => c.classList.remove("active"));
  const card = document.querySelector(`.store-card[data-id="${id}"]`);
  if (card) {
    card.classList.add("active");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// ─── SIDEBAR RENDER ───────────────────────────────────────────────────────────
function renderStoreList(stores) {
  const listEl = document.getElementById("stores-list");

  if (!stores.length) {
    listEl.innerHTML = `
      <div class="stores-empty">
        <i class="fa-solid fa-store-slash"></i>
        <p>No stores found.</p>
      </div>`;
    return;
  }

  listEl.innerHTML = stores
    .map((store) => {
      const isMarketplace = store.name.toLowerCase().includes("marketplace");
      const distLabel = store.distance_miles != null
        ? `<span class="store-card-dist">${store.distance_miles.toFixed(1)} mi</span>`
        : "";
      return `
        <div class="store-card" data-id="${store.id}"
             onclick="flyToStore(${store.id}, ${store.latitude}, ${store.longitude})">
          <div class="store-card-icon ${isMarketplace ? "marketplace" : ""}">
            <i class="fa-solid fa-store"></i>
          </div>
          <div class="store-card-body">
            <div class="store-card-name">${store.name}</div>
            <div class="store-card-addr">${store.address}</div>
            <div class="store-card-city">${store.city}, ${store.state} ${store.zip_code}</div>
            <div style="margin-top: 8px;">
              <a
                href="${buildGoogleMapsUrl(store)}"
                target="_blank"
                rel="noopener noreferrer"
                onclick="event.stopPropagation()"
                style="display:inline-flex;align-items:center;gap:6px;color:#2563eb;text-decoration:none;font-weight:600;font-size:13px;"
              >
                <i class="fa-solid fa-diamond-turn-right"></i> Directions
              </a>
            </div>
          </div>
          ${distLabel}
        </div>`;
    })
    .join("");
}

// ─── FLY TO STORE ─────────────────────────────────────────────────────────────
function flyToStore(id, lat, lng) {
  map.flyTo([lat, lng], 15, { duration: 0.8 });
  setTimeout(() => selectStore(id), 600);
}

// ─── UPDATE STATS ─────────────────────────────────────────────────────────────
function updateStats(stores, nearbyCount = null) {
  document.getElementById("stat-stores").textContent = stores.length;

  if (nearbyCount !== null) {
    document.getElementById("stat-nearby").textContent = nearbyCount;
  }

  // Closest store (first in list if sorted by distance)
  if (stores.length && stores[0].distance_miles != null) {
    const closest = stores[0];
    document.getElementById("stat-closest").textContent =
      `${closest.name.replace("Kroger", "").trim() || "Kroger"} (${closest.distance_miles.toFixed(1)} mi)`;
  }
}

// ─── FIT BOUNDS ───────────────────────────────────────────────────────────────
function fitMapToStores(stores) {
  if (!stores.length) return;
  const group = L.featureGroup(
    stores.map((s) => L.marker([s.latitude, s.longitude]))
  );
  map.fitBounds(group.getBounds().pad(0.15));
}

// ─── LOAD ALL STORES ──────────────────────────────────────────────────────────
async function loadStores() {
  setLoadingUI(true, false, "");

  try {
    const res = await fetch(`${STORES_API}?limit=100`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // API returns StoreListResponse: { stores: [...], total, page, page_size }
    allStores = Array.isArray(data) ? data : (data.stores || []);
    // Fall back to mock data if database has no stores seeded yet
    if (allStores.length === 0) {
      console.warn("No stores in database — using mock store data");
      allStores = MOCK_STORES;
    }
  } catch (err) {
    console.warn("API unavailable — using mock store data:", err.message);
    allStores = MOCK_STORES;
  }

  setLoadingUI(false, false, "");
  document.getElementById("store-count-label").textContent =
    `${allStores.length} store${allStores.length !== 1 ? "s" : ""} found`;

  renderStoreList(allStores);
  addMarkers(allStores);
  fitMapToStores(allStores);
  updateStats(allStores);
}

// ─── GEOLOCATION / NEARBY ─────────────────────────────────────────────────────
document.getElementById("btn-use-location").addEventListener("click", () => {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }

  const btn = document.getElementById("btn-use-location");
  btn.classList.add("loading");
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Locating...';

  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      const { latitude, longitude } = pos.coords;
      btn.classList.remove("loading");
      btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> Near Me';

      // Pan map to user
      map.flyTo([latitude, longitude], 12, { duration: 1 });

      // Add user marker
      L.circleMarker([latitude, longitude], {
        radius: 8,
        fillColor: "#3b82f6",
        color: "white",
        weight: 2,
        fillOpacity: 1,
      })
        .addTo(map)
        .bindPopup("<b>Your Location</b>")
        .openPopup();

      // Fetch nearby stores from API
      try {
        const res = await fetch(
          `${NEARBY_API}?lat=${latitude}&lng=${longitude}&radius=25&limit=50`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const nearby = await res.json();

        // Fall back to client-side filtering if DB has no stores seeded yet
        if (!nearby.length) throw new Error("No stores in database yet");

        clearMarkers();
        addMarkers(nearby);
        renderStoreList(nearby);
        updateStats(nearby, nearby.length);

        document.getElementById("store-count-label").textContent =
          `${nearby.length} store${nearby.length !== 1 ? "s" : ""} within 25 miles`;
      } catch (err) {
        console.warn("Nearby API error — filtering mock data:", err.message);

        // Client-side fallback: filter mocks by rough distance
        const nearbyMock = MOCK_STORES.map((s) => ({
          ...s,
          distance_miles: haversine(latitude, longitude, s.latitude, s.longitude),
        }))
          .filter((s) => s.distance_miles <= 25)
          .sort((a, b) => a.distance_miles - b.distance_miles);

        clearMarkers();
        addMarkers(nearbyMock);
        renderStoreList(nearbyMock);
        updateStats(nearbyMock, nearbyMock.length);

        document.getElementById("store-count-label").textContent =
          `${nearbyMock.length} store${nearbyMock.length !== 1 ? "s" : ""} nearby`;
      }
    },
    (err) => {
      btn.classList.remove("loading");
      btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> Near Me';
      alert("Could not get your location. Please allow location access and try again.");
      console.error("Geolocation error:", err);
    }
  );
});

// ─── SEARCH ───────────────────────────────────────────────────────────────────
document.getElementById("store-search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase().trim();
  const filtered = allStores.filter(
    (s) =>
      s.name.toLowerCase().includes(q) ||
      s.address.toLowerCase().includes(q) ||
      s.city.toLowerCase().includes(q) ||
      s.zip_code.includes(q)
  );
  renderStoreList(filtered);
});

// ─── HELPERS ──────────────────────────────────────────────────────────────────
function setLoadingUI(loading, error, errorMsg) {
  const loadingEl = document.getElementById("stores-loading");
  const errorEl   = document.getElementById("stores-error");
  const errorText = document.getElementById("stores-error-text");

  if (loadingEl) loadingEl.style.display = loading ? "flex" : "none";
  if (errorEl)   errorEl.style.display   = error   ? "flex" : "none";
  if (errorText) errorText.textContent   = errorMsg || "";
}

// Haversine distance formula (miles)
function haversine(lat1, lon1, lat2, lon2) {
  const R = 3958.8; // Earth radius in miles
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ─── ZIP CODE SEARCH ──────────────────────────────────────────────────────────
// Uses OpenStreetMap Nominatim (free, no API key) to convert ZIP → lat/lng

async function searchByZip(zip) {
  const btn = document.getElementById("btn-zip-search");
  const errorEl = document.getElementById("zip-error");
  const errorText = document.getElementById("zip-error-text");

  // Validate: 5 digits
  if (!/^\d{5}$/.test(zip)) {
    errorEl.style.display = "flex";
    errorText.textContent = "Please enter a valid 5-digit ZIP code.";
    return;
  }

  // Hide previous error
  errorEl.style.display = "none";

  // Loading state
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
  btn.disabled = true;

  try {
    // Geocode ZIP → lat/lng using Nominatim
    const geoRes = await fetch(
      `https://nominatim.openstreetmap.org/search?postalcode=${zip}&country=US&format=json&limit=1`,
      { headers: { "Accept-Language": "en" } }
    );
    const geoData = await geoRes.json();

    if (!geoData.length) {
      errorEl.style.display = "flex";
      errorText.textContent = `ZIP code ${zip} not found.`;
      return;
    }

    const lat = parseFloat(geoData[0].lat);
    const lng = parseFloat(geoData[0].lon);

    // Pan map to ZIP location
    map.flyTo([lat, lng], 12, { duration: 1 });

    // Drop a marker for the ZIP location
    L.circleMarker([lat, lng], {
      radius: 8,
      fillColor: "#3b82f6",
      color: "white",
      weight: 2,
      fillOpacity: 1,
    })
      .addTo(map)
      .bindPopup(`<b>ZIP: ${zip}</b>`)
      .openPopup();

    // Fetch nearby stores
    try {
      const res = await fetch(
        `${NEARBY_API}?lat=${lat}&lng=${lng}&radius=25&limit=50`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const nearby = await res.json();

      // Fall back to client-side filtering if DB has no stores seeded yet
      if (!nearby.length) throw new Error("No stores in database yet");

      clearMarkers();
      addMarkers(nearby);
      renderStoreList(nearby);
      updateStats(nearby, nearby.length);
      document.getElementById("store-count-label").textContent =
        `${nearby.length} store${nearby.length !== 1 ? "s" : ""} near ${zip}`;
    } catch {
      // Fallback: filter mocks by distance from ZIP coords
      const nearbyMock = MOCK_STORES.map((s) => ({
        ...s,
        distance_miles: haversine(lat, lng, s.latitude, s.longitude),
      }))
        .filter((s) => s.distance_miles <= 25)
        .sort((a, b) => a.distance_miles - b.distance_miles);

      clearMarkers();
      addMarkers(nearbyMock);
      renderStoreList(nearbyMock);
      updateStats(nearbyMock, nearbyMock.length);
      document.getElementById("store-count-label").textContent =
        `${nearbyMock.length} store${nearbyMock.length !== 1 ? "s" : ""} near ${zip}`;
    }
  } catch (err) {
    errorEl.style.display = "flex";
    errorText.textContent = "Could not look up ZIP code. Check your connection.";
    console.error("ZIP geocode error:", err);
  } finally {
    btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Search';
    btn.disabled = false;
  }
}

document.getElementById("btn-zip-search").addEventListener("click", () => {
  const zip = document.getElementById("zip-input").value.trim();
  searchByZip(zip);
});

// Also trigger on Enter key in the zip input
document.getElementById("zip-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const zip = document.getElementById("zip-input").value.trim();
    searchByZip(zip);
  }
});

// ─── BOOT ─────────────────────────────────────────────────────────────────────
initMap();
loadStores();
