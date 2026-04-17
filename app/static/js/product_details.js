// Product Detail Page JavaScript

const API_BASE = "/api/products";
let priceChart = null;
let activeProductId = null;

function getAuthHeaders() {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── TRACKING (localStorage) ──────────────────────────────────────────────────
function normalizeTrackedIds(ids) {
  if (!Array.isArray(ids)) return [];
  const unique = new Set();
  ids.forEach((rawId) => {
    const parsed = Number(rawId);
    if (Number.isInteger(parsed) && parsed > 0) unique.add(parsed);
  });
  return Array.from(unique);
}

function getTrackedKey() {
  const email = localStorage.getItem("user_email") || "guest";
  return "tracked_" + email;
}

function getTracked() {
  try { return normalizeTrackedIds(JSON.parse(localStorage.getItem(getTrackedKey()) || "[]")); }
  catch { return []; }
}

function saveTracked(ids) {
  localStorage.setItem(getTrackedKey(), JSON.stringify(normalizeTrackedIds(ids)));
}

function isTracked(id) {
  return getTracked().includes(Number(id));
}

function toggleTrack(id) {
  id = Number(id);
  if (!Number.isInteger(id) || id <= 0) return false;

  let tracked = getTracked();
  if (tracked.includes(id)) {
    tracked = tracked.filter(t => t !== id);
  } else {
    tracked.push(id);
  }
  saveTracked(tracked);
  updateTrackButton(id);
  return isTracked(id);
}

function handleTrackClick() {
  if (!localStorage.getItem("access_token")) {
    // Show toast if not logged in
    const existing = document.getElementById("po-toast");
    if (existing) existing.remove();
    const style = document.createElement("style");
    style.textContent = "@keyframes slideUp { from { opacity:0; transform:translateX(-50%) translateY(20px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }";
    document.head.appendChild(style);
    const toast = document.createElement("div");
    toast.id = "po-toast";
    toast.innerHTML = `<i class="fa-solid fa-circle-info"></i><span>Please log in or create an account to save products.</span><a href="/" style="color:white;font-weight:700;margin-left:10px;text-decoration:underline;">Log in</a><a href="/register" style="color:white;font-weight:700;margin-left:8px;text-decoration:underline;">Sign up</a>`;
    toast.style.cssText = "position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:#111;color:white;padding:14px 22px;border-radius:10px;font-size:14px;display:flex;align-items:center;gap:10px;box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:9999;animation:slideUp 0.3s ease;white-space:nowrap;";
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity="0"; toast.style.transition="opacity 0.4s"; setTimeout(() => toast.remove(), 400); }, 4000);
    return;
  }
  const id = Number(activeProductId || getProductId());
  if (!id) return;
  toggleTrack(id);
}
window.handleTrackClick = handleTrackClick;

function updateTrackButton(id) {
  const btn = document.getElementById("btn-track-product");
  if (!btn) return;
  const tracked = isTracked(id);
  if (tracked) {
    btn.innerHTML = '<i class="fa-solid fa-bookmark"></i> Tracked';
  } else {
    btn.innerHTML = '<i class="fa-solid fa-plus"></i> Track Product';
  }
  btn.classList.toggle("is-tracked", tracked);
  btn.setAttribute("aria-pressed", tracked ? "true" : "false");
}

function getProductId() {
  const fromWindow = Number(window.PRODUCT_ID);
  if (Number.isInteger(fromWindow) && fromWindow > 0) return fromWindow;

  const fromBody = Number(document.body?.dataset?.productId);
  if (Number.isInteger(fromBody) && fromBody > 0) return fromBody;

  const pathMatch = window.location.pathname.match(/\/products\/(\d+)(?:\/)?$/);
  if (pathMatch) {
    const fromPath = Number(pathMatch[1]);
    if (Number.isInteger(fromPath) && fromPath > 0) return fromPath;
  }

  const params = new URLSearchParams(window.location.search);
  const fromQuery = Number(params.get("id") || params.get("product_id"));
  if (Number.isInteger(fromQuery) && fromQuery > 0) return fromQuery;

  return null;
}

document.addEventListener("DOMContentLoaded", async () => {
  activeProductId = getProductId();
  bindActions();

  if (!activeProductId) {
    showError("Invalid product ID");
    return;
  }

  await loadProductDetail(activeProductId, { showLoading: true });
});

