// popup.js - Enhanced Property Capture with Bulk Support
// Handles both single property and search results pages

const DATA_SOURCE_ID = '2eb02656-b6a4-432d-bac1-7d681adbb640';

let pageType = null;
let singlePropertyData = null;
let bulkPropertyData = [];
let selectedIndices = new Set();
let notionApiKey = null;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup loaded');
  
  // Setup event handlers
  setupEventHandlers();
  
  // Load saved settings
  const result = await chrome.storage.sync.get([
    'notionApiKey', 
    'defaultAddedBy', 
    'lastInitiatedFor'
  ]);
  
  notionApiKey = result.notionApiKey;
  
  if (result.defaultAddedBy) {
    document.getElementById('added-by').value = result.defaultAddedBy;
    document.getElementById('bulk-added-by').value = result.defaultAddedBy;
  }
  
  if (result.lastInitiatedFor) {
    document.getElementById('initiated-for').value = result.lastInitiatedFor;
    document.getElementById('bulk-initiated-for').value = result.lastInitiatedFor;
  }
  
  if (!notionApiKey) {
    showConfigSection();
    updateStatus('Configure your Notion API key below', 'error');
    return;
  }
  
  // Detect page and scrape
  await detectAndScrape();
});

function setupEventHandlers() {
  // Header buttons
  document.getElementById('refresh-btn').addEventListener('click', detectAndScrape);
  document.getElementById('settings-btn').addEventListener('click', toggleConfigSection);
  
  // Single property
  document.getElementById('capture-btn').addEventListener('click', captureSingleProperty);
  
  // Bulk actions
  document.getElementById('select-all-btn').addEventListener('click', selectAll);
  document.getElementById('deselect-all-btn').addEventListener('click', deselectAll);
  document.getElementById('bulk-capture-btn').addEventListener('click', captureSelectedProperties);
  document.getElementById('deep-scrape-btn').addEventListener('click', deepScrapeSelected);
  document.getElementById('export-csv-btn').addEventListener('click', exportCSV);
  document.getElementById('copy-data-btn').addEventListener('click', copyData);
  
  // Config
  document.getElementById('save-config').addEventListener('click', saveConfig);
}

// ============================================================================
// PAGE DETECTION & SCRAPING
// ============================================================================
async function detectAndScrape() {
  updateStatus('Detecting page...', 'loading');
  
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab.url.includes('zillow.com')) {
      setMode('error', 'Not on Zillow');
      updateStatus('Please navigate to a Zillow page', 'error');
      return;
    }
    
    // Get page type from content script
    const response = await sendMessage(tab.id, { action: 'getPageType' });
    pageType = response?.pageType || 'unknown';
    
    console.log('Detected page type:', pageType);
    
    if (pageType === 'property') {
      await scrapeSingleProperty(tab.id);
    } else if (pageType === 'search') {
      await scrapeSearchResults(tab.id);
    } else {
      setMode('error', 'Unknown Page');
      updateStatus('Could not detect page type. Try a property or search page.', 'error');
    }
    
  } catch (error) {
    console.error('Error:', error);
    setMode('error', 'Error');
    updateStatus('Error: ' + error.message, 'error');
  }
}

async function scrapeSingleProperty(tabId) {
  setMode('property', 'Property Detail Page');
  updateStatus('Scraping property data...', 'loading');
  
  const data = await sendMessage(tabId, { action: 'scrapeProperty' });
  
  if (data && data.address) {
    singlePropertyData = data;
    displaySingleProperty(data);
    updateStatus('Property detected! Ready to capture', 'ready');
    document.getElementById('capture-btn').disabled = false;
  } else {
    updateStatus('Could not extract property data', 'error');
    document.getElementById('capture-btn').disabled = true;
  }
}

async function scrapeSearchResults(tabId) {
  setMode('search', 'Search Results Page');
  updateStatus('Scraping search results...', 'loading');
  
  const data = await sendMessage(tabId, { action: 'scrapeSearchResults' });
  
  if (data && data.length > 0) {
    bulkPropertyData = data;
    displayBulkResults(data);
    updateStatus(`Found ${data.length} properties`, 'ready');
    selectAll(); // Select all by default
  } else {
    updateStatus('No properties found on this page', 'error');
  }
}

