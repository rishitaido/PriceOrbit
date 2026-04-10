// ── TRACKED PRODUCTS (localStorage) ──────────────────────────────────────────

function getTrackedKey() {
  const email = localStorage.getItem("user_email") || "guest";
  return "tracked_" + email;
}

function getTracked() {
  try {
    return JSON.parse(localStorage.getItem(getTrackedKey()) || "[]");
  } catch { return []; }
}

function saveTracked(ids) {
  localStorage.setItem(getTrackedKey(), JSON.stringify(ids));
}

function isTracked(id) {
  return getTracked().includes(Number(id));
}

function toggleTrack(id, btn) {
  if (!localStorage.getItem("access_token")) {
    showToast("Please log in or create an account to save products.");
    return;
  }
  id = Number(id);
  let tracked = getTracked();
  if (tracked.includes(id)) {
    tracked = tracked.filter(t => t !== id);
    btn.innerHTML = '<i class="fa-regular fa-bookmark"></i>';
    btn.title = "Track this product";
  } else {
    tracked.push(id);
    btn.innerHTML = '<i class="fa-solid fa-bookmark"></i>';
    btn.title = "Untrack this product";
  }
  saveTracked(tracked);
}

function showToast(message) {
  const existing = document.getElementById("po-toast");
  if (existing) existing.remove();
  const style = document.createElement("style");
  style.textContent = "@keyframes slideUp { from { opacity:0; transform:translateX(-50%) translateY(20px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }";
  document.head.appendChild(style);
  const toast = document.createElement("div");
  toast.id = "po-toast";
  toast.innerHTML = `<i class="fa-solid fa-circle-info"></i><span>${message}</span><a href="/" style="color:white;font-weight:700;margin-left:10px;text-decoration:underline;">Log in</a><a href="/register" style="color:white;font-weight:700;margin-left:8px;text-decoration:underline;">Sign up</a>`;
  toast.style.cssText = "position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:#111;color:white;padding:14px 22px;border-radius:10px;font-size:14px;display:flex;align-items:center;gap:10px;box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:9999;animation:slideUp 0.3s ease;white-space:nowrap;";
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity="0"; toast.style.transition="opacity 0.4s"; setTimeout(() => toast.remove(), 400); }, 4000);
}

// products.js - product listing, filtering, search, and pagination
const API_BASE = "/api/products";

let allProducts = [];
let totalProducts = 0;

const state = {
  skip: 0,
  limit: 20,
  category: "all",
  query: "",
};

let searchTimeout;

function normalizeProduct(p) {
  return {
    id: p.id,
    name: p.name ?? "Unnamed Product",
    category: p.category ?? "Uncategorized",
    current_price: p.current_price ?? p.currentPrice ?? null,
    health_score: p.health_score ?? p.healthScore ?? 0,
  };
}

function getHealthScoreClass(score) {
  if (score >= 70) return "health-green";
  if (score >= 40) return "health-yellow";
  return "health-red";
}

function getRiskLevel(score) {
  if (score >= 70) return "Stable";
  if (score >= 40) return "Medium Risk";
  return "High Risk";
}

function getRiskIcon(score) {
  if (score >= 70) return '<i class="fa-solid fa-circle-check"></i>';
  if (score >= 40) return '<i class="fa-solid fa-triangle-exclamation"></i>';
  return '<i class="fa-solid fa-circle-exclamation"></i>';
}

function setLoadingUI({ loading, errorMessage }) {
  const loadingElement = document.getElementById("loading");
  const errorElement = document.getElementById("error");
  const errorText = document.getElementById("error-text");

  if (loadingElement) loadingElement.style.display = loading ? "flex" : "none";

  if (errorElement && errorText) {
    if (errorMessage) {
      errorElement.style.display = "flex";
      errorText.textContent = errorMessage;
    } else {
      errorElement.style.display = "none";
      errorText.textContent = "";
    }
  }
}

function applyClientFilters(products) {
  const riskFilter = document.getElementById("risk-filter")?.value || "all";
  const sortBy = document.getElementById("sort-select")?.value || "health-desc";

  let filtered = [...products];

  if (riskFilter !== "all") {
    filtered = filtered.filter((p) => {
      if (riskFilter === "low") return p.health_score >= 70;
      if (riskFilter === "medium") return p.health_score >= 40 && p.health_score < 70;
      if (riskFilter === "high") return p.health_score < 40;
      return true;
    });
  }

  filtered.sort((a, b) => {
    if (sortBy === "health-desc") return b.health_score - a.health_score;
    if (sortBy === "health-asc") return a.health_score - b.health_score;
    if (sortBy === "price-desc") return (b.current_price || 0) - (a.current_price || 0);
    if (sortBy === "price-asc") return (a.current_price || 0) - (b.current_price || 0);
    if (sortBy === "name-asc") return a.name.localeCompare(b.name);
    if (sortBy === "name-desc") return b.name.localeCompare(a.name);
    return 0;
  });

  return filtered;
}