function bindActions() {
  const trackButton = document.getElementById("btn-track-product");
  if (trackButton) {
    trackButton.addEventListener("click", handleTrackClick);
  }

  const updateButton = document.getElementById("update-price-btn");
  if (updateButton) {
    updateButton.addEventListener("click", async () => {
      if (!activeProductId) return;

      if (!localStorage.getItem("access_token")) {
        const statusEl = document.getElementById("update-price-status");
        if (statusEl) statusEl.textContent = "Please log in to update price.";
        return;
      }

      const statusEl = document.getElementById("update-price-status");
      updateButton.disabled = true;
      if (statusEl) statusEl.textContent = "Updating...";

      try {
        const response = await fetch(`${API_BASE}/${activeProductId}/update-price`, {
          method: "POST",
          headers: getAuthHeaders(),
        });

        if (!response.ok) {
          if (response.status === 401) {
            throw new Error("Session expired. Please log in again.");
          }
          const errorBody = await response.json().catch(() => ({}));
          const message = errorBody?.detail?.message || errorBody?.detail || "Price update failed";
          throw new Error(message);
        }

        const payload = await response.json();
        if (statusEl) {
          statusEl.textContent = `Updated to $${Number(payload.new_price).toFixed(2)}`;
        }

        await loadProductDetail(activeProductId, { showLoading: false });
      } catch (error) {
        if (statusEl) statusEl.textContent = String(error.message || "Update failed");
      } finally {
        updateButton.disabled = false;
      }
    });
  }
}

async function loadProductDetail(productId, { showLoading: shouldShowLoading }) {
  if (shouldShowLoading) showLoading();

  try {
    const productResponse = await fetch(`${API_BASE}/${productId}`);
    if (!productResponse.ok) throw new Error("Product not found");

    const product = await productResponse.json();

    let historyPayload = {
      history: [],
      current_price: product.current_price,
      statistics: {
        min: null,
        max: null,
        average: null,
        volatility: null,
        change_7d: null,
        change_30d: null,
        trend: "insufficient_data",
      },
    };

    const historyResponse = await fetch(`${API_BASE}/${productId}/price-history`);
    if (historyResponse.ok) {
      historyPayload = await historyResponse.json();
    }

    displayProductInfo(product, historyPayload.statistics);
    displayPriceHistory(historyPayload);
    hideLoading();
  } catch (error) {
    console.error("Error loading product:", error);
    showError(error.message);
  }
}

function displayProductInfo(product, stats = null) {
  activeProductId = Number(product.id);
  updateTrackButton(product.id);
  document.getElementById("product-name").textContent = product.name;
  document.getElementById("product-category").textContent = product.category || "Uncategorized";

  const healthScore = Number(product.health_score || 50);
  updateHealthScore(healthScore);

  const price = product.current_price;
  document.getElementById("current-price").textContent =
    price !== null && price !== undefined ? `$${Number(price).toFixed(2)}` : "N/A";

  displayPriceChange("change-7d", stats?.change_7d);
  displayPriceChange("change-30d", stats?.change_30d);

  const importDep = product.import_dependency || "Unknown";
  const importBadge = document.getElementById("import-dependency");
  importBadge.textContent = importDep;
  importBadge.className = `info-value badge-pill import-${importDep.toLowerCase()}`;

  const tariffRate = Number(product.tariff_rate || 0);
  document.getElementById("tariff-rate").textContent = `${tariffRate.toFixed(2)}%`;
  const rateTypeEl = document.getElementById("rate-type");
  if (rateTypeEl) {
    rateTypeEl.textContent = formatDisplayLabel(product.rate_type || "duty_free");
  }
  document.getElementById("origin-country").textContent = product.origin_country || "Not specified";
  document.getElementById("hts-code").textContent = product.hts_code || "Not specified";
  const confidenceEl = document.getElementById("confidence-score");
  if (confidenceEl) {
    confidenceEl.textContent = `${Number(product.confidence_score || 0).toFixed(2)}%`;
  }
  document.getElementById("retailer").textContent = product.retailer || "Kroger";

  updateHealthScoreBreakdown(product, stats);

  document.getElementById("product-description").textContent =
    product.description || "No description available for this product.";

  const lastUpdated = product.last_price_check ? formatDate(product.last_price_check) : "Never";
  document.getElementById("last-updated").textContent = lastUpdated;

  document.getElementById("product-detail").style.display = "block";
}

