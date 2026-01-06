// popup.js - Handles popup UI and Notion integration
// Updated with "Initiated For" and "Added By" fields

const DATA_SOURCE_ID = '54df6a1e-390d-43c6-8023-3e0dc9b87c23';
let propertyData = null;
let notionApiKey = null;

// Load API key and scrape property on popup open
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Popup loaded');
  
  // Set up ALL button handlers FIRST
  document.getElementById('capture-btn').addEventListener('click', captureToNotion);
  document.getElementById('refresh-btn').addEventListener('click', refreshPropertyData);
  document.getElementById('save-config').addEventListener('click', saveConfig);
  document.getElementById('settings-btn').addEventListener('click', toggleConfigSection);
  
  // Load saved settings
  const result = await chrome.storage.sync.get(['notionApiKey', 'defaultAddedBy', 'lastInitiatedFor']);
  notionApiKey = result.notionApiKey;
  
  // Restore last used "Added By" preference
  if (result.defaultAddedBy) {
    document.getElementById('added-by').value = result.defaultAddedBy;
  }
  
  // Optionally restore last "Initiated For" (helpful when researching multiple properties for same lead)
  if (result.lastInitiatedFor) {
    document.getElementById('initiated-for').value = result.lastInitiatedFor;
  }
  
  if (!notionApiKey) {
    showConfigSection();
    updateStatus('Configure your Notion API key below', 'error');
    return;
  }
  
  // Scrape current page
  await refreshPropertyData();
});

async function refreshPropertyData() {
  updateStatus('Detecting property...', 'loading');
  
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    console.log('Current tab URL:', tab.url);
    
    if (!tab.url.match(/zillow|realtor|trulia|homes\.com|smokymountainhomes4sale/)) {
      updateStatus('Not on a supported property site', 'error');
      document.getElementById('capture-btn').disabled = true;
      document.getElementById('capture-btn').innerHTML = '❌ Not on property site';
      document.getElementById('research-context').style.display = 'none';
      return;
    }
    
    // Send message to content script with timeout
    console.log('Sending scrape message to tab:', tab.id);
    
    const response = await Promise.race([
      chrome.tabs.sendMessage(tab.id, { action: 'scrapeProperty' }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 5000))
    ]);
    
    console.log('Received response:', response);
    
    if (response && response.address) {
      propertyData = response;
      displayProperty(response);
      updateStatus('Property detected! Ready to capture', 'ready');
      document.getElementById('capture-btn').disabled = false;
      document.getElementById('capture-btn').innerHTML = '✅ Add to DREAMS';
      document.getElementById('research-context').style.display = 'block';
    } else {
      updateStatus('Could not detect property details', 'error');
      document.getElementById('capture-btn').disabled = true;
      document.getElementById('capture-btn').innerHTML = '❌ No data found';
    }
  } catch (error) {
    console.error('Error scraping:', error);
    updateStatus('Error: ' + error.message, 'error');
    document.getElementById('capture-btn').disabled = true;
    document.getElementById('capture-btn').innerHTML = '❌ Error';
  }
}

function displayProperty(data) {
  document.getElementById('property-preview').style.display = 'block';
  
  let html = `<h3>${data.address || 'Unknown Address'}</h3>`;
  
  const details = [
    { label: 'Price', value: data.price ? `$${data.price.toLocaleString()}` : '—' },
    { label: 'Beds/Baths', value: `${data.bedrooms || '?'} bed / ${data.bathrooms || '?'} bath` },
    { label: 'Sqft', value: data.sqft ? `${data.sqft.toLocaleString()} sqft` : '—' },
    { label: 'Acreage', value: data.acreage ? `${data.acreage} acres` : '—' },
    { label: 'MLS #', value: data.mls_number || '—' },
    { label: 'Year Built', value: data.year_built || '—' },
    { label: 'Style', value: data.style || '—' },
    { label: 'County', value: data.county || '—' },
    { label: 'DOM', value: data.dom ? `${data.dom} days` : '—' },
    { label: 'Status', value: data.status || 'Active' },
    { label: 'Source', value: data.source || 'Unknown' }
  ];
  
  details.forEach(detail => {
    html += `<div class="property-detail"><span>${detail.label}:</span><strong>${detail.value}</strong></div>`;
  });
  
  document.getElementById('property-preview').innerHTML = html;
}