function updateDashboardStats(products, total) {
  const avgHealth = products.length
    ? Math.round(products.reduce((sum, p) => sum + Number(p.health_score || 0), 0) / products.length)
    : 0;
  const highRisk = products.filter((p) => p.health_score < 40).length;

  const userEmail = localStorage.getItem("user_email") || "guest";

  // Active alerts from localStorage
  let activeAlerts = 0;
  try {
    const alerts = JSON.parse(localStorage.getItem("alerts_" + userEmail) || "{}");
    activeAlerts = Object.values(alerts).filter(a => a.enabled).length;
  } catch { activeAlerts = 0; }

  // User's personally tracked products count
  let myTrackedCount = 0;
  try {
    myTrackedCount = JSON.parse(localStorage.getItem("tracked_" + userEmail) || "[]").length;
  } catch { myTrackedCount = 0; }

  document.getElementById("stat-total").textContent = myTrackedCount;
  document.getElementById("stat-health").textContent = avgHealth;
  document.getElementById("stat-risk").textContent = highRisk;
  document.getElementById("stat-alerts").textContent = activeAlerts;
}

function createProductCard(product) {
  const healthClass = getHealthScoreClass(product.health_score);
  const riskLevel = getRiskLevel(product.health_score);
  const riskIcon = getRiskIcon(product.health_score);

  const priceDisplay =
    product.current_price !== null && product.current_price !== undefined
      ? `$${parseFloat(product.current_price).toFixed(2)}`
      : "N/A";

  return `
    <div class="product-item">
      <div class="product-icon">
        <i class="fa-solid fa-box"></i>
      </div>

      <div class="product-info">
        <h3 class="product-name">${product.name}</h3>
        <div class="product-meta">
          <span class="product-category">${product.category}</span>
          <span class="product-price">Kroger Price: ${priceDisplay}</span>
        </div>
      </div>

      <div class="product-health">
        <div class="health-label">Health Score</div>
        <div class="health-score-container">
          <div class="health-bar-wrapper">
            <div class="health-bar-fill health-bar-${healthClass.replace("health-", "")}" style="width: ${product.health_score}%"></div>
          </div>
          <span class="health-score-number ${healthClass}">${product.health_score}</span>
        </div>
      </div>

      <div class="product-status">
        <span class="status-badge ${healthClass}">
          ${riskIcon} ${riskLevel}
        </span>
      </div>

      <div class="product-actions" style="display:flex; gap:8px; align-items:center;">
        <button class="btn-view-details" data-product-id="${product.id}">View Details <i class="fa-solid fa-arrow-right"></i></button>
      </div>
    </div>
  `;
}