function updateHealthScore(score) {
  const scoreText = document.getElementById("score-text");
  const scoreFill = document.getElementById("score-fill");
  const statusBadge = document.getElementById("health-status");
  if (!scoreText || !scoreFill || !statusBadge) return;

  scoreText.textContent = Math.round(score);
  scoreFill.style.strokeDasharray = `${(score / 100) * 251.2} 251.2`;

  if (score >= 70) {
    statusBadge.textContent = "Low Risk";
    statusBadge.className = "status-badge low-risk";
    scoreFill.style.stroke = "#16a34a";
  } else if (score >= 40) {
    statusBadge.textContent = "Medium Risk";
    statusBadge.className = "status-badge medium-risk";
    scoreFill.style.stroke = "#eab308";
  } else {
    statusBadge.textContent = "High Risk";
    statusBadge.className = "status-badge high-risk";
    scoreFill.style.stroke = "#dc2626";
  }
}

function displayPriceChange(elementId, change) {
  const element = document.getElementById(elementId);
  if (change === null || change === undefined || Number.isNaN(Number(change))) {
    element.textContent = "--";
    return;
  }

  const value = Number(change);
  const arrow = value >= 0 ? "↑" : "↓";
  const className = value >= 0 ? "up" : "down";
  element.innerHTML = `<span class="price-badge ${className}">${arrow} ${Math.abs(value).toFixed(1)}%</span>`;
}

function formatDisplayLabel(value) {
  return String(value || "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function updateHealthScoreBreakdown(product, stats = null) {
  const tariffRate = Number(product.tariff_rate || 0);
  const tariffPenalty = Math.min((tariffRate / 25) * 40, 40);

  const dependencyMap = { Low: 0, Medium: 15, High: 30, Unknown: 10 };
  const dependencyPenalty = dependencyMap[product.import_dependency] ?? 10;

  const volatilityPercent = Number(stats?.volatility);
  const volatilityPenalty = Number.isFinite(volatilityPercent)
    ? Math.min((volatilityPercent / 100) * 30, 30)
    : 0;

  const tariffScore = Math.max(0, 100 - (tariffPenalty / 40) * 100);
  const dependencyScore = Math.max(0, 100 - (dependencyPenalty / 30) * 100);
  const volatilityScore = Math.max(0, 100 - (volatilityPenalty / 30) * 100);

  updateBreakdownBar("tariff-bar", tariffScore);
  updateBreakdownBar("dependency-bar", dependencyScore);
  updateBreakdownBar("volatility-bar", volatilityScore);
}

function updateBreakdownBar(barId, score) {
  const bar = document.getElementById(barId);
  if (!bar) return;

  bar.style.width = `${Math.max(0, Math.min(100, score))}%`;

  if (score >= 70) bar.style.backgroundColor = "#16a34a";
  else if (score >= 40) bar.style.backgroundColor = "#eab308";
  else bar.style.backgroundColor = "#dc2626";
}

function displayPriceHistory(historyData) {
  const history = Array.isArray(historyData.history) ? historyData.history : [];
  const stats = historyData.statistics || {};

  if (history.length === 0) {
    document.getElementById("chart-empty").style.display = "flex";
    displayStatistics(stats, historyData.current_price);
    displayRecentUpdates([]);
    return;
  }

  document.getElementById("chart-empty").style.display = "none";

  // API history is newest-first. Reverse for chart (oldest-first).
  const oldestFirst = [...history].reverse();
  const labels = oldestFirst.map((h) => formatChartDate(h.date));
  const prices = oldestFirst.map((h) => Number(h.price));
  createPriceChart(labels, prices);

  displayStatistics(stats, historyData.current_price);
  displayRecentUpdates(history.slice(0, 10));
}

function createPriceChart(labels, prices) {
  const canvas = document.getElementById("price-chart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  if (priceChart) priceChart.destroy();

  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Price ($)",
          data: prices,
          borderColor: "#111",
          backgroundColor: "rgba(17, 17, 17, 0.05)",
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "#111",
          pointBorderColor: "#fff",
          pointBorderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: false,
          ticks: {
            callback(value) {
              return `$${Number(value).toFixed(2)}`;
            },
            font: { size: 12 },
            color: "#666",
          },
          grid: { color: "rgba(0, 0, 0, 0.05)", drawBorder: false },
        },
        x: {
          grid: { display: false },
          ticks: {
            maxRotation: 45,
            minRotation: 45,
            font: { size: 11 },
            color: "#666",
          },
        },
      },
    },
  });
}

