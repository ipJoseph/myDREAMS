/**
 * DREAMS Property Scraper - Popup Controller
 */

// ============================================
// STATE
// ============================================

let currentProperty = null;
let searchResults = [];
let selectedResults = new Set();

// ============================================
// DOM ELEMENTS
// ============================================

const elements = {
  // States
  loadingState: document.getElementById('loadingState'),
  errorState: document.getElementById('errorState'),
  propertyView: document.getElementById('propertyView'),
  searchView: document.getElementById('searchView'),
  settingsPanel: document.getElementById('settingsPanel'),
  unsupportedView: document.getElementById('unsupportedView'),

  // Status
  statusDot: document.getElementById('statusDot'),
  statusText: document.getElementById('statusText'),
  sourceBadge: document.getElementById('sourceBadge'),
  queueBadge: document.getElementById('queueBadge'),

  // Property fields
  propertyAddress: document.getElementById('propertyAddress'),
  propertyPrice: document.getElementById('propertyPrice'),
  confidenceBadge: document.getElementById('confidenceBadge'),
  fieldBeds: document.getElementById('fieldBeds'),
  fieldBaths: document.getElementById('fieldBaths'),
  fieldSqft: document.getElementById('fieldSqft'),
  fieldLot: document.getElementById('fieldLot'),
  fieldYear: document.getElementById('fieldYear'),
  fieldDOM: document.getElementById('fieldDOM'),
  fieldMLS: document.getElementById('fieldMLS'),
  fieldAgent: document.getElementById('fieldAgent'),
  fieldAgentPhone: document.getElementById('fieldAgentPhone'),
  fieldAgentEmail: document.getElementById('fieldAgentEmail'),
  fieldBrokerage: document.getElementById('fieldBrokerage'),
  fieldViews: document.getElementById('fieldViews'),
  fieldFavorites: document.getElementById('fieldFavorites'),
  fieldMLSSource: document.getElementById('fieldMLSSource'),
  fieldParcelID: document.getElementById('fieldParcelID'),
  fieldLatitude: document.getElementById('fieldLatitude'),
  fieldLongitude: document.getElementById('fieldLongitude'),

  // Form
  addedBy: document.getElementById('addedBy'),
  addedFor: document.getElementById('addedFor'),
  saveBtn: document.getElementById('saveBtn'),
  saveMessage: document.getElementById('saveMessage'),

  // Search
  resultCount: document.getElementById('resultCount'),
  searchResults: document.getElementById('searchResults'),
  selectAllBtn: document.getElementById('selectAllBtn'),
  quickAddBtn: document.getElementById('quickAddBtn'),
  deepScrapeBtn: document.getElementById('deepScrapeBtn'),
  bulkProgress: document.getElementById('bulkProgress'),
  bulkProgressFill: document.getElementById('bulkProgressFill'),
  bulkStatus: document.getElementById('bulkStatus'),
  searchAddedBy: document.getElementById('searchAddedBy'),
  searchAddedFor: document.getElementById('searchAddedFor'),

  // Settings
  serverUrl: document.getElementById('serverUrl'),
  apiKey: document.getElementById('apiKey'),
  defaultAddedBy: document.getElementById('defaultAddedBy'),
  saveSettingsBtn: document.getElementById('saveSettingsBtn'),
  testConnectionBtn: document.getElementById('testConnectionBtn'),
  settingsMessage: document.getElementById('settingsMessage'),

  // Buttons
  popOutBtn: document.getElementById('popOutBtn'),
  refreshBtn: document.getElementById('refreshBtn'),
  settingsBtn: document.getElementById('settingsBtn'),
  closeSettingsBtn: document.getElementById('closeSettingsBtn'),

  // Error
  errorMessage: document.getElementById('errorMessage')
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await updateServerStatus();
  await updateQueueBadge();
  await loadPageData();

  setupEventListeners();
});

async function loadSettings() {
  const settings = await chrome.storage.sync.get([
    'serverUrl',
    'apiKey',
    'defaultAddedBy',
    'lastAddedFor'
  ]);

  if (settings.serverUrl) {
    elements.serverUrl.value = settings.serverUrl;
  }
  if (settings.apiKey) {
    elements.apiKey.value = settings.apiKey;
  }
  if (settings.defaultAddedBy) {
    elements.addedBy.value = settings.defaultAddedBy;
    elements.searchAddedBy.value = settings.defaultAddedBy;
    elements.defaultAddedBy.value = settings.defaultAddedBy;
  }
  if (settings.lastAddedFor) {
    elements.addedFor.value = settings.lastAddedFor;
    elements.searchAddedFor.value = settings.lastAddedFor;
  }
}