// ============================================================================
// DISPLAY FUNCTIONS
// ============================================================================
function setMode(mode, label) {
  const banner = document.getElementById('mode-banner');
  const singleView = document.getElementById('single-property-view');
  const bulkView = document.getElementById('bulk-results-view');
  
  banner.className = `mode-banner ${mode}-mode`;
  
  if (mode === 'property') {
    banner.innerHTML = '🏠 ' + label;
    singleView.style.display = 'block';
    bulkView.style.display = 'none';
  } else if (mode === 'search') {
    banner.innerHTML = '🔍 ' + label;
    singleView.style.display = 'none';
    bulkView.style.display = 'block';
  } else {
    banner.innerHTML = '⚠️ ' + label;
    singleView.style.display = 'none';
    bulkView.style.display = 'none';
  }
}

function displaySingleProperty(data) {
  const preview = document.getElementById('property-preview');
  
  let html = `<h3>${data.address || 'Unknown Address'}</h3>`;
  html += '<div class="property-grid">';
  
  const fields = [
    ['Price', data.price ? `$${data.price.toLocaleString()}` : '—'],
    ['Beds/Baths', `${data.bedrooms || '?'} bd / ${data.bathrooms || '?'} ba`],
    ['Sqft', data.sqft ? `${data.sqft.toLocaleString()}` : '—'],
    ['Acreage', data.lotAcres ? `${data.lotAcres.toFixed(2)} ac` : '—'],
    ['Year Built', data.yearBuilt || '—'],
    ['Style', data.homeType || '—'],
    ['DOM', data.daysOnZillow ? `${data.daysOnZillow} days` : '—'],
    ['HOA', data.hoaFee ? `$${data.hoaFee}/mo` : '—'],
    ['MLS #', data.mlsId || '—'],
    ['MLS Source', data.mlsSource || '—'],
    ['Parcel ID', data.parcelId || '—'],
    ['County', data.county || '—'],
    ['Agent', data.agentName || '—'],
    ['Agent Phone', data.agentPhone || '—'],
    ['Agent Email', data.agentEmail || '—'],
    ['Broker', data.brokerName || '—'],
    ['Lat/Long', data.latitude ? `${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)}` : '—'],
    ['Status', data.homeStatus || '—'],
    ['Zestimate', data.zestimate ? `$${data.zestimate.toLocaleString()}` : '—'],
    ['Zillow Views', data.pageViewCount || '—'],
    ['Zillow Saves', data.favoriteCount || '—'],
    ['Last Sale', data.lastSalePrice ? `$${data.lastSalePrice.toLocaleString()} (${data.lastSaleDate || '?'})` : '—'],
    ['Last Tax Paid', data.lastTaxPaid ? `$${data.lastTaxPaid.toLocaleString()}` : '—'],
  ];
  
  fields.forEach(([label, value]) => {
    html += `<div class="property-detail"><span>${label}:</span><strong>${value}</strong></div>`;
  });
  
  html += '</div>';
  preview.innerHTML = html;
}

function displayBulkResults(data) {
  const countEl = document.getElementById('bulk-count');
  const listEl = document.getElementById('bulk-list');
  
  countEl.textContent = `${data.length} Properties Found`;
  
  let html = '';
  data.forEach((prop, idx) => {
    const price = prop.price ? `$${prop.price.toLocaleString()}` : '—';
    const details = [
      prop.bedrooms ? `${prop.bedrooms} bd` : null,
      prop.bathrooms ? `${prop.bathrooms} ba` : null,
      prop.sqft ? `${prop.sqft.toLocaleString()} sqft` : null,
      prop.daysOnZillow ? `${prop.daysOnZillow}d` : null,
    ].filter(Boolean).join(' · ');
    
    // Show data quality indicator
    const hasLatLong = prop.latitude && prop.longitude;
    const hasMls = prop.mlsId;
    const quality = hasMls ? '🟢' : hasLatLong ? '🟡' : '🔴';
    
    html += `
      <div class="property-row" data-index="${idx}">
        <input type="checkbox" data-index="${idx}" checked>
        <div class="property-row-info">
          <div class="property-row-address">${quality} ${prop.address || 'Unknown'}, ${prop.city || ''}</div>
          <div class="property-row-details">${details || 'No details'}</div>
        </div>
        <div class="property-row-price">${price}</div>
      </div>
    `;
  });
  
  // Add legend
  html += `
    <div class="data-legend">
      🟢 Full data (MLS#) · 🟡 Partial (lat/long) · 🔴 Basic only
    </div>
  `;
  
  listEl.innerHTML = html;
  
  // Add checkbox event listeners
  listEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', updateSelectedCount);
  });
  
  updateSelectedCount();
}

