/**
 * main.js - Core JavaScript utilities for PriceOrbit
 * for use across all pages (index.html, products.html, future pages)
 */

// ============================================
// CONFIGURATION & SETUP
// ============================================

const PriceOrbit = {
  // Enable/disable debug logging (set to false in production)
  DEBUG: true,
  
  // API base URL 
  API_BASE: '/api',
  
  // Application version
  VERSION: '1.0.0-sprint2'
};

// ============================================
// LOGGING UTILITIES
// ============================================

/**
 * Centralized logging system for debugging
 * Only logs when DEBUG is enabled
 */
const Logger = {
  log: function(message, data = null) {
    if (!PriceOrbit.DEBUG) return;
    console.log(`[PriceOrbit] ${message}`, data || '');
  },
  
  error: function(message, error = null) {
    if (!PriceOrbit.DEBUG) return;
    console.error(`[PriceOrbit ERROR] ${message}`, error || '');
  },
  
  warn: function(message, data = null) {
    if (!PriceOrbit.DEBUG) return;
    console.warn(`[PriceOrbit WARNING] ${message}`, data || '');
  },
  
  success: function(message, data = null) {
    if (!PriceOrbit.DEBUG) return;
    console.log(`%c[PriceOrbit SUCCESS] ${message}`, 'color: green; font-weight: bold;', data || '');
  }
};

// ============================================
// DOM MANIPULATION UTILITIES
// ============================================

/**
 * Simplified DOM selection and manipulation
 * Vanilla JS wrapper for common operations
 */
const DOM = {
  /**
   * Select single element
   * @param {string} selector - CSS selector
   * @returns {Element|null}
   */
  select: function(selector) {
    return document.querySelector(selector);
  },
  
  /**
   * Select multiple elements
   * @param {string} selector - CSS selector
   * @returns {NodeList}
   */
  selectAll: function(selector) {
    return document.querySelectorAll(selector);
  },
  
  /**
   * Add event listener with error handling
   * @param {string} selector - CSS selector
   * @param {string} event - Event name
   * @param {Function} handler - Event handler
   */
  on: function(selector, event, handler) {
    const element = this.select(selector);
    if (element) {
      element.addEventListener(event, handler);
      Logger.log(`Event listener added: ${event} on ${selector}`);
    } else {
      Logger.warn(`Element not found for event binding: ${selector}`);
    }
  },
  
  /**
   * Show element
   * @param {string} selector - CSS selector
   */
  show: function(selector) {
    const element = this.select(selector);
    if (element) {
      element.style.display = '';
    }
  },
  
  /**
   * Hide element
   * @param {string} selector - CSS selector
   */
  hide: function(selector) {
    const element = this.select(selector);
    if (element) {
      element.style.display = 'none';
    }
  },
  
  /**
   * Toggle element visibility
   * @param {string} selector - CSS selector
   */
  toggle: function(selector) {
    const element = this.select(selector);
    if (element) {
      element.style.display = element.style.display === 'none' ? '' : 'none';
    }
  },
  
  /**
   * Add class to element
   * @param {string} selector - CSS selector
   * @param {string} className - Class name to add
   */
  addClass: function(selector, className) {
    const element = this.select(selector);
    if (element) {
      element.classList.add(className);
    }
  },
  
  /**
   * Remove class from element
   * @param {string} selector - CSS selector
   * @param {string} className - Class name to remove
   */
  removeClass: function(selector, className) {
    const element = this.select(selector);
    if (element) {
      element.classList.remove(className);
    }
  }
};

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * General utility functions
 */
const Utils = {
  /**
   * Format currency
   * @param {number} amount - Amount to format
   * @returns {string}
   */
  formatCurrency: function(amount) {
    return `$${parseFloat(amount).toFixed(2)}`;
  },
  
  /**
   * Format date
   * @param {Date|string} date - Date to format
   * @returns {string}
   */
  formatDate: function(date) {
    const d = new Date(date);
    return d.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric' 
    });
  },
  
  /**
   * Debounce function (useful for search inputs)
   * @param {Function} func - Function to debounce
   * @param {number} wait - Wait time in ms
   * @returns {Function}
   */
  debounce: function(func, wait) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  },
  
  /**
   * Simple form validation
   * @param {string} formSelector - Form selector
   * @returns {boolean}
   */
  validateForm: function(formSelector) {
    const form = DOM.select(formSelector);
    if (!form) return false;
    return form.checkValidity();
  }
};

// ============================================
// INITIALIZATION
// ============================================

/**
 * Initialize core functionality when DOM is ready
 */
function initializePriceOrbit() {
  Logger.log('PriceOrbit JavaScript initialized', { version: PriceOrbit.VERSION });
  Logger.log('Using Vanilla JavaScript (no jQuery)');
  
  // Add any global event listeners here
  // Example: Track navigation clicks for analytics (Sprint 2-4)
  
  Logger.success('Core utilities loaded successfully');
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializePriceOrbit);
} else {
  // DOM is already ready
  initializePriceOrbit();
}

// ============================================
// EXPORT FOR USE IN OTHER FILES
// ============================================

// Make utilities available globally
window.PriceOrbit = PriceOrbit;
window.Logger = Logger;
window.DOM = DOM;
window.Utils = Utils;

// ============================================
// MOBILE NAVIGATION - Ticket #52
// ============================================

function initMobileNav() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;

  // Create overlay
  const overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);

  // Create hamburger button and inject into topbar
  const topbarInner = document.querySelector('.topbar-inner');
  if (topbarInner) {
    const hamburger = document.createElement('button');
    hamburger.className = 'hamburger';
    hamburger.setAttribute('aria-label', 'Toggle navigation');
    hamburger.innerHTML = '<i class="fa-solid fa-bars"></i>';
    topbarInner.insertBefore(hamburger, topbarInner.firstChild);

    function openSidebar() {
      sidebar.classList.add('open');
      overlay.classList.add('active');
      hamburger.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    }

    function closeSidebar() {
      sidebar.classList.remove('open');
      overlay.classList.remove('active');
      hamburger.innerHTML = '<i class="fa-solid fa-bars"></i>';
    }

    hamburger.addEventListener('click', () => {
      sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
    });

    overlay.addEventListener('click', closeSidebar);

    // Close on sidebar link click (mobile UX)
    sidebar.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth <= 900) closeSidebar();
      });
    });
  }
}

document.addEventListener('DOMContentLoaded', initMobileNav);