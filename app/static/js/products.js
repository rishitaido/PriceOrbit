// products.js - Fetches and displays tracked products from FastAPI backend

// URL when FastAPI serves the page
const API_URL = "/api/products";

// Global products array for filtering and sorting
let allProducts = [];

// TEMP data for Live Server 
const FALLBACK_PRODUCTS = [
  { id: 1, name: "Organic Milk", category: "Dairy", current_price: 4.99, health_score: 85 },
  { id: 2, name: "Baby Formula", category: "Baby Products", current_price: 31.99, health_score: 42 },
  { id: 3, name: "Olive Oil", category: "Pantry", current_price: 18.99, health_score: 38 },
  { id: 4, name: "Coffee Beans", category: "Pantry", current_price: 12.99, health_score: 72 },
];

// Normalize backend field names in case backend returns snake_case
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
  if (score >= 70) return "health-green";   // 70-100
  if (score >= 40) return "health-yellow";  // 40-69
  return "health-red";                      // 0-39
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

function updateDashboardStats(products) {
  const total = products.length;
  const avgHealth = total > 0 
    ? Math.round(products.reduce((sum, p) => sum + p.health_score, 0) / total) 
    : 0;
  const highRisk = products.filter(p => p.health_score < 40).length;
  
  // Active alerts: count products with health score below 70 (medium-high risk)
  const activeAlerts = products.filter(p => p.health_score < 70).length;

  document.getElementById("stat-total").textContent = total;
  document.getElementById("stat-health").textContent = avgHealth;
  document.getElementById("stat-risk").textContent = highRisk;
  document.getElementById("stat-alerts").textContent = activeAlerts;
}

function filterAndSortProducts() {
  const categoryFilter = document.getElementById("category-filter")?.value || "all";
  const riskFilter = document.getElementById("risk-filter")?.value || "all";
  const sortBy = document.getElementById("sort-select")?.value || "health-desc";
  const searchTerm = document.getElementById("search-input")?.value.toLowerCase().trim() || "";

  let filtered = [...allProducts];

  // 1. Apply category filter
  if (categoryFilter !== "all") {
    filtered = filtered.filter(p => p.category === categoryFilter);
  }

  // 2. Apply risk filter
  if (riskFilter !== "all") {
    filtered = filtered.filter(p => {
      if (riskFilter === "low") return p.health_score >= 70;
      if (riskFilter === "medium") return p.health_score >= 40 && p.health_score < 70;
      if (riskFilter === "high") return p.health_score < 40;
      return true;
    });
  }

  // 3. Apply search filter 
  if (searchTerm.length >= 2) {
    filtered = filtered.filter(p => 
      p.name.toLowerCase().includes(searchTerm) || 
      p.category.toLowerCase().includes(searchTerm)
    );
  }

    // 4. Apply sorting
  filtered.sort((a, b) => {
    if (sortBy === "health-desc") return b.health_score - a.health_score;
    if (sortBy === "health-asc") return a.health_score - b.health_score;
    if (sortBy === "price-desc") return (b.current_price || 0) - (a.current_price || 0);
    if (sortBy === "price-asc") return (a.current_price || 0) - (b.current_price || 0);
    if (sortBy === "name-asc") return a.name.localeCompare(b.name);
    if (sortBy === "name-desc") return b.name.localeCompare(a.name);
    return 0;
  });


  renderProducts(filtered);
}