function updateSelectedCount() {
  const checkboxes = document.querySelectorAll('#bulk-list input[type="checkbox"]');
  selectedIndices.clear();
  
  checkboxes.forEach(cb => {
    if (cb.checked) {
      selectedIndices.add(parseInt(cb.dataset.index));
    }
  });
  
  const quickBtn = document.getElementById('bulk-capture-btn');
  const deepBtn = document.getElementById('deep-scrape-btn');
  const count = selectedIndices.size;
  
  quickBtn.disabled = count === 0;
  deepBtn.disabled = count === 0;
  
  quickBtn.textContent = `⚡ Quick Add ${count > 0 ? count : 'Selected'}`;
  deepBtn.textContent = `🔍 Deep Scrape ${count > 0 ? count : 'Selected'}`;
}

function selectAll() {
  document.querySelectorAll('#bulk-list input[type="checkbox"]').forEach(cb => {
    cb.checked = true;
  });
  updateSelectedCount();
}

function deselectAll() {
  document.querySelectorAll('#bulk-list input[type="checkbox"]').forEach(cb => {
    cb.checked = false;
  });
  updateSelectedCount();
}

// ============================================================================
// CAPTURE TO NOTION
// ============================================================================
async function captureSingleProperty() {
  if (!singlePropertyData || !notionApiKey) return;
  
  const initiatedFor = document.getElementById('initiated-for').value.trim();
  const addedBy = document.getElementById('added-by').value;
  const openInNotion = document.getElementById('open-in-notion').checked;
  
  // Save preferences
  await chrome.storage.sync.set({ 
    defaultAddedBy: addedBy,
    lastInitiatedFor: initiatedFor
  });
  
  document.getElementById('capture-btn').disabled = true;
  document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Saving...';
  
  try {
    const result = await savePropertyToNotion(singlePropertyData, initiatedFor, addedBy);
    
    updateStatus('✅ Property saved to DREAMS!', 'ready');
    document.getElementById('capture-btn').innerHTML = '✅ Saved!';
    
    if (openInNotion && result.url) {
      setTimeout(() => chrome.tabs.create({ url: result.url }), 500);
    }
    
  } catch (error) {
    updateStatus('Error: ' + error.message, 'error');
    document.getElementById('capture-btn').innerHTML = '✅ Add to DREAMS';
    document.getElementById('capture-btn').disabled = false;
  }
}

async function captureSelectedProperties() {
  if (selectedIndices.size === 0 || !notionApiKey) return;
  
  const initiatedFor = document.getElementById('bulk-initiated-for').value.trim();
  const addedBy = document.getElementById('bulk-added-by').value;
  
  // Save preferences
  await chrome.storage.sync.set({ 
    defaultAddedBy: addedBy,
    lastInitiatedFor: initiatedFor
  });
  
  const btn = document.getElementById('bulk-capture-btn');
  btn.disabled = true;
  
  let successCount = 0;
  let errorCount = 0;
  const total = selectedIndices.size;
  
  for (const idx of selectedIndices) {
    btn.innerHTML = `<span class="spinner"></span> Saving ${successCount + errorCount + 1}/${total}...`;
    
    try {
      await savePropertyToNotion(bulkPropertyData[idx], initiatedFor, addedBy);
      successCount++;
    } catch (error) {
      console.error('Error saving property:', error);
      errorCount++;
    }
    
    // Small delay to avoid rate limiting
    await sleep(300);
  }
  
  if (errorCount === 0) {
    updateStatus(`✅ All ${successCount} properties saved!`, 'ready');
    btn.innerHTML = '✅ Complete!';
  } else {
    updateStatus(`Saved ${successCount}, failed ${errorCount}`, 'error');
    btn.innerHTML = `⚡ Quick Add Selected`;
    btn.disabled = false;
  }
}