async function captureToNotion() {
  if (!propertyData || !notionApiKey) return;
  
  // Get research context values
  const initiatedFor = document.getElementById('initiated-for').value.trim();
  const addedBy = document.getElementById('added-by').value;
  const openInNotion = document.getElementById('open-in-notion').checked;
  
  // Save preferences for next time
  await chrome.storage.sync.set({ 
    defaultAddedBy: addedBy,
    lastInitiatedFor: initiatedFor  // Remember for multi-property research sessions
  });
  
  updateStatus('Checking for existing property...', 'loading');
  document.getElementById('capture-btn').disabled = true;
  document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Checking...';
  
  try {
    // First, check if property already exists by MLS#
    let existingPageId = null;
    
    if (propertyData.mls_number) {
      const searchResponse = await fetch('https://api.notion.com/v1/databases/' + DATA_SOURCE_ID.replace(/-/g, '') + '/query', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${notionApiKey}`,
          'Content-Type': 'application/json',
          'Notion-Version': '2022-06-28'
        },
        body: JSON.stringify({
          filter: {
            property: 'MLS #',
            rich_text: {
              equals: propertyData.mls_number
            }
          }
        })
      });
      
      if (searchResponse.ok) {
        const searchResults = await searchResponse.json();
        if (searchResults.results && searchResults.results.length > 0) {
          existingPageId = searchResults.results[0].id;
          console.log('Found existing property with MLS#:', propertyData.mls_number);
        }
      }
    }
    
    // Build properties object
    const properties = {
      'Address': {
        title: [{ text: { content: propertyData.address || 'Unknown' } }]
      },
      'Price': propertyData.price ? { number: propertyData.price } : undefined,
      'Bedrooms': propertyData.bedrooms ? { number: propertyData.bedrooms } : undefined,
      'Bathrooms': propertyData.bathrooms ? { number: propertyData.bathrooms } : undefined,
      'Sqft': propertyData.sqft ? { number: propertyData.sqft } : undefined,
      'Acreage': propertyData.acreage ? { number: propertyData.acreage } : undefined,
      'Year Built': propertyData.year_built ? { number: propertyData.year_built } : undefined,
      'Style': propertyData.style ? { select: { name: propertyData.style } } : undefined,
      'County': propertyData.county ? { rich_text: [{ text: { content: propertyData.county } }] } : undefined,
      'Community': propertyData.subdivision ? { rich_text: [{ text: { content: propertyData.subdivision } }] } : undefined,
      'Parcel ID': propertyData.parcel_id ? { rich_text: [{ text: { content: propertyData.parcel_id } }] } : undefined,
      'MLS #': propertyData.mls_number ? { rich_text: [{ text: { content: propertyData.mls_number } }] } : undefined,
      'City': propertyData.city ? { select: { name: propertyData.city } } : undefined,
      'Status': { select: { name: propertyData.status } },
      'Source': { select: { name: propertyData.source } },
      'Zillow URL': propertyData.url ? { url: propertyData.url } : undefined,
      'DOM': propertyData.dom ? { number: propertyData.dom } : undefined,
      'Days on Zillow': propertyData.dom ? { number: propertyData.dom } : undefined,
      'Monitoring Active': { checkbox: true },
      
      // NEW: Research context fields
      'Added By': { select: { name: addedBy } },
    };
    
    // Add "Initiated For" if provided
    if (initiatedFor) {
      properties['Initiated For'] = { 
        rich_text: [{ text: { content: initiatedFor } }] 
      };
    }
    
    if (existingPageId) {
      // UPDATE existing property
      updateStatus('Updating existing property...', 'loading');
      document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Updating...';
      
      // Add Date Updated instead of Date Added
      properties['Date Updated'] = { date: { start: new Date().toISOString().split('T')[0] } };
      
      // If updating for a different lead, we might want to append, not replace
      // For now, we'll replace - can enhance later with multi-lead tracking
      
      const response = await fetch(`https://api.notion.com/v1/pages/${existingPageId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${notionApiKey}`,
          'Content-Type': 'application/json',
          'Notion-Version': '2022-06-28'
        },
        body: JSON.stringify({ properties })
      });
      
      if (response.ok) {
        const result = await response.json();
        updateStatus('✅ Property updated in DREAMS!', 'ready');
        document.getElementById('capture-btn').innerHTML = '✅ Updated!';
        
        if (openInNotion) {
          setTimeout(() => {
            chrome.tabs.create({ url: result.url });
          }, 500);
        }
      } else {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Failed to update property');
      }
      
    } else {
      // CREATE new property
      updateStatus('Creating new property...', 'loading');
      document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Creating...';
      
      properties['Date Added'] = { date: { start: new Date().toISOString().split('T')[0] } };
      
      const response = await fetch('https://api.notion.com/v1/pages', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${notionApiKey}`,
          'Content-Type': 'application/json',
          'Notion-Version': '2022-06-28'
        },
        body: JSON.stringify({
          parent: {
            type: 'database_id',
            database_id: DATA_SOURCE_ID
          },
          properties
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        updateStatus('✅ Property added to DREAMS!', 'ready');
        document.getElementById('capture-btn').innerHTML = '✅ Added!';
        
        if (openInNotion) {
          setTimeout(() => {
            chrome.tabs.create({ url: result.url });
          }, 500);
        }
      } else {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create property');
      }
    }
    
    // Reset button after success (allow adding more properties)
    setTimeout(() => {
      document.getElementById('capture-btn').disabled = false;
      document.getElementById('capture-btn').innerHTML = '✅ Add to DREAMS';
    }, 2000);
    
  } catch (error) {
    console.error('Error:', error);
    updateStatus('Error: ' + error.message, 'error');
    document.getElementById('capture-btn').disabled = false;
    document.getElementById('capture-btn').innerHTML = '✅ Add to DREAMS';
  }
}

function updateStatus(message, type) {
  const statusEl = document.getElementById('status');
  statusEl.className = `status ${type}`;
  
  if (type === 'loading') {
    statusEl.innerHTML = `<span class="spinner"></span> ${message}`;
  } else {
    statusEl.textContent = message;
  }
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
    alert('Please enter a valid Notion API key (starts with ntn_)');
    return;
  }
  
  await chrome.storage.sync.set({ notionApiKey: apiKey });
  notionApiKey = apiKey;
  
  document.getElementById('config-section').style.display = 'none';
  updateStatus('API key saved! Click refresh to detect property', 'ready');
}