// Check if running in popout mode
const isPopout = new URLSearchParams(window.location.search).get('popout') === 'true';

function setupEventListeners() {
  // Header buttons
  elements.popOutBtn.addEventListener('click', () => popOutWindow());
  elements.refreshBtn.addEventListener('click', () => loadPageData());
  elements.settingsBtn.addEventListener('click', () => showSettings());
  elements.closeSettingsBtn.addEventListener('click', () => hideSettings());

  // Hide pop-out button if already in popout mode
  if (isPopout) {
    elements.popOutBtn.style.display = 'none';
  }

  // Save button
  elements.saveBtn.addEventListener('click', () => saveProperty());

  // Settings
  elements.saveSettingsBtn.addEventListener('click', () => saveSettings());
  elements.testConnectionBtn.addEventListener('click', () => testConnection());

  // Search results
  elements.selectAllBtn.addEventListener('click', () => toggleSelectAll());
  elements.quickAddBtn.addEventListener('click', () => quickAddSelected());
  elements.deepScrapeBtn.addEventListener('click', () => deepScrapeSelected());

  // Listen for background messages
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Use setTimeout to avoid blocking the message channel
    setTimeout(() => {
      if (message.type === 'QUEUE_ITEM_PROCESSED' || message.type === 'QUEUE_ITEM_FAILED') {
        updateQueueBadge();
      }

      // Handle batch progress updates
      if (message.type === 'BATCH_PROGRESS' && message.data) {
        const { current, total, property, status, error } = message.data;

        // Update progress bar
        const percent = (current / total) * 100;
        elements.bulkProgressFill.style.width = `${percent}%`;

        // Update status text based on status
        if (status === 'scraping') {
          elements.bulkStatus.textContent = `Scraping ${current}/${total}: ${property}...`;
        } else if (status === 'saving') {
          elements.bulkStatus.textContent = `Saving ${current}/${total}: ${property}...`;
        } else if (status === 'complete') {
          elements.bulkStatus.textContent = `Completed ${current}/${total}: ${property}`;
        } else if (status === 'failed') {
          elements.bulkStatus.textContent = `Failed ${current}/${total}: ${property} - ${error || 'Unknown error'}`;
        } else if (status === 'done') {
          // Final status handled by deepScrapeSelected response
        }

        // Update individual item status indicator
        updateItemStatus(property, status);
      }
    }, 0);

    // Return false since we're not sending an async response
    return false;
  });
}

// Cache for status indicator elements to avoid repeated DOM queries
let statusIndicatorCache = new Map();

// Update the status indicator for a specific property
function updateItemStatus(address, status) {
  if (!address) return;

  // Use requestAnimationFrame to batch DOM updates
  requestAnimationFrame(() => {
    // Try to find in cache first
    let statusEl = null;
    const cacheKey = address.substring(0, 20);

    if (statusIndicatorCache.has(cacheKey)) {
      statusEl = statusIndicatorCache.get(cacheKey);
    } else {
      // Find the result item by address
      const items = elements.searchResults.querySelectorAll('.result-item');
      for (const item of items) {
        const itemAddress = item.dataset.address;
        if (itemAddress && itemAddress.includes(cacheKey)) {
          statusEl = item.querySelector('.status-indicator');
          if (statusEl) {
            statusIndicatorCache.set(cacheKey, statusEl);
          }
          break;
        }
      }
    }

    if (statusEl) {
      switch (status) {
        case 'scraping':
          statusEl.textContent = '⏳';
          statusEl.title = 'Scraping...';
          break;
        case 'saving':
          statusEl.textContent = '💾';
          statusEl.title = 'Saving...';
          break;
        case 'complete':
          statusEl.textContent = '✓';
          statusEl.title = 'Saved!';
          statusEl.style.color = 'green';
          break;
        case 'failed':
          statusEl.textContent = '✗';
          statusEl.title = 'Failed';
          statusEl.style.color = 'red';
          break;
      }
    }
  });
}

// ============================================
// SOURCE BADGE
// ============================================