// ============================================================================
// DEEP SCRAPE - Opens each property page to get full details
// ============================================================================
async function deepScrapeSelected() {
  if (selectedIndices.size === 0 || !notionApiKey) return;
  
  const initiatedFor = document.getElementById('bulk-initiated-for').value.trim();
  const addedBy = document.getElementById('bulk-added-by').value;
  
  // Save preferences
  await chrome.storage.sync.set({ 
    defaultAddedBy: addedBy,
    lastInitiatedFor: initiatedFor
  });
  
  // Disable buttons during scrape
  const deepBtn = document.getElementById('deep-scrape-btn');
  const quickBtn = document.getElementById('bulk-capture-btn');
  deepBtn.disabled = true;
  quickBtn.disabled = true;
  
  // Show progress
  const progressDiv = document.getElementById('scrape-progress');
  const progressFill = document.getElementById('progress-fill');
  const progressText = document.getElementById('progress-text');
  progressDiv.style.display = 'block';
  
  const selectedUrls = [];
  for (const idx of selectedIndices) {
    const prop = bulkPropertyData[idx];
    if (prop.url) {
      selectedUrls.push({ index: idx, url: prop.url, address: prop.address });
    }
  }
  
  const total = selectedUrls.length;
  let successCount = 0;
  let errorCount = 0;
  
  progressText.textContent = `Preparing to scrape ${total} properties...`;
  progressText.className = 'progress-text';
  
  for (let i = 0; i < selectedUrls.length; i++) {
    const { index, url, address } = selectedUrls[i];
    const current = i + 1;
    
    // Update progress
    const percent = Math.round((current / total) * 100);
    progressFill.style.width = `${percent}%`;
    progressText.textContent = `Scraping ${current}/${total}: ${address || 'Loading...'}`;
    
    try {
      // Deep scrape this property
      console.log(`[${current}/${total}] Deep scraping: ${address}`);
      const fullData = await deepScrapeProperty(url);
      
      if (fullData && fullData.address) {
        // Save to Notion
        progressText.textContent = `Saving ${current}/${total}: ${fullData.address}`;
        console.log(`[${current}/${total}] Saving to Notion: ${fullData.address}`);
        
        try {
          await savePropertyToNotion(fullData, initiatedFor, addedBy);
          successCount++;
          console.log(`[${current}/${total}] ✅ Saved: ${fullData.address}`);
          markRowComplete(index);
        } catch (saveError) {
          console.error(`[${current}/${total}] ❌ Save failed:`, saveError.message);
          progressText.textContent = `Error saving: ${saveError.message.substring(0, 50)}...`;
          errorCount++;
          markRowError(index);
        }
      } else {
        throw new Error('Failed to scrape property data');
      }
    } catch (error) {
      console.error(`[${current}/${total}] ❌ Scrape failed for ${address}:`, error.message);
      errorCount++;
      markRowError(index);
    }
    
    // Small delay between properties
    await sleep(500);
  }
  
  // Complete
  progressFill.style.width = '100%';
  
  if (errorCount === 0) {
    progressText.textContent = `✅ Complete! Scraped and saved ${successCount} properties`;
    progressText.className = 'progress-text success';
  } else {
    progressText.textContent = `Done: ${successCount} saved, ${errorCount} failed`;
    progressText.className = 'progress-text error';
  }
  
  // Re-enable buttons
  deepBtn.innerHTML = '🔍 Deep Scrape Selected';
  deepBtn.disabled = false;
  quickBtn.disabled = false;
}