function renderProducts(products) {
  const productsList = document.getElementById("products-list");
  const countBadge = document.getElementById("category-count");
  if (!productsList) return;

  // Update the count badge 
  if (countBadge) {
    countBadge.textContent = `${products.length} Products`;
  }

  // Handle Empty State 
  if (products.length === 0) {
    productsList.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 40px;">
        <i class="fa-solid fa-magnifying-glass" style="font-size: 3rem; color: #ccc;"></i>
        <p style="margin-top: 10px; color: #666;">No products found matching your search.</p>
        <button onclick="location.href='products.html'" class="btn-api-docs" style="margin-top: 10px;">Clear All Filters</button>
      </div>`;
    return;
  }

  // Render the list of products
  productsList.innerHTML = products.map(createProductCard).join("");

  // view details
  productsList.querySelectorAll(".btn-view-details").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-product-id");
      viewProductDetails(id);
    });
  });
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
            <div class="health-bar-fill health-bar-${healthClass.replace('health-', '')}" style="width: ${product.health_score}%"></div>
          </div>
          <span class="health-score-number ${healthClass}">${product.health_score}</span>
        </div>
      </div>

      <div class="product-status">
        <span class="status-badge ${healthClass}">
          ${riskIcon} ${riskLevel}
        </span>
      </div>

      <div class="product-actions">
        <button class="btn-view-details" data-product-id="${product.id}"> 
        View Details
        </button>
      </div>
    </div>
  `;
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

async function fetchProducts() {
  const productsList = document.getElementById("products-list");
  if (!productsList) return;

  setLoadingUI({ loading: true, errorMessage: null });

  try {
    const res = await fetch("/api/products?skip=0&limit=50");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    // Save to the global array so filtering/sorting works later
    allProducts = Array.isArray(data) ? data : data.products;

    if (!allProducts || allProducts.length === 0) {
      setLoadingUI({ loading: false, errorMessage: "No products found in database." });
      return;
    }

    // Display the products and update the stats
    renderProducts(allProducts);
    updateDashboardStats(allProducts);
    setLoadingUI({ loading: false, errorMessage: null });

  } catch (err) {
    console.error("Backend connection failed:", err);
    setLoadingUI({ loading: false, errorMessage: "Failed to connect to PriceOrbit API." });
  }
}




// Setup filter and sort event listeners
function setupControls() {
  const categoryFilter = document.getElementById("category-filter");
  const riskFilter = document.getElementById("risk-filter");
  const sortSelect = document.getElementById("sort-select");
  const searchInput = document.getElementById("search-input");

  if (categoryFilter) categoryFilter.addEventListener("change", filterAndSortProducts);
  if (riskFilter) riskFilter.addEventListener("change", filterAndSortProducts);
  if (sortSelect) sortSelect.addEventListener("change", filterAndSortProducts);
  

  
  const clearBtn = document.getElementById("clear-filter");

  // Show/Hide "Clear" button based on selection
  categoryFilter.addEventListener("change", () => {
    if (categoryFilter.value !== "all") {
      clearBtn.style.display = "inline-block";
    } else {
      clearBtn.style.display = "none";
  }
  });

  // Reset logic
  clearBtn.addEventListener("click", () => {
    categoryFilter.value = "all";           // Reset dropdown
    clearBtn.style.display = "none";        // Hide self
    
    // Clear the URL parameter
    const url = new URL(window.location);
    url.searchParams.delete('category');
    window.history.pushState({}, '', url);
    
    filterAndSortProducts();                // Refresh the list
  });
  }

// Placeholder
function viewProductDetails(productId) {
  window.location.href = `/product/${productId}`;
}

document.addEventListener("DOMContentLoaded", () => {
  console.log("Ready, fetching products...");
  setupControls();
  
  // 1. Check if the URL has a category (e.g., ?category=Fresh+Produce)
  const urlParams = new URLSearchParams(window.location.search);
  const categoryParam = urlParams.get('category');

  // 2. If it does, set the dropdown value before fetching
  if (categoryParam) {
    const categoryFilter = document.getElementById("category-filter");
    if (categoryFilter) {
      categoryFilter.value = categoryParam;
    }
  }

  fetchProducts().then(() => {
    // 3. Re-filter after products are loaded to match the URL
    if (categoryParam) {
      filterAndSortProducts();
    }
  });
});

let searchTimeout;

const searchInput = document.getElementById("search-input");

if (searchInput) {
  searchInput.addEventListener("input", (e) => {
    const query = e.target.value.trim();

    // Clear the previous timer every time the user types
    clearTimeout(searchTimeout);

    // Wait 300ms after the user stops typing to trigger the search
    searchTimeout = setTimeout(() => {
      handleSearch(query);
    }, 300);
  });
}

function handleSearch(query) {
  // Update URL for deep linking
  const url = new URL(window.location);
  if (query) {
    url.searchParams.set('q', query);
  } else {
    url.searchParams.delete('q');
  }
  window.history.pushState({}, '', url);

  // Trigger the filtering logic
  filterAndSortProducts();
}