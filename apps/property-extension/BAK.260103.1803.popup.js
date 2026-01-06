// popup.js - Handles popup UI and Notion integration

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
  
  // Load saved API key
  const result = await chrome.storage.sync.get(['notionApiKey']);
  notionApiKey = result.notionApiKey;
  
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
      document.getElementById('capture-btn').innerHTML = '✅ Add to Notion';
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
      'Monitoring Active': { checkbox: true }
    };
    
    if (existingPageId) {
      // UPDATE existing property
      updateStatus('Updating existing property...', 'loading');
      document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Updating...';
      
      // Add Date Updated instead of Date Added
      properties['Date Updated'] = { date: { start: new Date().toISOString().split('T')[0] } };
      
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
        updateStatus('✅ Property updated in Notion!', 'ready');
        document.getElementById('capture-btn').innerHTML = '✅ Updated!';
        
        setTimeout(() => {
          chrome.tabs.create({ url: result.url });
        }, 500);
      } else {
        throw new Error('Failed to update property');
      }
      
    } else {
      // CREATE new property
      updateStatus('Creating new property...', 'loading');
      document.getElementById('capture-btn').innerHTML = '<span class="spinner"></span> Creating...';
      
      properties['Added By'] = { select: { name: 'Dolores' } };
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
            type: 'data_source_id',
            data_source_id: DATA_SOURCE_ID
          },
          properties
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        updateStatus('✅ Property added to Notion!', 'ready');
        document.getElementById('capture-btn').innerHTML = '✅ Added!';
        
        setTimeout(() => {
          chrome.tabs.create({ url: result.url });
        }, 500);
      } else {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create property');
      }
    }
    
  } catch (error) {
    console.error('Error:', error);
    updateStatus('Error: ' + error.message, 'error');
    document.getElementById('capture-btn').disabled = false;
    document.getElementById('capture-btn').innerHTML = '✅ Add to Notion';
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