async function deepScrapeProperty(url) {
  return new Promise(async (resolve, reject) => {
    let tab = null;
    try {
      console.log('Deep scraping:', url);
      
      // Open the property page in a new background tab
      tab = await chrome.tabs.create({ 
        url: url, 
        active: false  // Keep in background
      });
      
      console.log('Tab created:', tab.id);
      
      // Wait for page to load
      await waitForTabLoad(tab.id);
      console.log('Tab loaded, waiting for content...');
      
      // Wait for JavaScript to render - Zillow needs time
      await sleep(3000);
      
      // Try to get data with retries
      let data = null;
      let attempts = 0;
      const maxAttempts = 3;
      
      while (!data && attempts < maxAttempts) {
        attempts++;
        console.log(`Scrape attempt ${attempts}/${maxAttempts}`);
        
        data = await sendMessage(tab.id, { action: 'scrapeProperty' });
        
        if (!data || !data.address) {
          if (attempts < maxAttempts) {
            console.log('No data, waiting and retrying...');
            await sleep(1500);
          }
          data = null;
        }
      }
      
      // Close the tab
      await chrome.tabs.remove(tab.id);
      console.log('Tab closed');
      
      if (data && data.address) {
        console.log('Scraped:', data.address, data.mlsId);
        resolve(data);
      } else {
        reject(new Error('No data returned after ' + maxAttempts + ' attempts'));
      }
    } catch (error) {
      console.error('Deep scrape error:', error);
      // Try to close tab if it exists
      if (tab) {
        try { await chrome.tabs.remove(tab.id); } catch (e) {}
      }
      reject(error);
    }
  });
}

function waitForTabLoad(tabId) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Tab load timeout'));
    }, 30000); // 30 second timeout
    
    const listener = (updatedTabId, changeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    
    chrome.tabs.onUpdated.addListener(listener);
  });
}

function markRowComplete(index) {
  const row = document.querySelector(`.property-row[data-index="${index}"]`);
  if (row) {
    row.style.background = '#e8f5e9';
    const checkbox = row.querySelector('input[type="checkbox"]');
    if (checkbox) {
      checkbox.checked = false;
      checkbox.disabled = true;
    }
  }
}

function markRowError(index) {
  const row = document.querySelector(`.property-row[data-index="${index}"]`);
  if (row) {
    row.style.background = '#ffebee';
  }
}

async function savePropertyToNotion(propertyData, initiatedFor, addedBy) {
  // Check for existing property by MLS# or address
  let existingPageId = null;
  
  if (propertyData.mlsId) {
    existingPageId = await findExistingProperty('MLS #', propertyData.mlsId);
    if (existingPageId) {
      console.log('Found existing property by MLS#:', propertyData.mlsId);
    }
  }
  
  const properties = buildNotionProperties(propertyData, initiatedFor, addedBy, !!existingPageId);
  
  // Remove properties that might not exist in the database to avoid errors
  const safeProperties = {};
  for (const [key, value] of Object.entries(properties)) {
    if (value !== undefined && value !== null) {
      safeProperties[key] = value;
    }
  }
  
  if (existingPageId) {
    // Update existing
    console.log('Updating existing property:', existingPageId);
    const response = await fetch(`https://api.notion.com/v1/pages/${existingPageId}`, {
      method: 'PATCH',
      headers: notionHeaders(),
      body: JSON.stringify({ properties: safeProperties })
    });
    
    if (!response.ok) {
      const error = await response.json();
      console.error('Notion update error:', error);
      // If a property doesn't exist, try again without that property
      if (error.message && error.message.includes('property does not exist')) {
        const badProp = error.message.match(/property "([^"]+)"/)?.[1];
        if (badProp) {
          console.log('Removing bad property:', badProp);
          delete safeProperties[badProp];
          const retryResponse = await fetch(`https://api.notion.com/v1/pages/${existingPageId}`, {
            method: 'PATCH',
            headers: notionHeaders(),
            body: JSON.stringify({ properties: safeProperties })
          });
          if (retryResponse.ok) {
            return await retryResponse.json();
          }
        }
      }
      throw new Error(error.message || 'Failed to update property');
    }
    return await response.json();
    
  } else {
    // Create new
    console.log('Creating new property');
    const response = await fetch('https://api.notion.com/v1/pages', {
      method: 'POST',
      headers: notionHeaders(),
      body: JSON.stringify({
        parent: { type: 'database_id', database_id: DATA_SOURCE_ID },
        properties: safeProperties
      })
    });
    
    if (!response.ok) {
      const error = await response.json();
      console.error('Notion create error:', error);
      // If a property doesn't exist, try again without that property
      if (error.message && error.message.includes('property does not exist')) {
        const badProp = error.message.match(/property "([^"]+)"/)?.[1];
        if (badProp) {
          console.log('Removing bad property:', badProp);
          delete safeProperties[badProp];
          const retryResponse = await fetch('https://api.notion.com/v1/pages', {
            method: 'POST',
            headers: notionHeaders(),
            body: JSON.stringify({
              parent: { type: 'database_id', database_id: DATA_SOURCE_ID },
              properties: safeProperties
            })
          });
          if (retryResponse.ok) {
            return await retryResponse.json();
          }
        }
      }
      throw new Error(error.message || 'Failed to create property');
    }
    return await response.json();
  }
}