function displayStatistics(stats, fallbackCurrentPrice = null) {
  const current = stats.current ?? fallbackCurrentPrice;
  const average = stats.average;
  const min = stats.min;
  const max = stats.max;
  const volatility = stats.volatility;

  document.getElementById("stat-current").textContent = formatCurrency(current);
  document.getElementById("stat-average").textContent = formatCurrency(average);
  document.getElementById("stat-min").textContent = formatCurrency(min);
  document.getElementById("stat-max").textContent = formatCurrency(max);
  document.getElementById("stat-volatility").textContent =
    volatility === null || volatility === undefined || Number.isNaN(Number(volatility))
      ? "N/A"
      : `${Number(volatility).toFixed(1)}%`;
}

function displayRecentUpdates(history) {
  const container = document.getElementById("price-history-list");
  if (!container) return;

  if (!history.length) {
    container.innerHTML = '<p class="text-muted">No price history available</p>';
    return;
  }

  container.innerHTML = history
    .map((item, index) => {
      const current = Number(item.price);
      const previous = index < history.length - 1 ? Number(history[index + 1].price) : null;

      let changeHtml = "";
      if (previous !== null && previous !== 0) {
        const change = ((current - previous) / previous) * 100;
        changeHtml = `<span class="price-badge ${change >= 0 ? "up" : "down"}">`
          + `${change >= 0 ? "↑" : "↓"} ${Math.abs(change).toFixed(1)}%</span>`;
      }

      return `
        <div class="history-item">
          <span class="history-date">${formatDate(item.date)}</span>
          <span class="history-price">
            ${formatCurrency(item.price)}
            ${changeHtml}
          </span>
        </div>
      `;
    })
    .join("");
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return `$${Number(value).toFixed(2)}`;
}

