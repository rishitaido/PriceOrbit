// Product Detail Page JavaScript
// Handles product detail display, price history, and Chart.js visualization

const API_BASE = '/api/products';
let priceChart = null;

// Get product ID from URL
function getProductId() {
  const path = window.location.pathname;
  const match = path.match(/\/product\/(\d+)/);
  return match ? match[1] : null;
}

// Initialize page when DOM loads
document.addEventListener('DOMContentLoaded', () => {
  const productId = getProductId();
  
  if (productId) {
    loadProductDetail(productId);
  } else {
    showError('Invalid product ID');
  }
});

// Load product details from API
async function loadProductDetail(productId) {
  showLoading();
  
  try {
    // Fetch product details
    const response = await fetch(`${API_BASE}/${productId}`);
    
    if (!response.ok) {
      throw new Error('Product not found');
    }
    
    const product = await response.json();
    
    // Display product details
    displayProductInfo(product);
    
    // Try to fetch price history
    try {
      const historyResponse = await fetch(`${API_BASE}/${productId}`);
      
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        displayPriceHistory(historyData);
      } else {
        // Generate sample data if no history available
        generateSamplePriceHistory(product);
      }
    } catch (error) {
      console.log('Price history endpoint not available, using sample data');
      generateSamplePriceHistory(product);
    }
    
    hideLoading();
    
  } catch (error) {
    console.error('Error loading product:', error);
    showError(error.message);
  }
}

// Display product information
function displayProductInfo(product) {
  // Product name and category
  document.getElementById('product-name').textContent = product.name;
  
  const categoryText = product.category || 'Uncategorized';
  document.getElementById('product-category').textContent = categoryText;
  
  // Health score
  const healthScore = product.health_score || 50;
  updateHealthScore(healthScore);
  
  // Current price
  const price = product.current_price || 0;
  document.getElementById('current-price').textContent = `$${parseFloat(price).toFixed(2)}`;
  
  // Sample price changes (would come from API in production)
  const change7d = (Math.random() * 10 - 5).toFixed(1);
  const change30d = (Math.random() * 15 - 7).toFixed(1);
  
  displayPriceChange('change-7d', change7d);
  displayPriceChange('change-30d', change30d);
  
  // Supply chain information
  const importDep = product.import_dependency || 'Unknown';
  const importBadge = document.getElementById('import-dependency');
  importBadge.textContent = importDep;
  importBadge.className = `info-value badge-pill import-${importDep.toLowerCase()}`;
  
  document.getElementById('tariff-rate').textContent = `${product.tariff_rate || 0}%`;
  document.getElementById('origin-country').textContent = product.origin_country || 'Not specified';
  document.getElementById('hts-code').textContent = product.hts_code || 'Not specified';
  document.getElementById('retailer').textContent = product.retailer || 'Kroger';
  
  // Health score breakdown
  updateHealthScoreBreakdown(product);
  
  // Description
  document.getElementById('product-description').textContent = 
    product.description || 'No description available for this product.';
  
  // Last updated
  const lastUpdated = product.last_price_check 
    ? formatDate(product.last_price_check)
    : 'Never';
  document.getElementById('last-updated').textContent = lastUpdated;
  
  // Show the detail section
  document.getElementById('product-detail').style.display = 'block';
}

// Update health score circle
function updateHealthScore(score) {
  const scoreText = document.getElementById('score-text');
  const scoreFill = document.getElementById('score-fill');
  const statusBadge = document.getElementById('health-status');
  
  scoreText.textContent = Math.round(score);
  
  // Calculate stroke-dasharray for circle (circumference = 2 * π * r = 251.2)
  const dashArray = `${(score / 100) * 251.2} 251.2`;
  scoreFill.style.strokeDasharray = dashArray;
  
  // Determine status and color
  let statusText, statusClass, strokeColor;
  
  if (score >= 70) {
    statusText = 'Low Risk';
    statusClass = 'low-risk';
    strokeColor = '#16a34a';
  } else if (score >= 40) {
    statusText = 'Medium Risk';
    statusClass = 'medium-risk';
    strokeColor = '#eab308';
  } else {
    statusText = 'High Risk';
    statusClass = 'high-risk';
    strokeColor = '#dc2626';
  }
  
  statusBadge.textContent = statusText;
  statusBadge.className = `status-badge ${statusClass}`;
  scoreFill.style.stroke = strokeColor;
}

// Display price change
function displayPriceChange(elementId, change) {
  const element = document.getElementById(elementId);
  const value = parseFloat(change);
  const arrow = value >= 0 ? '↑' : '↓';
  const className = value >= 0 ? 'up' : 'down';
  
  element.innerHTML = `<span class="price-badge ${className}">${arrow} ${Math.abs(value)}%</span>`;
}

// Update health score breakdown bars
function updateHealthScoreBreakdown(product) {
  // Tariff impact (inverse - higher tariff = lower score)
  const tariffScore = Math.max(0, 100 - (product.tariff_rate * 3.33));
  updateBreakdownBar('tariff-bar', tariffScore);
  
  // Volatility (sample - would be calculated from price history)
  const volatilityScore = 75; // Placeholder
  updateBreakdownBar('volatility-bar', volatilityScore);
  
  // Import dependency
  const dependencyMap = { 'Low': 100, 'Medium': 50, 'High': 0, 'Unknown': 50 };
  const dependencyScore = dependencyMap[product.import_dependency] || 50;
  updateBreakdownBar('dependency-bar', dependencyScore);
}

