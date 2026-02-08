// products.js - Fetches and displays tracked products from FastAPI backend

// URL when FastAPI serves the page
const API_URL = "/api/products";

// TEMP data for Live Server / when backend isn't running yet
const FALLBACK_PRODUCTS = [
  { id: 1, name: "Organic Milk", category: "Dairy", current_price: 4.99, health_score: 85 },
  { id: 2, name: "Baby Formula", category: "Baby Products", current_price: 31.99, health_score: 42 },
  { id: 3, name: "Olive Oil", category: "Pantry", current_price: 18.99, health_score: 38 },
  { id: 4, name: "Coffee Beans", category: "Pantry", current_price: 12.99, health_score: 72 },
];

// Normalize backend field names just in case backend returns snake_case
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
          <span class="product-price">Walmart Price: ${priceDisplay}</span>
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
  productsList.innerHTML = "";

  let products = [];

  try {
    // Try API first
    const res = await fetch(API_URL);

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    products = Array.isArray(data) ? data.map(normalizeProduct) : [];
  } catch (err) {
    // Fallback for Live Server / backend down
    console.warn("API fetch failed, using fallback products:", err);
    products = FALLBACK_PRODUCTS.map(normalizeProduct);
  }

  setLoadingUI({ loading: false, errorMessage: null });

  if (!products.length) {
    setLoadingUI({
      loading: false,
      errorMessage: 'No products found. Click "+ Track Product" to add products.',
    });
    return;
  }

  // Render
  productsList.innerHTML = products.map(createProductCard).join("");

  // Hook up buttons (no inline onclick needed)
  productsList.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-view-details");
    if (!btn) return;
    const id = btn.getAttribute("data-product-id");
    viewProductDetails(id);
  });
}

// Placeholder
function viewProductDetails(productId) {
  alert(`Product details for ID ${productId} will be implemented later`);
}

// Search functionality
function setupSearchFilter() {
  const searchInput = document.getElementById("search-input");
  if (!searchInput) return;

  searchInput.addEventListener("input", (e) => {
    const searchTerm = e.target.value.toLowerCase().trim();
    const productItems = document.querySelectorAll(".product-item");

    productItems.forEach((item) => {
      const productName = item.querySelector(".product-name")?.textContent.toLowerCase() || "";
      const productCategory = item.querySelector(".product-category")?.textContent.toLowerCase() || "";
      
      if (productName.includes(searchTerm) || productCategory.includes(searchTerm)) {
        item.style.display = "";
      } else {
        item.style.display = "none";
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  fetchProducts();
  setupSearchFilter();
});