function formatDate(dateString) {
  const parsed = new Date(dateString);
  if (Number.isNaN(parsed.getTime())) return "Unknown date";

  const now = new Date();
  const diffMs = now.getTime() - parsed.getTime();
  if (diffMs < 0) {
    return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;

  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatChartDate(dateString) {
  const parsed = new Date(dateString);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function showLoading() {
  document.getElementById("detail-loading").style.display = "flex";
  document.getElementById("detail-error").style.display = "none";
  document.getElementById("product-detail").style.display = "none";
}

function hideLoading() {
  document.getElementById("detail-loading").style.display = "none";
}

// =============================================================================
// STORE PRICE COMPARISON MAP
// =============================================================================

const STORES_API_BASE  = "/api/stores";
const PRICES_API_BASE  = "/api/products";

let storeMap       = null;
let storeMarkers   = {};
let activeRowId    = null;

// Mock store price data — used when backend prices API is not ready
const MOCK_STORE_PRICES = [
  { id: 1, name: "Kroger Marketplace", address: "4880 Lower Roswell Rd", city: "Marietta",      state: "GA", latitude: 33.9526, longitude: -84.4477, price: null },
  { id: 2, name: "Kroger",             address: "11695 Haynes Bridge Rd", city: "Alpharetta",   state: "GA", latitude: 34.0798, longitude: -84.2749, price: null },
  { id: 3, name: "Kroger",             address: "2685 Peachtree Rd NE",   city: "Atlanta",      state: "GA", latitude: 33.8340, longitude: -84.3680, price: null },
  { id: 4, name: "Kroger",             address: "5600 Roswell Rd NE",     city: "Sandy Springs", state: "GA", latitude: 33.9030, longitude: -84.3742, price: null },
  { id: 5, name: "Kroger",             address: "3330 Piedmont Rd NE",    city: "Atlanta",      state: "GA", latitude: 33.8468, longitude: -84.3618, price: null },
];

// Color tier helpers
function getPriceTier(price, min, max) {
  if (min === max) return "green";
  const range = max - min;
  const pct   = (price - min) / range;
  if (pct <= 0.33) return "green";
  if (pct <= 0.66) return "yellow";
  return "red";
}

function tierColor(tier) {
  return tier === "green" ? "#16a34a" : tier === "yellow" ? "#eab308" : "#dc2626";
}

function tierTextClass(tier) {
  return tier === "green" ? "price-green" : tier === "yellow" ? "price-yellow" : "price-red";
}

// Build a colored pin icon
function storePinIcon(tier, selected = false) {
  const color  = tierColor(tier);
  const border = selected ? "#111" : "white";
  const size   = selected ? 34 : 28;
  return L.divIcon({
    className: "",
    html: `<div style="
      width:${size}px; height:${size}px;
      background:${color};
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      border:2px solid ${border};
      box-shadow:0 3px 8px rgba(0,0,0,0.25);
      transition: all 0.15s;
    "></div>`,
    iconSize:    [size, size],
    iconAnchor:  [size / 2, size],
    popupAnchor: [0, -(size + 4)],
  });
}

// Open modal
async function openStoreMapModal(productId, productName, basePrice) {
  const modal = document.getElementById("store-map-modal");
  modal.style.display = "flex";
  document.getElementById("modal-product-name").textContent = productName;
  document.getElementById("modal-loading-icon").style.display = "inline-block";
  document.getElementById("modal-store-count").textContent = "";

  // Init map (lazy — only once)
  if (!storeMap) {
    storeMap = L.map("store-price-map", { zoomControl: false })
      .setView([33.9526, -84.3533], 11);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }).addTo(storeMap);

    L.control.zoom({ position: "bottomright" }).addTo(storeMap);
  }

  // Clear previous markers
  Object.values(storeMarkers).forEach((m) => storeMap.removeLayer(m));
  storeMarkers = {};
  activeRowId  = null;

  // Invalidate size after modal displays
  setTimeout(() => storeMap.invalidateSize(), 100);

  // Fetch stores + prices
  let storesWithPrices = [];

  try {
    // 1. Get all stores
    const storeRes = await fetch(`${STORES_API_BASE}?limit=100`);
    let stores = [];
    if (storeRes.ok) {
      const data = await storeRes.json();
      stores = Array.isArray(data) ? data : (data.stores || []);
    } else {
      stores = MOCK_STORE_PRICES;
    }

    // 2. Try to get product prices by store
    const storeIds = stores.map((s) => s.id).join(",");
    let priceMap = {};
    try {
      const priceRes = await fetch(`${PRICES_API_BASE}/${productId}/prices?store_ids=${storeIds}`);
      if (priceRes.ok) {
        const priceData = await priceRes.json();
        const pricesArray = priceData?.prices || priceData;
        (Array.isArray(pricesArray) ? pricesArray : []).forEach((p) => {
          priceMap[p.store_id] = p.price;
        });
      }
    } catch {
      // Prices API not ready yet — generate slight variations of base price
    }

    // 3. Assemble stores with prices
    storesWithPrices = stores.map((s) => {
      let price = priceMap[s.id] ?? null;
      // Fallback: use base price with small random variation so colors differ
      if (price === null && basePrice) {
        const variation = (Math.random() * 0.3 - 0.1);   // ±10-30 cents
        price = Math.max(0.01, Number(basePrice) + variation);
        price = Math.round(price * 100) / 100;
      }
      return { ...s, price };
    }).filter((s) => s.latitude && s.longitude);

  } catch (err) {
    console.warn("Store map error:", err);
    storesWithPrices = MOCK_STORE_PRICES.map((s, i) => ({
      ...s,
      price: basePrice ? Math.round((Number(basePrice) + (i - 2) * 0.08) * 100) / 100 : null,
    }));
  }

  // Color-code by price tier
  const prices = storesWithPrices.map((s) => s.price).filter((p) => p !== null);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);

  storesWithPrices.forEach((store) => {
    const tier   = store.price !== null ? getPriceTier(store.price, minPrice, maxPrice) : "yellow";
    store._tier  = tier;
  });

  // Add markers
  storesWithPrices.forEach((store) => {
    const marker = L.marker([store.latitude, store.longitude], {
      icon: storePinIcon(store._tier, false),
    }).addTo(storeMap);

    const priceLabel = store.price !== null ? `$${store.price.toFixed(2)}` : "N/A";
    marker.bindPopup(`
      <div style="font-family:Arial,sans-serif; min-width:180px; padding:4px;">
        <div style="font-weight:700; font-size:14px; margin-bottom:6px;">${store.name}</div>
        <div style="font-size:12px; color:#666; margin-bottom:4px;">
          <i class="fa-solid fa-location-dot"></i> ${store.address}, ${store.city}
        </div>
        <div style="font-size:18px; font-weight:700; color:${tierColor(store._tier)}; margin-top:8px;">
          ${priceLabel}
        </div>
      </div>
    `, { maxWidth: 220 });

    marker.on("click", () => selectStoreRow(store.id));
    storeMarkers[store.id] = { marker, tier: store._tier };
  });

  // Fit bounds
  if (storesWithPrices.length) {
    const group = L.featureGroup(storesWithPrices.map((s) => L.marker([s.latitude, s.longitude])));
    storeMap.fitBounds(group.getBounds().pad(0.15));
  }

  // Render sidebar list (sorted cheapest first)
  const sorted = [...storesWithPrices].sort((a, b) => (a.price ?? 999) - (b.price ?? 999));
  renderModalList(sorted, minPrice, maxPrice);

  // Update header
  document.getElementById("modal-loading-icon").style.display = "none";
  document.getElementById("modal-store-count").textContent =
    `${storesWithPrices.length} store${storesWithPrices.length !== 1 ? "s" : ""}`;
}