async function findExistingProperty(field, value) {
  try {
    const response = await fetch(`https://api.notion.com/v1/databases/${DATA_SOURCE_ID.replace(/-/g, '')}/query`, {
      method: 'POST',
      headers: notionHeaders(),
      body: JSON.stringify({
        filter: { property: field, rich_text: { equals: value } }
      })
    });
    
    if (response.ok) {
      const results = await response.json();
      if (results.results?.length > 0) {
        return results.results[0].id;
      }
    }
  } catch (e) {
    console.log('Error checking for existing property:', e);
  }
  return null;
}

function buildNotionProperties(data, initiatedFor, addedBy, isUpdate) {
  const props = {
    'Address': { title: [{ text: { content: data.address || 'Unknown' } }] },
    'Added By': { select: { name: addedBy } },
  };
  
  // Numbers
  if (data.price) props['Price'] = { number: data.price };
  if (data.bedrooms) props['Bedrooms'] = { number: data.bedrooms };
  if (data.bathrooms) props['Bathrooms'] = { number: data.bathrooms };
  if (data.sqft) props['Sqft'] = { number: data.sqft };
  if (data.lotAcres) props['Acreage'] = { number: data.lotAcres };
  if (data.yearBuilt) props['Year Built'] = { number: data.yearBuilt };
  if (data.daysOnZillow) props['DOM'] = { number: data.daysOnZillow };
  if (data.daysOnZillow) props['Days on Zillow'] = { number: data.daysOnZillow };
  if (data.latitude) props['Latitude'] = { number: data.latitude };
  if (data.longitude) props['Longitude'] = { number: data.longitude };
  if (data.zestimate) props['Zestimate'] = { number: data.zestimate };
  if (data.pageViewCount) props['Zillow Views'] = { number: data.pageViewCount };
  if (data.favoriteCount) props['Zillow Saves'] = { number: data.favoriteCount };
  if (data.hoaFee) props['HOA'] = { number: data.hoaFee };
  if (data.lastSalePrice) props['Last Sale Price'] = { number: data.lastSalePrice };
  if (data.lastTaxPaid) props['Last Tax Paid'] = { number: data.lastTaxPaid };
  
  // Text fields
  if (data.mlsId) props['MLS #'] = { rich_text: [{ text: { content: data.mlsId } }] };
  if (data.mlsSource) props['MLS Source'] = { rich_text: [{ text: { content: data.mlsSource } }] };
  if (data.parcelId) props['Parcel ID'] = { rich_text: [{ text: { content: data.parcelId } }] };
  if (data.agentName) props['Agent Name'] = { rich_text: [{ text: { content: data.agentName } }] };
  if (data.agentPhone) props['Agent Phone'] = { rich_text: [{ text: { content: data.agentPhone } }] };
  if (data.brokerName) props['Broker'] = { rich_text: [{ text: { content: data.brokerName } }] };
  
  // County is rich_text in Notion - validate it's not garbage like "the"
  if (data.county && data.county.length >= 3 && !['the', 'this', 'that'].includes(data.county.toLowerCase())) {
    props['County'] = { rich_text: [{ text: { content: data.county } }] };
  }
  
  // Email field - Notion email type
  if (data.agentEmail) props['Agent Email'] = { email: data.agentEmail };
  
  // "Added For" field (formerly "Initiated For" / "Researching For")
  if (initiatedFor) props['Added For'] = { rich_text: [{ text: { content: initiatedFor } }] };
  
  // Selects
  if (data.city) props['City'] = { select: { name: data.city } };
  if (data.homeStatus) props['Status'] = { select: { name: formatStatus(data.homeStatus) } };
  if (data.homeType) props['Style'] = { select: { name: formatHomeType(data.homeType) } };
  props['Source'] = { select: { name: 'Zillow' } };
  
  // URL
  if (data.url) props['Zillow URL'] = { url: data.url };
  
  // Dates - Always set Last Updated, only set Date Created on new records
  const today = new Date().toISOString().split('T')[0];
  props['Last Updated'] = { date: { start: today } };
  
  if (!isUpdate) {
    props['Date Created'] = { date: { start: today } };
  }
  
  // Last Sale Date
  if (data.lastSaleDate) {
    props['Last Sale Date'] = { date: { start: data.lastSaleDate } };
  }
  
  // Monitoring
  props['Monitoring Active'] = { checkbox: true };
  
  return props;
}