function updateSourceBadge(source) {
  const badge = elements.sourceBadge;
  badge.textContent = source;
  badge.className = 'source-badge ' + source.toLowerCase();
}

// ============================================
// SERVER STATUS
// ============================================

async function updateServerStatus() {
  elements.statusDot.className = 'status-dot checking';
  elements.statusText.textContent = 'Checking server...';

  try {
    const response = await chrome.runtime.sendMessage({ type: 'GET_SERVER_STATUS' });
    const status = response.status;

    elements.statusDot.className = `status-dot ${status}`;
    elements.statusText.textContent = status === 'online' ? 'Server connected' : 'Server offline (queuing)';
  } catch (e) {
    elements.statusDot.className = 'status-dot offline';
    elements.statusText.textContent = 'Connection error';
  }
}

async function updateQueueBadge() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'GET_QUEUE' });
    const queue = response.queue || [];
    const pending = queue.filter(q => q.status === 'pending').length;

    if (pending > 0) {
      elements.queueBadge.textContent = `${pending} queued`;
      elements.queueBadge.classList.remove('hidden');
    } else {
      elements.queueBadge.classList.add('hidden');
    }
  } catch (e) {
    elements.queueBadge.classList.add('hidden');
  }
}

// ============================================
// PAGE DATA LOADING
// ============================================

async function loadPageData() {
  showState('loading');

  try {
    // In popout mode, get data from the stored source tab
    let pageInfo;
    if (isPopout) {
      const { popoutSourceTabId } = await chrome.storage.local.get('popoutSourceTabId');
      if (popoutSourceTabId) {
        try {
          pageInfo = await chrome.tabs.sendMessage(popoutSourceTabId, { type: 'SCRAPE_PROPERTY' });
        } catch (e) {
          pageInfo = { error: 'Source tab no longer available. Please close this window and try again.' };
        }
      } else {
        pageInfo = { error: 'No source tab found. Please close this window and try again.' };
      }
    } else {
      // Normal popup mode - get from active tab
      pageInfo = await chrome.runtime.sendMessage({ type: 'GET_PROPERTY_DATA' });
    }

    console.log('Page info response:', pageInfo);

    // Update source badge
    const source = pageInfo.source || pageInfo.data?.source || 'unknown';
    updateSourceBadge(source);

    // Check if it's a search page first (even if property scrape returned an error)
    if (pageInfo.pageType === 'search') {
      // Try to get search results
      const searchResponse = await chrome.runtime.sendMessage({ type: 'GET_SEARCH_RESULTS' });
      if (searchResponse.data && searchResponse.data.length > 0) {
        searchResults = searchResponse.data;
        displaySearchResults(searchResults);
        showState('search');
        return;
      } else {
        showError('No properties found on this search page. Try scrolling to load more results.');
        return;
      }
    }

    if (pageInfo.error) {
      if (pageInfo.error.includes('not loaded') || pageInfo.error.includes('refresh')) {
        showError('Please refresh the page and try again. The extension needs to load after the page.');
        return;
      }
      showError(pageInfo.error);
      return;
    }

    if (pageInfo.pageType === 'property' && pageInfo.data) {
      currentProperty = pageInfo.data;
      displayProperty(pageInfo.data);
      showState('property');
    } else if (pageInfo.pageType === 'unknown') {
      showError('This page type is not recognized. Navigate to a property detail or search page.');
    } else {
      showState('unsupported');
    }
  } catch (e) {
    console.error('Failed to load page data:', e);
    showError('Please refresh the Zillow/Realtor page. The extension needs to reload.');
  }
}

// ============================================
// DISPLAY FUNCTIONS
// ============================================

function showState(state) {
  elements.loadingState.classList.add('hidden');
  elements.errorState.classList.add('hidden');
  elements.propertyView.classList.add('hidden');
  elements.searchView.classList.add('hidden');
  elements.settingsPanel.classList.remove('active');
  elements.unsupportedView.classList.add('hidden');

  switch (state) {
    case 'loading':
      elements.loadingState.classList.remove('hidden');
      break;
    case 'error':
      elements.errorState.classList.remove('hidden');
      break;
    case 'property':
      elements.propertyView.classList.remove('hidden');
      break;
    case 'search':
      elements.searchView.classList.remove('hidden');
      break;
    case 'unsupported':
      elements.unsupportedView.classList.remove('hidden');
      break;
  }
}