function selectStoreRow(id) {
  // Reset previous
  if (activeRowId && storeMarkers[activeRowId]) {
    storeMarkers[activeRowId].marker.setIcon(
      storePinIcon(storeMarkers[activeRowId].tier, false)
    );
  }
  activeRowId = id;

  if (storeMarkers[id]) {
    storeMarkers[id].marker.setIcon(storePinIcon(storeMarkers[id].tier, true));
    storeMarkers[id].marker.openPopup();
  }

  document.querySelectorAll(".store-price-row").forEach((r) => r.classList.remove("active"));
  const row = document.querySelector(`.store-price-row[data-id="${id}"]`);
  if (row) {
    row.classList.add("active");
    row.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function renderModalList(stores, minPrice, maxPrice) {
  const listEl = document.getElementById("modal-store-list");
  if (!stores.length) {
    listEl.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af;font-size:13px;">No stores found</div>';
    return;
  }

  listEl.innerHTML = stores.map((store) => {
    const tier       = store._tier || "yellow";
    const dotColor   = tierColor(tier);
    const textClass  = tierTextClass(tier);
    const priceLabel = store.price !== null ? `$${store.price.toFixed(2)}` : "N/A";
    return `
      <div class="store-price-row" data-id="${store.id}"
           onclick="flyModalToStore(${store.id}, ${store.latitude}, ${store.longitude})">
        <span class="store-price-dot" style="background:${dotColor};"></span>
        <div class="store-price-info">
          <div class="store-price-name">${store.name}</div>
          <div class="store-price-addr">${store.city}, ${store.state}</div>
        </div>
        <span class="store-price-tag ${textClass}">${priceLabel}</span>
      </div>`;
  }).join("");
}

function flyModalToStore(id, lat, lng) {
  storeMap.flyTo([lat, lng], 15, { duration: 0.7 });
  setTimeout(() => selectStoreRow(id), 500);
}

// Close modal
function closeStoreMapModal() {
  const modal = document.getElementById("store-map-modal");
  if (modal) modal.style.display = "none";
}

const closeModalButton = document.getElementById("close-modal-btn");
if (closeModalButton) {
  closeModalButton.addEventListener("click", closeStoreMapModal);
}

// Close on backdrop click
const storeMapModal = document.getElementById("store-map-modal");
if (storeMapModal) {
  storeMapModal.addEventListener("click", (e) => {
    if (e.target === storeMapModal) closeStoreMapModal();
  });
}

// Close on Escape key
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeStoreMapModal();
});

// Wire up the "Find in Stores" button
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("find-in-stores-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const productName = document.getElementById("product-name")?.textContent || "Product";
      const priceText   = document.getElementById("current-price")?.textContent || "0";
      const basePrice   = parseFloat(priceText.replace("$", "")) || null;
      openStoreMapModal(activeProductId, productName, basePrice);
    });
  }
});

function showError(message) {
  const loading = document.getElementById("detail-loading");
  const error = document.getElementById("detail-error");
  const errorText = document.getElementById("detail-error-text");
  const detail = document.getElementById("product-detail");

  if (loading) loading.style.display = "none";
  if (error) error.style.display = "flex";
  if (errorText) errorText.textContent = message || "Product not found";
  if (detail) detail.style.display = "none";
}