function renderProducts(products) {
  const productsList = document.getElementById("products-list");
  if (!productsList) return;

  if (products.length === 0) {
    productsList.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 40px;">
        <i class="fa-solid fa-magnifying-glass" style="font-size: 3rem; color: #ccc;"></i>
        <p style="margin-top: 10px; color: #666;">No products found matching your filters.</p>
      </div>`;
    return;
  }

  productsList.innerHTML = products.map(createProductCard).join("");
  productsList.querySelectorAll(".btn-view-details").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-product-id");
      window.location.href = `/products/${id}`;
    });
  });
}

function getEndpoint() {
  const params = new URLSearchParams({
    skip: String(state.skip),
    limit: String(state.limit),
  });

  if (state.query.length >= 2) {
    params.set("q", state.query);
    if (state.category !== "all") params.set("category", state.category);
    return `${API_BASE}/search?${params.toString()}`;
  }

  if (state.category !== "all") {
    return `${API_BASE}/category/${encodeURIComponent(state.category)}?${params.toString()}`;
  }

  return `${API_BASE}/?${params.toString()}`;
}

function syncStateFromURL() {
  const params = new URLSearchParams(window.location.search);
  const category = params.get("category");
  const query = params.get("q");
  const page = Number(params.get("page") || "1");

  if (category) state.category = category;
  if (query) state.query = query;
  if (Number.isFinite(page) && page > 0) state.skip = (page - 1) * state.limit;

  const categoryFilter = document.getElementById("category-filter");
  const searchInput = document.getElementById("search-input");
  if (categoryFilter && state.category !== "all") categoryFilter.value = state.category;
  if (searchInput && state.query) searchInput.value = state.query;
}

function syncURLFromState(page, totalPages) {
  const url = new URL(window.location);
  if (state.category !== "all") url.searchParams.set("category", state.category);
  else url.searchParams.delete("category");

  if (state.query.length >= 2) url.searchParams.set("q", state.query);
  else url.searchParams.delete("q");

  if (totalPages > 1) url.searchParams.set("page", String(page));
  else url.searchParams.delete("page");

  window.history.pushState({}, "", url);
}

function updatePagination(page, totalPages) {
  const prevBtn = document.getElementById("prev-page");
  const nextBtn = document.getElementById("next-page");
  const pageInfo = document.getElementById("page-info");

  if (!prevBtn || !nextBtn || !pageInfo) return;

  const hasPages = totalPages > 0;
  prevBtn.disabled = !hasPages || page <= 1;
  nextBtn.disabled = !hasPages || page >= totalPages;
  pageInfo.textContent = hasPages ? `Page ${page} of ${totalPages}` : "Page 0 of 0";
}

async function fetchProducts() {
  setLoadingUI({ loading: true, errorMessage: null });

  try {
    const response = await fetch(getEndpoint());
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    const payload = Array.isArray(data)
      ? { products: data, total: data.length, page: 1, page_size: state.limit }
      : data;

    allProducts = (payload.products || []).map(normalizeProduct);
    totalProducts = payload.total ?? allProducts.length;

    const visibleProducts = applyClientFilters(allProducts);
    renderProducts(visibleProducts);
    updateDashboardStats(allProducts, totalProducts);

    const countBadge = document.getElementById("category-count");
    if (countBadge) countBadge.textContent = `${totalProducts} Products`;

    const page = payload.page || 1;
    const totalPages = Math.max(1, Math.ceil(totalProducts / state.limit));
    updatePagination(page, totalPages);
    syncURLFromState(page, totalPages);

    setLoadingUI({ loading: false, errorMessage: null });
  } catch (error) {
    console.error("Failed to load products:", error);
    setLoadingUI({ loading: false, errorMessage: "Unable to load products." });
    updatePagination(0, 0);
  }
}

function setupControls() {
  const categoryFilter = document.getElementById("category-filter");
  const riskFilter = document.getElementById("risk-filter");
  const sortSelect = document.getElementById("sort-select");
  const clearBtn = document.getElementById("clear-filter");
  const searchInput = document.getElementById("search-input");
  const prevBtn = document.getElementById("prev-page");
  const nextBtn = document.getElementById("next-page");

  if (categoryFilter) {
    categoryFilter.addEventListener("change", async () => {
      state.category = categoryFilter.value || "all";
      state.skip = 0;
      if (clearBtn) clearBtn.style.display = state.category !== "all" ? "inline-block" : "none";
      await fetchProducts();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      state.category = "all";
      state.skip = 0;
      if (categoryFilter) categoryFilter.value = "all";
      clearBtn.style.display = "none";
      await fetchProducts();
    });
  }

  if (riskFilter) {
    riskFilter.addEventListener("change", () => renderProducts(applyClientFilters(allProducts)));
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", () => renderProducts(applyClientFilters(allProducts)));
  }

  if (searchInput) {
    searchInput.addEventListener("input", (event) => {
      const query = (event.target.value || "").trim();
      clearTimeout(searchTimeout);

      searchTimeout = setTimeout(async () => {
        state.query = query;
        state.skip = 0;

        if (query.length === 0 || query.length >= 2) {
          await fetchProducts();
        }
      }, 300);
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", async () => {
      if (state.skip >= state.limit) {
        state.skip -= state.limit;
        await fetchProducts();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", async () => {
      if (state.skip + state.limit < totalProducts) {
        state.skip += state.limit;
        await fetchProducts();
      }
    });
  }
}


document.addEventListener("DOMContentLoaded", async () => {
  syncStateFromURL();
  setupControls();

  const clearBtn = document.getElementById("clear-filter");
  if (clearBtn && state.category !== "all") clearBtn.style.display = "inline-block";

  await fetchProducts();
});