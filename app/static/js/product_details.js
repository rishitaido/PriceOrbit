// Product Detail Page JavaScript

const API_BASE = "/api/products";
let priceChart = null;
let activeProductId = null;

function getProductId() {
  const match = window.location.pathname.match(/\/products?\/(\d+)/);
  return match ? match[1] : null;
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
  const updateButton = document.getElementById("update-price-btn");
  if (!updateButton) return;

  updateButton.addEventListener("click", async () => {
    if (!activeProductId) return;

    const statusEl = document.getElementById("update-price-status");
    updateButton.disabled = true;
    if (statusEl) statusEl.textContent = "Updating...";

    try {
      const response = await fetch(`${API_BASE}/${activeProductId}/update-price`, {
        method: "POST",
      });

      if (!response.ok) {
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

  document.getElementById("tariff-rate").textContent = `${product.tariff_rate || 0}%`;
  document.getElementById("origin-country").textContent = product.origin_country || "Not specified";
  document.getElementById("hts-code").textContent = product.hts_code || "Not specified";
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

function showError(message) {
  document.getElementById("detail-loading").style.display = "none";
  document.getElementById("detail-error").style.display = "flex";
  document.getElementById("detail-error-text").textContent = message || "Product not found";
  document.getElementById("product-detail").style.display = "none";
}