function showError(message) {
  elements.errorMessage.textContent = message;
  showState('error');
}

function displayProperty(data) {
  // Address and price
  elements.propertyAddress.textContent = data.address || 'Unknown Address';
  elements.propertyPrice.textContent = formatPrice(data.price);

  // Confidence badge
  const confidence = data.confidence || 50;
  elements.confidenceBadge.textContent = `${confidence}% complete`;
  elements.confidenceBadge.className = `confidence-badge ${
    confidence >= 80 ? 'high' : confidence >= 50 ? 'medium' : 'low'
  }`;

  // Fields
  elements.fieldBeds.textContent = data.beds || '-';
  elements.fieldBaths.textContent = data.baths || '-';
  elements.fieldSqft.textContent = data.sqft ? formatNumber(data.sqft) : '-';
  elements.fieldLot.textContent = data.lot_acres ? `${data.lot_acres} acres` : '-';
  elements.fieldYear.textContent = data.year_built || '-';
  elements.fieldDOM.textContent = data.days_on_market || '-';
  elements.fieldMLS.textContent = data.mls_number || '-';
  elements.fieldAgent.textContent = data.listing_agent_name || '-';
  elements.fieldAgentPhone.textContent = data.listing_agent_phone || '-';
  elements.fieldAgentEmail.textContent = data.listing_agent_email || '-';
  elements.fieldBrokerage.textContent = data.listing_brokerage || '-';
  elements.fieldViews.textContent = data.page_views ? formatNumber(data.page_views) : '-';
  elements.fieldFavorites.textContent = data.favorites_count ? formatNumber(data.favorites_count) : '-';
  elements.fieldMLSSource.textContent = data.mls_source || '-';
  elements.fieldParcelID.textContent = data.parcel_id || '-';
  elements.fieldLatitude.textContent = data.latitude ? data.latitude.toFixed(6) : '-';
  elements.fieldLongitude.textContent = data.longitude ? data.longitude.toFixed(6) : '-';

  // Mark empty fields
  document.querySelectorAll('.property-field-value').forEach(el => {
    if (el.textContent === '-') {
      el.classList.add('empty');
    } else {
      el.classList.remove('empty');
    }
  });
}

function displaySearchResults(results) {
  elements.resultCount.textContent = results.length;
  selectedResults.clear();
  statusIndicatorCache.clear(); // Clear cache when displaying new results

  elements.searchResults.innerHTML = results.map((result, index) => `
    <div class="result-item" data-index="${index}" data-address="${(result.address || '').replace(/"/g, '&quot;')}">
      <input type="checkbox" class="result-checkbox" data-index="${index}">
      <div class="result-info">
        <div class="result-address">${result.address || 'Unknown'}</div>
        <div class="result-details">
          ${formatPrice(result.price)} · ${result.beds || '?'} bd · ${result.baths || '?'} ba · ${result.sqft ? formatNumber(result.sqft) + ' sqft' : ''}
        </div>
      </div>
      <div class="result-status" data-index="${index}" title="Status">
        <span class="status-indicator">${getQualityIndicator(result)}</span>
      </div>
    </div>
  `).join('');

  // Add checkbox listeners
  elements.searchResults.querySelectorAll('.result-checkbox').forEach(checkbox => {
    checkbox.addEventListener('change', (e) => {
      const index = parseInt(e.target.dataset.index);
      if (e.target.checked) {
        selectedResults.add(index);
      } else {
        selectedResults.delete(index);
      }
      updateBulkButtons();
    });
  });

  // Check which properties already exist in database (async)
  checkExistingProperties(results);
}

function getQualityIndicator(result) {
  // Initial indicator - will be updated after checking database
  // ⏳ = checking, ✓ = new record, ↻ = update existing
  return '⏳';
}

// Check which properties exist in database and update indicators
async function checkExistingProperties(results) {
  try {
    // Check each property against the API
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const indicator = await checkPropertyExists(result);

      // Update the indicator in the DOM
      const statusEl = document.querySelector(`.result-status[data-index="${i}"] .status-indicator`);
      if (statusEl) {
        statusEl.textContent = indicator;
        statusEl.title = indicator === '✓' ? 'New record' : 'Update existing';
      }
    }
  } catch (error) {
    console.error('Error checking existing properties:', error);
  }
}