function formatStatus(status) {
  if (!status) return 'Active';
  const statusMap = {
    'FOR_SALE': 'Active',
    'PENDING': 'Pending',
    'SOLD': 'Sold',
    'RECENTLY_SOLD': 'Sold',
    'OFF_MARKET': 'Off Market'
  };
  return statusMap[status] || status;
}

function formatHomeType(homeType) {
  if (!homeType) return 'Unknown';
  const typeMap = {
    'SINGLE_FAMILY': 'Single Family',
    'MULTI_FAMILY': 'Multi-Family',
    'CONDO': 'Condo',
    'TOWNHOUSE': 'Townhouse',
    'MANUFACTURED': 'Manufactured',
    'LOT': 'Lot/Land',
    'LAND': 'Lot/Land',
    'APARTMENT': 'Apartment'
  };
  return typeMap[homeType] || homeType;
}

function notionHeaders() {
  return {
    'Authorization': `Bearer ${notionApiKey}`,
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
  };
}

// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================
function exportCSV() {
  const selected = Array.from(selectedIndices).map(i => bulkPropertyData[i]);
  if (selected.length === 0) {
    alert('No properties selected');
    return;
  }
  
  const headers = [
    'Address', 'City', 'State', 'Zip', 'Price', 'Beds', 'Baths', 'Sqft', 
    'Acreage', 'Year Built', 'DOM', 'MLS #', 'Parcel ID', 'Agent', 
    'Broker', 'Latitude', 'Longitude', 'Status', 'URL'
  ];
  
  const rows = selected.map(p => [
    p.address, p.city, p.state, p.zipcode, p.price, p.bedrooms, p.bathrooms,
    p.sqft, p.lotAcres, p.yearBuilt, p.daysOnZillow, p.mlsId, p.parcelId,
    p.agentName, p.brokerName, p.latitude, p.longitude, p.homeStatus, p.url
  ]);
  
  let csv = headers.join(',') + '\n';
  rows.forEach(row => {
    csv += row.map(v => `"${(v || '').toString().replace(/"/g, '""')}"`).join(',') + '\n';
  });
  
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  
  chrome.downloads.download({
    url: url,
    filename: `zillow-properties-${Date.now()}.csv`
  });
}

function copyData() {
  const selected = Array.from(selectedIndices).map(i => bulkPropertyData[i]);
  if (selected.length === 0) {
    alert('No properties selected');
    return;
  }
  
  const text = JSON.stringify(selected, null, 2);
  navigator.clipboard.writeText(text).then(() => {
    updateStatus('Data copied to clipboard!', 'ready');
  });
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
function updateStatus(message, type) {
  const el = document.getElementById('status');
  el.className = `status ${type}`;
  el.innerHTML = type === 'loading' 
    ? `<span class="spinner"></span> ${message}` 
    : message;
}

function showConfigSection() {
  document.getElementById('config-section').style.display = 'block';
}

function toggleConfigSection() {
  const section = document.getElementById('config-section');
  section.style.display = section.style.display === 'none' ? 'block' : 'none';
}

async function saveConfig() {
  const apiKey = document.getElementById('api-key').value.trim();
  
  if (!apiKey || !apiKey.startsWith('ntn_')) {
    alert('Please enter a valid Notion API key');
    return;
  }
  
  await chrome.storage.sync.set({ notionApiKey: apiKey });
  notionApiKey = apiKey;
  
  document.getElementById('config-section').style.display = 'none';
  updateStatus('API key saved! Click refresh', 'ready');
}

async function sendMessage(tabId, message) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        console.log('Message error:', chrome.runtime.lastError.message);
        resolve(null);
      } else {
        resolve(response);
      }
    });
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