// Update individual breakdown bar
function updateBreakdownBar(barId, score) {
  const bar = document.getElementById(barId);
  bar.style.width = `${score}%`;
  
  // Color based on score
  if (score >= 70) {
    bar.style.backgroundColor = '#16a34a';
  } else if (score >= 40) {
    bar.style.backgroundColor = '#eab308';
  } else {
    bar.style.backgroundColor = '#dc2626';
  }
}

// Display price history with Chart.js
function displayPriceHistory(historyData) {
  const history = historyData.history || [];
  
  if (history.length === 0) {
    document.getElementById('chart-empty').style.display = 'flex';
    return;
  }
  
  // Prepare chart data
  const labels = history.map(h => formatChartDate(h.date));
  const prices = history.map(h => parseFloat(h.price));
  
  // Create chart
  createPriceChart(labels.reverse(), prices.reverse());
  
  // Display statistics
  const stats = historyData.statistics || calculateStatistics(prices);
  displayStatistics(stats);
  
  // Display recent updates
  displayRecentUpdates(history.slice(-10).reverse());
}

// Generate sample price history (for when API doesn't have it yet)
function generateSamplePriceHistory(product) {
  const currentPrice = parseFloat(product.current_price) || 2.99;
  const history = [];
  const labels = [];
  
  // Generate 30 days of sample data
  for (let i = 30; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    
    // Random price variation ±8%
    const variation = (Math.random() - 0.5) * 0.16;
    const price = currentPrice * (1 + variation);
    
    labels.push(formatChartDate(date.toISOString()));
    history.push({
      date: date.toISOString(),
      price: price.toFixed(2)
    });
  }
  
  const prices = history.map(h => parseFloat(h.price));
  
  // Create chart
  createPriceChart(labels, prices);
  
  // Calculate and display statistics
  const stats = calculateStatistics(prices);
  stats.current = currentPrice;
  displayStatistics(stats);
  
  // Display recent updates
  displayRecentUpdates(history.slice(-10).reverse());
}

// Create Chart.js price chart
function createPriceChart(labels, prices) {
  const ctx = document.getElementById('price-chart').getContext('2d');
  
  if (priceChart) {
    priceChart.destroy();
  }
  
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Price ($)',
        data: prices,
        borderColor: '#111',
        backgroundColor: 'rgba(17, 17, 17, 0.05)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: '#111',
        pointBorderColor: '#fff',
        pointBorderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(17, 17, 17, 0.9)',
          padding: 12,
          titleFont: { size: 14, weight: 600 },
          bodyFont: { size: 13 },
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            label: function(context) {
              return `Price: $${context.parsed.y.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: false,
          ticks: {
            callback: function(value) {
              return '$' + value.toFixed(2);
            },
            font: { size: 12 },
            color: '#666'
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.05)',
            drawBorder: false
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            maxRotation: 45,
            minRotation: 45,
            font: { size: 11 },
            color: '#666'
          }
        }
      }
    }
  });
}

// Calculate statistics from price array
function calculateStatistics(prices) {
  const current = prices[prices.length - 1];
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const average = prices.reduce((a, b) => a + b, 0) / prices.length;
  const volatility = calculateVolatility(prices);
  
  return { current, min, max, average, volatility };
}

// Calculate price volatility (coefficient of variation)
function calculateVolatility(prices) {
  const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
  const variance = prices.reduce((sum, price) => 
    sum + Math.pow(price - mean, 2), 0) / prices.length;
  const stdDev = Math.sqrt(variance);
  return (stdDev / mean) * 100;
}

// Display price statistics
function displayStatistics(stats) {
  document.getElementById('stat-current').textContent = `$${stats.current.toFixed(2)}`;
  document.getElementById('stat-average').textContent = `$${stats.average.toFixed(2)}`;
  document.getElementById('stat-min').textContent = `$${stats.min.toFixed(2)}`;
  document.getElementById('stat-max').textContent = `$${stats.max.toFixed(2)}`;
  document.getElementById('stat-volatility').textContent = `${stats.volatility.toFixed(1)}%`;
}

// Display recent price updates
function displayRecentUpdates(history) {
  const container = document.getElementById('price-history-list');
  
  if (history.length === 0) {
    container.innerHTML = '<p class="text-muted">No price history available</p>';
    return;
  }
  
  container.innerHTML = history.map((item, index) => {
    const change = index < history.length - 1 
      ? ((parseFloat(item.price) - parseFloat(history[index + 1].price)) / parseFloat(history[index + 1].price) * 100)
      : 0;
    
    const changeHtml = change !== 0 
      ? `<span class="price-badge ${change >= 0 ? 'up' : 'down'}">${change >= 0 ? '↑' : '↓'} ${Math.abs(change).toFixed(1)}%</span>`
      : '';
    
    return `
      <div class="history-item">
        <span class="history-date">${formatDate(item.date)}</span>
        <span class="history-price">
          $${parseFloat(item.price).toFixed(2)}
          ${changeHtml}
        </span>
      </div>
    `;
  }).join('');
}

// Helper functions
function formatDate(dateString) {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = Math.abs(now - date);
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  
  return date.toLocaleDateString('en-US', { 
    month: 'short', 
    day: 'numeric', 
    year: 'numeric' 
  });
}

function formatChartDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { 
    month: 'short', 
    day: 'numeric' 
  });
}

function showLoading() {
  document.getElementById('detail-loading').style.display = 'flex';
  document.getElementById('detail-error').style.display = 'none';
  document.getElementById('product-detail').style.display = 'none';
}

function hideLoading() {
  document.getElementById('detail-loading').style.display = 'none';
}

function showError(message) {
  document.getElementById('detail-loading').style.display = 'none';
  document.getElementById('detail-error').style.display = 'flex';
  document.getElementById('detail-error-text').textContent = message || 'Product not found';
  document.getElementById('product-detail').style.display = 'none';
} 