async function checkPropertyExists(property) {
  try {
    // Check by redfin_id, address, or mls_number
    const params = new URLSearchParams();
    if (property.redfin_id) params.set('redfin_id', property.redfin_id);
    if (property.address) params.set('address', property.address);
    if (property.mls_number) params.set('mls', property.mls_number);

    const response = await fetch(`${CONFIG.SERVER_URL}/api/v1/properties/check?${params}`);
    if (response.ok) {
      const data = await response.json();
      return data.exists ? '↻' : '✓';  // ↻ for update, ✓ for new
    }
    return '?';  // Unknown - API error
  } catch (error) {
    return '?';  // Unknown - network error
  }
}

function updateBulkButtons() {
  const count = selectedResults.size;
  elements.quickAddBtn.disabled = count === 0;
  elements.deepScrapeBtn.disabled = count === 0;
  elements.quickAddBtn.textContent = `Quick Add ${count > 0 ? `(${count})` : 'Selected'}`;
  elements.deepScrapeBtn.textContent = `Deep Scrape ${count > 0 ? `(${count})` : 'Selected'}`;
}

// ============================================
// SAVE FUNCTIONS
// ============================================

async function saveProperty() {
  if (!currentProperty) return;

  elements.saveBtn.disabled = true;
  elements.saveBtn.innerHTML = '<div class="spinner"></div> Saving...';
  elements.saveMessage.classList.add('hidden');

  try {
    // Add user metadata
    currentProperty.added_by = elements.addedBy.value;
    currentProperty.added_for = elements.addedFor.value;

    // Save "Added For" for next time
    await chrome.storage.sync.set({ lastAddedFor: elements.addedFor.value });

    // Send to background
    const response = await chrome.runtime.sendMessage({
      type: 'SAVE_PROPERTY',
      data: currentProperty
    });

    if (response.success) {
      showSaveMessage(
        response.queued
          ? 'Property queued (server offline). Will sync when connected.'
          : 'Property saved successfully!',
        response.queued ? 'warning' : 'success'
      );
      updateQueueBadge();
    } else {
      throw new Error(response.error || 'Save failed');
    }
  } catch (e) {
    showSaveMessage(`Error: ${e.message}`, 'error');
  } finally {
    elements.saveBtn.disabled = false;
    elements.saveBtn.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
      </svg>
      Add to DREAMS
    `;
  }
}

function showSaveMessage(text, type) {
  elements.saveMessage.textContent = text;
  elements.saveMessage.className = `message message-${type}`;
  elements.saveMessage.classList.remove('hidden');

  // Auto-hide success messages
  if (type === 'success') {
    setTimeout(() => {
      elements.saveMessage.classList.add('hidden');
    }, 3000);
  }
}

// ============================================
// BULK OPERATIONS
// ============================================

function toggleSelectAll() {
  const checkboxes = elements.searchResults.querySelectorAll('.result-checkbox');
  const allSelected = selectedResults.size === searchResults.length;

  checkboxes.forEach((checkbox, index) => {
    checkbox.checked = !allSelected;
    if (!allSelected) {
      selectedResults.add(index);
    } else {
      selectedResults.delete(index);
    }
  });

  updateBulkButtons();
  elements.selectAllBtn.textContent = allSelected ? 'Select All' : 'Deselect All';
}

async function quickAddSelected() {
  if (selectedResults.size === 0) return;

  const selected = Array.from(selectedResults).map(i => searchResults[i]);
  const addedBy = elements.searchAddedBy.value;
  const addedFor = elements.searchAddedFor.value;

  // Save "Added For" for next time
  await chrome.storage.sync.set({ lastAddedFor: addedFor });

  elements.bulkProgress.classList.remove('hidden');
  elements.bulkStatus.classList.remove('hidden');

  let processed = 0;
  const total = selected.length;

  for (const result of selected) {
    result.added_by = addedBy;
    result.added_for = addedFor;

    try {
      await chrome.runtime.sendMessage({
        type: 'SAVE_PROPERTY',
        data: result
      });
    } catch (e) {
      console.error('Failed to save:', e);
    }

    processed++;
    elements.bulkProgressFill.style.width = `${(processed / total) * 100}%`;
    elements.bulkStatus.textContent = `Processed ${processed} of ${total}...`;
  }

  elements.bulkStatus.textContent = `Done! Added ${processed} properties.`;
  updateQueueBadge();

  setTimeout(() => {
    elements.bulkProgress.classList.add('hidden');
    elements.bulkStatus.classList.add('hidden');
    elements.bulkProgressFill.style.width = '0%';
  }, 2000);
}

async function deepScrapeSelected() {
  if (selectedResults.size === 0) return;

  const selected = Array.from(selectedResults).map(i => searchResults[i]);
  const addedBy = elements.searchAddedBy.value;
  const addedFor = elements.searchAddedFor.value;

  // Save "Added For" for next time
  await chrome.storage.sync.set({ lastAddedFor: addedFor });

  // Disable buttons during operation
  elements.quickAddBtn.disabled = true;
  elements.deepScrapeBtn.disabled = true;
  elements.deepScrapeBtn.textContent = 'Scraping...';

  // Show progress UI
  elements.bulkProgress.classList.remove('hidden');
  elements.bulkStatus.classList.remove('hidden');
  elements.bulkProgressFill.style.width = '0%';
  elements.bulkStatus.textContent = 'Starting deep scrape...';

  try {
    // Send batch to background for deep scraping
    const response = await chrome.runtime.sendMessage({
      type: 'DEEP_SCRAPE_BATCH',
      properties: selected,
      metadata: {
        added_by: addedBy,
        added_for: addedFor
      }
    });

    if (response.success && response.results) {
      const r = response.results;
      elements.bulkStatus.textContent = `Done! Saved: ${r.saved}, Queued: ${r.queued}, Failed: ${r.failed}`;
      elements.bulkProgressFill.style.width = '100%';
    } else {
      elements.bulkStatus.textContent = 'Deep scrape completed';
    }

    updateQueueBadge();

  } catch (error) {
    console.error('Deep scrape error:', error);
    elements.bulkStatus.textContent = `Error: ${error.message}`;
  } finally {
    // Re-enable buttons
    elements.quickAddBtn.disabled = false;
    elements.deepScrapeBtn.disabled = false;
    updateBulkButtons();

    // Hide progress after delay
    setTimeout(() => {
      elements.bulkProgress.classList.add('hidden');
      elements.bulkStatus.classList.add('hidden');
      elements.bulkProgressFill.style.width = '0%';
    }, 5000);
  }
}

// ============================================
// POP OUT WINDOW
// ============================================

async function popOutWindow() {
  try {
    await chrome.runtime.sendMessage({ type: 'POP_OUT_WINDOW' });
    // Close the current popup
    window.close();
  } catch (e) {
    console.error('Failed to pop out:', e);
  }
}

// ============================================
// SETTINGS
// ============================================

function showSettings() {
  elements.settingsPanel.classList.add('active');
}

function hideSettings() {
  elements.settingsPanel.classList.remove('active');
}

async function saveSettings() {
  const serverUrl = elements.serverUrl.value.trim();
  const apiKey = elements.apiKey.value.trim();
  const defaultAddedBy = elements.defaultAddedBy.value;

  await chrome.storage.sync.set({
    serverUrl,
    apiKey,
    defaultAddedBy
  });

  elements.addedBy.value = defaultAddedBy;
  showSettingsMessage('Settings saved!', 'success');
}

async function testConnection() {
  elements.testConnectionBtn.disabled = true;
  elements.testConnectionBtn.textContent = 'Testing...';

  try {
    const serverUrl = elements.serverUrl.value.trim();
    const response = await fetch(`${serverUrl}/health`);

    if (response.ok) {
      showSettingsMessage('Connection successful!', 'success');
    } else {
      showSettingsMessage(`Server error: ${response.status}`, 'error');
    }
  } catch (e) {
    showSettingsMessage(`Connection failed: ${e.message}`, 'error');
  } finally {
    elements.testConnectionBtn.disabled = false;
    elements.testConnectionBtn.textContent = 'Test Connection';
  }

  await updateServerStatus();
}

function showSettingsMessage(text, type) {
  elements.settingsMessage.textContent = text;
  elements.settingsMessage.className = `message message-${type}`;
  elements.settingsMessage.classList.remove('hidden');

  setTimeout(() => {
    elements.settingsMessage.classList.add('hidden');
  }, 3000);
}

// ============================================
// UTILITIES
// ============================================

function formatPrice(price) {
  if (!price) return '$-';
  return '$' + price.toLocaleString();
}

function formatNumber(num) {
  if (!num) return '-';
  return num.toLocaleString();
}
