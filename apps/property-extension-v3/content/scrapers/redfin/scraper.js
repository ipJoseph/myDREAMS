/**
 * DREAMS Property Scraper - Redfin Module
 * Version 3.9.2 - Improved search results extraction
 */

const REDFIN_VERSION = '3.9.5';

// ============================================
// PAGE TYPE DETECTION
// ============================================
function detectRedfinPageType() {
  const url = window.location.href;
  const path = window.location.pathname;

  // Property detail page patterns
  if (path.includes('/home/') || url.includes('property_id=')) {
    return 'property';
  }

  // Search/filter results
  if (path.includes('/city/') || path.includes('/zipcode/') ||
      path.includes('/neighborhood/') || path.includes('/school/') ||
      url.includes('market=') || url.includes('region_id=')) {
    return 'search';
  }

  return 'unknown';
}

// ============================================
// EXTRACT REDFIN PROPERTY DATA
// ============================================
function scrapeRedfinProperty() {
  console.log('=== REDFIN SCRAPER v' + REDFIN_VERSION + ' ===');
  console.log('URL:', window.location.href);

  let data = initRedfinPropertyData();

  // Method 1: Direct extraction from script content
  console.log('\n[Method 1] Direct script extraction...');
  const directData = extractPropertyFromScripts();
  if (directData) {
    console.log('  Found keys:', Object.keys(directData).filter(k => directData[k] != null));
    data = mergeData(data, normalizeRedfinProperty(directData));
  } else {
    console.log('  No data from direct extraction');
  }

  // Method 2: Look for reactServerState
  console.log('\n[Method 2] React server state...');
  const serverState = extractReactServerState();
  if (serverState) {
    console.log('  Found server state, keys:', Object.keys(serverState).slice(0, 10));
    data = mergeData(data, normalizeRedfinProperty(serverState));
  } else {
    console.log('  No react server state found');
  }

  // Method 3: Look for preloaded data in scripts
  console.log('\n[Method 3] Preload data...');
  const preloadData = extractPreloadData();
  if (preloadData) {
    console.log('  Found preload data');
    data = mergeData(data, normalizeRedfinProperty(preloadData));
  } else {
    console.log('  No preload data found');
  }

  // Method 4: DOM fallback
  console.log('\n[Method 4] DOM scraping...');
  const domData = scrapeRedfinDOM();
  const domFields = Object.keys(domData).filter(k => domData[k] != null);
  console.log('  DOM found:', domFields);
  data = mergeData(data, domData);

  // Set metadata
  data.source = 'redfin';
  data.url = window.location.href;
  data.scraped_at = new Date().toISOString();

  // Extract Redfin property ID from URL
  const propIdMatch = window.location.href.match(/\/home\/(\d+)/);
  if (propIdMatch) {
    data.redfin_id = propIdMatch[1];
  }

  // Parse city/state/zip from address if not already set
  if (data.address && (!data.city || !data.state || !data.zip)) {
    console.log('Parsing address components from:', data.address);
    const addressParts = parseAddressComponents(data.address);
    if (!data.city && addressParts.city) data.city = addressParts.city;
    if (!data.state && addressParts.state) data.state = addressParts.state;
    if (!data.zip && addressParts.zip) data.zip = addressParts.zip;
    console.log('Parsed:', addressParts);
  }

  data.confidence = calculateConfidence(data);

  // Log final results
  console.log('\n=== FINAL SCRAPED DATA ===');
  const populated = {};
  const missing = [];
  for (const [key, val] of Object.entries(data)) {
    if (val !== null && val !== undefined && val !== '' &&
        !(Array.isArray(val) && val.length === 0)) {
      populated[key] = val;
    } else {
      missing.push(key);
    }
  }
  console.log('Populated fields:', Object.keys(populated));
  console.log('Missing fields:', missing);
  console.log('Data:', populated);
  console.log('=== END SCRAPE ===\n');

  return data;
}

// ============================================
// DIRECT EXTRACTION FROM SCRIPTS (New Method)
// ============================================
function extractPropertyFromScripts() {
  console.log('Redfin: Attempting direct script extraction...');

  const scripts = document.querySelectorAll('script:not([src])');

  for (const script of scripts) {
    const text = script.textContent || '';

    // Skip small scripts
    if (text.length < 1000) continue;

    // Look for script with all our target patterns
    if (text.includes('"beds"') && text.includes('"baths"') && text.includes('"streetAddress"')) {
      console.log('Redfin: Found script with property data patterns');

      // Try multiple extraction patterns

      // Pattern 1: Find a complete property-like object
      // Look for {"propertyId":12345, followed by beds, baths, etc
      const patterns = [
        /"propertyId"\s*:\s*(\d+)[\s\S]*?"beds"\s*:\s*(\d+)[\s\S]*?"baths"\s*:\s*([\d.]+)[\s\S]*?"streetAddress"\s*:\s*"([^"]+)"/,
        /"listingId"\s*:\s*(\d+)[\s\S]*?"beds"\s*:\s*(\d+)[\s\S]*?"baths"\s*:\s*([\d.]+)/,
      ];

      // Extract individual fields using targeted regex
      const extracted = {};

      // Property/Listing ID
      let match = text.match(/"propertyId"\s*:\s*(\d+)/);
      if (match) extracted.propertyId = match[1];

      match = text.match(/"listingId"\s*:\s*(\d+)/);
      if (match) extracted.listingId = match[1];

      // Beds and Baths
      match = text.match(/"beds"\s*:\s*(\d+)/);
      if (match) extracted.beds = parseInt(match[1]);

      match = text.match(/"baths"\s*:\s*([\d.]+)/);
      if (match) extracted.baths = parseFloat(match[1]);

      // MLS ID - try multiple field names, avoid source names like "ConsumerAccess"
      // Look for actual listing numbers (usually alphanumeric with numbers)
      match = text.match(/"mlsListingId"\s*:\s*"([^"]+)"/);
      if (match) {
        extracted.mlsId = match[1];
      } else {
        match = text.match(/"listingMlsId"\s*:\s*"([^"]+)"/);
        if (match) {
          extracted.mlsId = match[1];
        } else {
          // Only use mlsId if it looks like an actual listing number (has digits)
          match = text.match(/"mlsId"\s*:\s*"([^"]+)"/);
          if (match && /\d/.test(match[1]) && match[1].length < 20) {
            extracted.mlsId = match[1];
          }
        }
      }

      // Also look for MLS # in visible text patterns
      if (!extracted.mlsId) {
        match = text.match(/"mlsNumber"\s*:\s*"([^"]+)"/);
        if (match) extracted.mlsId = match[1];
      }

      // Street Address
      match = text.match(/"streetAddress"\s*:\s*\{[^}]*"assembledAddress"\s*:\s*"([^"]+)"/);
      if (match) {
        extracted.streetAddress = match[1];
      } else {
        match = text.match(/"streetAddress"\s*:\s*"([^"]+)"/);
        if (match) extracted.streetAddress = match[1];
      }

      // City, State, Zip
      match = text.match(/"city"\s*:\s*"([^"]+)"/);
      if (match) extracted.city = match[1];

      match = text.match(/"state"\s*:\s*"([^"]+)"/);
      if (match) extracted.state = match[1];

      match = text.match(/"zip"\s*:\s*"?(\d{5})"?/);
      if (match) extracted.zip = match[1];

      // Price
      match = text.match(/"price"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)/);
      if (match) {
        extracted.price = parseInt(match[1]);
      } else {
        match = text.match(/"listPrice"\s*:\s*(\d+)/);
        if (match) extracted.price = parseInt(match[1]);
      }

      // Sqft
      match = text.match(/"sqFt"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)/);
      if (match) {
        extracted.sqFt = parseInt(match[1]);
      } else {
        match = text.match(/"sqFt"\s*:\s*(\d+)/);
        if (match) extracted.sqFt = parseInt(match[1]);
      }

      // Year Built
      match = text.match(/"yearBuilt"\s*:\s*(\d{4})/);
      if (match) extracted.yearBuilt = parseInt(match[1]);

      // Lot Size
      match = text.match(/"lotSize"\s*:\s*\{[^}]*"value"\s*:\s*([\d.]+)/);
      if (match) extracted.lotSize = parseFloat(match[1]);

      // Days on Market - be more specific to avoid matching years
      match = text.match(/"dom"\s*:\s*(\d{1,4})(?=\s*[,}])/);
      if (match && parseInt(match[1]) < 1000) {
        extracted.dom = parseInt(match[1]);
      }
      if (!extracted.dom) {
        match = text.match(/"daysOnMarket"\s*:\s*(\d{1,4})/);
        if (match && parseInt(match[1]) < 1000) {
          extracted.dom = parseInt(match[1]);
        }
      }
      if (!extracted.dom) {
        match = text.match(/"timeOnRedfin"\s*:\s*(\d{1,4})/);
        if (match && parseInt(match[1]) < 1000) {
          extracted.dom = parseInt(match[1]);
        }
      }

      // Page views / Favorites (saves) - Redfin shows these
      match = text.match(/"pageViews"\s*:\s*(\d+)/);
      if (match) extracted.pageViews = parseInt(match[1]);
      if (!extracted.pageViews) {
        match = text.match(/"views"\s*:\s*(\d+)/);
        if (match) extracted.pageViews = parseInt(match[1]);
      }

      match = text.match(/"favorites"\s*:\s*(\d+)/);
      if (match) extracted.favorites = parseInt(match[1]);
      if (!extracted.favorites) {
        match = text.match(/"saves"\s*:\s*(\d+)/);
        if (match) extracted.favorites = parseInt(match[1]);
      }
      if (!extracted.favorites) {
        match = text.match(/"numFavorites"\s*:\s*(\d+)/);
        if (match) extracted.favorites = parseInt(match[1]);
      }

      // County
      match = text.match(/"county(?:Name)?"\s*:\s*"([^"]+)"/i);
      if (match) extracted.county = match[1];

      // MLS Source (the name of the MLS, not the listing number)
      match = text.match(/"mlsSource(?:Name)?"\s*:\s*"([^"]+)"/i);
      if (match) extracted.mlsSource = match[1];
      if (!extracted.mlsSource) {
        match = text.match(/"sourceName"\s*:\s*"([^"]+)"/i);
        if (match) extracted.mlsSource = match[1];
      }
      if (!extracted.mlsSource) {
        match = text.match(/"listingSource"\s*:\s*"([^"]+)"/i);
        if (match) extracted.mlsSource = match[1];
      }

      // Agent email - try multiple patterns
      match = text.match(/"listingAgent"\s*:\s*\{[^}]*"email"\s*:\s*"([^"]+)"/);
      if (match) extracted.listingAgentEmail = match[1];
      if (!extracted.listingAgentEmail) {
        match = text.match(/"agentEmail"\s*:\s*"([^"]+)"/);
        if (match) extracted.listingAgentEmail = match[1];
      }
      if (!extracted.listingAgentEmail) {
        match = text.match(/"listingAgentEmail"\s*:\s*"([^"]+)"/);
        if (match) extracted.listingAgentEmail = match[1];
      }

      // Listing Agent - try multiple patterns
      match = text.match(/"listingAgent"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"/);
      if (match) extracted.listingAgentName = match[1];

      // Agent phone - try multiple field locations
      match = text.match(/"listingAgent"\s*:\s*\{[^}]*"phone"\s*:\s*"([^"]+)"/);
      if (match) extracted.listingAgentPhone = match[1];

      // Also try agentPhone, phoneNumber patterns
      if (!extracted.listingAgentPhone) {
        match = text.match(/"agentPhone"\s*:\s*"([^"]+)"/);
        if (match) extracted.listingAgentPhone = match[1];
      }
      if (!extracted.listingAgentPhone) {
        match = text.match(/"listingAgentPhone"\s*:\s*"([^"]+)"/);
        if (match) extracted.listingAgentPhone = match[1];
      }
      // Look for phone number pattern near agent info
      if (!extracted.listingAgentPhone && extracted.listingAgentName) {
        // Find phone near the agent name in the text
        const agentIdx = text.indexOf(extracted.listingAgentName);
        if (agentIdx > -1) {
          const nearbyText = text.substring(Math.max(0, agentIdx - 200), agentIdx + 500);
          const phoneMatch = nearbyText.match(/"phone(?:Number)?"\s*:\s*"([\d\s().-]+)"/);
          if (phoneMatch) extracted.listingAgentPhone = phoneMatch[1];
        }
      }

      // Lat/Long - critical for mapping
      match = text.match(/"latitude"\s*:\s*([\d.-]+)/);
      if (match) extracted.latitude = parseFloat(match[1]);

      match = text.match(/"longitude"\s*:\s*([\d.-]+)/);
      if (match) extracted.longitude = parseFloat(match[1]);

      // Also try lat/lng variants
      if (!extracted.latitude) {
        match = text.match(/"lat"\s*:\s*([\d.-]+)/);
        if (match) extracted.latitude = parseFloat(match[1]);
      }
      if (!extracted.longitude) {
        match = text.match(/"(?:lng|long)"\s*:\s*([\d.-]+)/);
        if (match) extracted.longitude = parseFloat(match[1]);
      }

      // Parcel ID - critical for property identification
      match = text.match(/"parcelId"\s*:\s*"?([^",]+)"?/);
      if (match) extracted.parcelId = match[1];

      if (!extracted.parcelId) {
        match = text.match(/"parcelNumber"\s*:\s*"?([^",]+)"?/);
        if (match) extracted.parcelId = match[1];
      }

      if (!extracted.parcelId) {
        match = text.match(/"apn"\s*:\s*"?([^",]+)"?/);
        if (match) extracted.parcelId = match[1];
      }

      console.log('Redfin: Direct extraction results:', extracted);
      console.log('Redfin: Critical fields - lat:', extracted.latitude, 'lng:', extracted.longitude, 'parcel:', extracted.parcelId);

      if (extracted.beds || extracted.mlsId || extracted.streetAddress) {
        return extracted;
      }
    }
  }

  return null;
}

// ============================================
// EXTRACT HOMES FROM ALL SCRIPT TAGS
// ============================================
function extractHomesFromScripts() {
  console.log('Redfin: Searching all scripts for homes data...');
  const homes = [];
  const scripts = document.querySelectorAll('script:not([src])');

  for (const script of scripts) {
    const text = script.textContent || '';
    if (text.length < 100) continue;

    // Look for patterns that indicate home/property data
    if (text.includes('propertyId') || text.includes('listingId') || text.includes('homeData')) {
      // Try to find JSON objects with homes array
      const jsonMatches = text.matchAll(/\{[^{}]*"(?:homes|listings|searchResults)"[^{}]*\[[\s\S]*?\][\s\S]*?\}/g);

      for (const match of jsonMatches) {
        try {
          // This is a rough match, try to parse
          const parsed = JSON.parse(match[0]);
          if (parsed.homes && Array.isArray(parsed.homes)) {
            homes.push(...parsed.homes);
          }
        } catch (e) {
          // Not valid JSON, continue
        }
      }

      // Also try to find individual home objects
      const homeMatches = text.matchAll(/\{"propertyId":\d+[^}]+(?:"streetAddress"|"price")[^}]+\}/g);
      for (const match of homeMatches) {
        try {
          const home = JSON.parse(match[0]);
          if (home.propertyId) {
            homes.push(home);
          }
        } catch (e) {
          // Continue
        }
      }
    }
  }

  // Deduplicate by propertyId
  const seen = new Set();
  const unique = homes.filter(h => {
    const id = h.propertyId || h.listingId;
    if (id && !seen.has(id)) {
      seen.add(id);
      return true;
    }
    return false;
  });

  console.log('Redfin: extractHomesFromScripts found', unique.length, 'unique homes');
  return unique;
}

// ============================================
// EXTRACT SEARCH RESULTS (Bulk Operations)
// ============================================
function scrapeRedfinSearchResults() {
  console.log('Redfin: Scraping search results');
  const results = [];

  // Method 0: Search all script tags for JSON with homes array
  const scriptsData = extractHomesFromScripts();
  if (scriptsData.length > 0) {
    console.log('Redfin: Found', scriptsData.length, 'homes from script tags');
    for (const home of scriptsData) {
      results.push(normalizeRedfinSearchResult(home));
    }
  }

  // Method 1: Extract from reactServerState
  if (results.length === 0) {
    const serverState = extractReactServerState();
    if (serverState?.searchResults?.homes) {
      console.log('Redfin: Found homes in reactServerState');
      for (const home of serverState.searchResults.homes) {
        results.push(normalizeRedfinSearchResult(home));
      }
    }
  }

  // Method 2: Extract from preloaded data
  if (results.length === 0) {
    const preload = extractPreloadData();
    if (preload?.homes) {
      for (const home of preload.homes) {
        results.push(normalizeRedfinSearchResult(home));
      }
    }
  }

  // Method 3: Find property cards by looking for elements with price text
  if (results.length === 0) {
    console.log('Redfin: Using price-based card detection');

    // Find all elements containing a price
    const allElements = document.body.querySelectorAll('*');
    const priceContainers = [];

    // First, find all links to property pages
    const propertyLinks = document.querySelectorAll('a[href*="/home/"]');
    console.log('Redfin: Found', propertyLinks.length, 'property links');

    const seenUrls = new Set();

    propertyLinks.forEach(link => {
      const url = link.href;
      if (seenUrls.has(url) || !url.includes('/home/')) return;

      // Walk up to find a container with price AND beds/baths info
      let container = link;
      let foundGoodContainer = false;

      for (let i = 0; i < 10; i++) {
        if (!container.parentElement) break;
        container = container.parentElement;

        const text = container.textContent || '';
        const hasPrice = /\$[\d,]+/.test(text);
        const hasBeds = /\d+\s*bed/i.test(text);

        if (hasPrice && hasBeds && text.length < 5000) {
          foundGoodContainer = true;
          break;
        }
      }

      if (foundGoodContainer) {
        seenUrls.add(url);
        try {
          const result = parseRedfinCardFromContainer(container, link);
          if (result.price || result.beds) {
            results.push(result);
            console.log('Redfin: Extracted property:', result.price, result.beds, 'beds');
          }
        } catch (e) {
          console.warn('Failed to parse container:', e);
        }
      }
    });

    console.log('Redfin: Price-based detection found', results.length, 'properties');
  }

  console.log('Redfin: Extracted', results.length, 'search results');
  return results;
}

// ============================================
// EXTRACT REACT SERVER STATE
// ============================================
function extractReactServerState() {
  console.log('Redfin: Searching for __reactServerState...');

  // Look for __reactServerState in window
  if (window.__reactServerState) {
    console.log('Redfin: Found window.__reactServerState');
    return parseNestedState(window.__reactServerState);
  }

  // Search in script tags - find the one with property data
  const scripts = document.querySelectorAll('script:not([src])');

  for (const script of scripts) {
    const text = script.textContent || '';

    // Skip small scripts
    if (text.length < 500) continue;

    // Look for script containing both __reactServerState and property data
    if (text.includes('__reactServerState') && text.includes('propertyId')) {
      console.log('Redfin: Found script with __reactServerState and propertyId');

      // Try to extract the full state object
      // Pattern: root.__reactServerState = {...}
      let match = text.match(/root\.__reactServerState\s*=\s*(\{[\s\S]*\})\s*;?\s*(?:root\.|window\.|$)/);

      if (!match) {
        // Alternative pattern: window.__reactServerState = {...}
        match = text.match(/window\.__reactServerState\s*=\s*(\{[\s\S]*\})\s*;?\s*(?:window\.|$)/);
      }

      if (!match) {
        // Try to find the JSON blob more aggressively
        // Look for the start of the object after __reactServerState
        const startIdx = text.indexOf('__reactServerState');
        if (startIdx > -1) {
          const afterAssign = text.substring(startIdx);
          const objStart = afterAssign.indexOf('{');
          if (objStart > -1) {
            // Find matching closing brace
            let depth = 0;
            let objEnd = -1;
            for (let i = objStart; i < afterAssign.length; i++) {
              if (afterAssign[i] === '{') depth++;
              else if (afterAssign[i] === '}') {
                depth--;
                if (depth === 0) {
                  objEnd = i + 1;
                  break;
                }
              }
            }
            if (objEnd > objStart) {
              const jsonStr = afterAssign.substring(objStart, objEnd);
              try {
                const state = JSON.parse(jsonStr);
                console.log('Redfin: Parsed __reactServerState (aggressive), keys:', Object.keys(state).slice(0, 5));
                return parseNestedState(state);
              } catch (e) {
                console.log('Redfin: Failed to parse aggressive extraction');
              }
            }
          }
        }
      }

      if (match) {
        try {
          const state = JSON.parse(match[1]);
          console.log('Redfin: Parsed __reactServerState, keys:', Object.keys(state).slice(0, 5));
          return parseNestedState(state);
        } catch (e) {
          console.log('Redfin: Failed to parse __reactServerState JSON:', e.message);
        }
      }
    }

    // Also try to find inline property data directly
    if (text.includes('"beds"') && text.includes('"baths"') && text.includes('"mlsId"')) {
      console.log('Redfin: Found script with property fields directly');

      // Try to extract property object
      const propMatch = text.match(/\{"propertyId":\d+[^}]*"beds":\d+[^}]*"baths":[^}]*"mlsId":"[^"]+"/);
      if (propMatch) {
        // Find the complete object
        const startIdx = text.indexOf(propMatch[0]);
        let depth = 0;
        let objEnd = -1;
        for (let i = startIdx; i < text.length; i++) {
          if (text[i] === '{') depth++;
          else if (text[i] === '}') {
            depth--;
            if (depth === 0) {
              objEnd = i + 1;
              break;
            }
          }
        }
        if (objEnd > startIdx) {
          try {
            const propObj = JSON.parse(text.substring(startIdx, objEnd));
            console.log('Redfin: Extracted property object directly');
            return propObj;
          } catch (e) {}
        }
      }
    }
  }

  return null;
}

// ============================================
// EXTRACT PRELOAD DATA
// ============================================
function extractPreloadData() {
  // Look for various Redfin data patterns in scripts
  const scripts = document.querySelectorAll('script:not([src])');

  for (const script of scripts) {
    const text = script.textContent || '';

    // Look for property data patterns
    const patterns = [
      /window\.defined\s*=\s*(\{[\s\S]+?\});/,
      /window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]+?\});/,
      /"listingId":\s*\d+[\s\S]*?"mlsId":/,
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        try {
          if (match[1]) {
            return JSON.parse(match[1]);
          }
        } catch (e) {}
      }
    }

    // Look for inline JSON with property data
    if (text.includes('"listingId"') && text.includes('"streetAddress"')) {
      // Extract the largest JSON object containing listing data
      const jsonObjects = text.match(/\{[^{}]*"listingId"[^{}]*("streetAddress"|"propertyId")[^{}]*\}/g);
      if (jsonObjects) {
        for (const jsonStr of jsonObjects) {
          try {
            return JSON.parse(jsonStr);
          } catch (e) {}
        }
      }
    }
  }

  return null;
}

// ============================================
// PARSE NESTED STATE
// ============================================
function parseNestedState(state) {
  if (!state) return null;

  // Redfin often nests data in various paths
  const paths = [
    'propertyDetailsInfo',
    'initialData',
    'preloadedDataByResource',
    'marketingInfo',
    'aboveTheFold',
    'listingInfo',
  ];

  // Check direct paths
  for (const path of paths) {
    if (state[path]?.propertyId || state[path]?.listingId) {
      return state[path];
    }
  }

  // Check for nested property data
  if (state.payload?.propertyId) return state.payload;
  if (state.data?.propertyId) return state.data;

  // Deep search for property-like object
  return deepFindRedfinProperty(state);
}

// ============================================
// DEEP FIND REDFIN PROPERTY
// ============================================
function deepFindRedfinProperty(obj, depth = 0) {
  if (depth > 8 || !obj || typeof obj !== 'object') return null;

  // Check if this object looks like property data
  if (obj.propertyId && (obj.streetAddress || obj.mlsId || obj.beds)) {
    return obj;
  }

  // Check for listingInfo pattern
  if (obj.listingId && obj.mlsId) {
    return obj;
  }

  const skipKeys = ['schools', 'similarHomes', 'nearbyHomes', 'comparables', 'trendLines'];

  for (const key of Object.keys(obj)) {
    if (skipKeys.includes(key)) continue;
    const result = deepFindRedfinProperty(obj[key], depth + 1);
    if (result) return result;
  }

  return null;
}

// ============================================
// NORMALIZE REDFIN PROPERTY DATA
// ============================================
function normalizeRedfinProperty(raw) {
  if (!raw) return {};

  console.log('Redfin: Normalizing property with keys:', Object.keys(raw));

  const data = {};

  // IDs
  data.redfin_id = raw.propertyId?.toString() || raw.listingId?.toString() || null;
  data.mls_number = raw.mlsId || raw.mlsNumber || raw.listingMlsId || null;

  // Price - handle various formats
  if (typeof raw.price === 'object' && raw.price?.value) {
    data.price = raw.price.value;
  } else if (typeof raw.price === 'number') {
    data.price = raw.price;
  } else {
    data.price = raw.listPrice || null;
  }

  // Basic details
  data.beds = raw.beds ?? raw.numBeds ?? raw.bedrooms ?? null;
  data.baths = raw.baths ?? raw.numBaths ?? raw.bathrooms ?? null;

  // Sqft - handle object format
  if (typeof raw.sqFt === 'object' && raw.sqFt?.value) {
    data.sqft = raw.sqFt.value;
  } else if (typeof raw.sqFt === 'number') {
    data.sqft = raw.sqFt;
  } else {
    data.sqft = raw.livingArea || null;
  }

  data.lot_acres = parseLotSize(raw);
  data.year_built = raw.yearBuilt || null;
  data.property_type = raw.propertyType || raw.propertyTypeName || null;
  data.stories = raw.stories || raw.numStories || null;

  // Address - handle string or object
  if (typeof raw.streetAddress === 'object' && raw.streetAddress?.assembledAddress) {
    data.address = raw.streetAddress.assembledAddress;
  } else if (typeof raw.streetAddress === 'string') {
    data.address = raw.streetAddress;
  } else if (raw.address) {
    data.address = typeof raw.address === 'string' ? raw.address : raw.address.streetAddress;
  }

  data.city = raw.city || raw.streetAddress?.city || null;
  data.state = raw.state || raw.streetAddress?.state || null;
  data.zip = raw.zip || raw.zipCode || raw.streetAddress?.zip || null;

  // Parse city/state/zip from address if not separately available
  if (data.address && (!data.city || !data.state || !data.zip)) {
    const addressParts = parseAddressComponents(data.address);
    if (!data.city && addressParts.city) data.city = addressParts.city;
    if (!data.state && addressParts.state) data.state = addressParts.state;
    if (!data.zip && addressParts.zip) data.zip = addressParts.zip;
  }

  // Location
  data.latitude = raw.latitude || raw.lat || null;
  data.longitude = raw.longitude || raw.long || raw.lng || null;

  // Listing info
  data.status = raw.listingStatus || raw.status || null;
  data.days_on_market = raw.dom || raw.daysOnMarket || raw.timeOnRedfin || null;
  data.hoa_fee = raw.hoaDues || raw.hoaFee || null;

  // Agent info - check multiple sources
  // Direct extraction fields
  if (raw.listingAgentName) data.listing_agent_name = raw.listingAgentName;
  if (raw.listingAgentPhone) data.listing_agent_phone = raw.listingAgentPhone;
  if (raw.listingAgentEmail) data.listing_agent_email = raw.listingAgentEmail;

  // Nested listingAgent object
  const agent = raw.listingAgent || raw.agentInfo || raw.marketingInfo?.listingAgent || {};
  if (!data.listing_agent_name) {
    data.listing_agent_name = agent.name || agent.agentName || null;
  }
  if (!data.listing_agent_phone) {
    data.listing_agent_phone = agent.phone || agent.phoneNumber || null;
  }
  if (!data.listing_agent_email) {
    data.listing_agent_email = agent.email || null;
  }
  data.listing_brokerage = agent.brokerageName || raw.listingBrokerName || raw.brokerageName || null;

  // Also check brokerInfo
  if (raw.brokerInfo) {
    if (!data.listing_brokerage) data.listing_brokerage = raw.brokerInfo.name;
    if (!data.listing_agent_phone) data.listing_agent_phone = raw.brokerInfo.phone;
  }

  // Tax info
  data.tax_assessed_value = raw.taxAssessedValue || null;
  data.tax_annual_amount = raw.taxAnnualAmount || raw.taxes || null;

  // Views and Saves (Favorites)
  data.page_views = raw.pageViews || raw.views || null;
  data.favorites_count = raw.favorites || raw.saves || raw.numFavorites || null;

  // County
  data.county = raw.county || raw.countyName || null;

  // MLS Source (the name of the MLS)
  data.mls_source = raw.mlsSource || raw.mlsSourceName || raw.sourceName || raw.listingSource || null;

  // Parcel ID - critical field
  data.parcel_id = raw.parcelId || raw.parcelNumber || raw.apn || null;

  // Features
  if (raw.amenities || raw.propertyAmenities) {
    const amenities = raw.amenities || raw.propertyAmenities;
    data.heating = extractAmenity(amenities, 'heating');
    data.cooling = extractAmenity(amenities, 'cooling');
    data.garage = extractAmenity(amenities, 'garage', 'parking');
  }

  // Photos
  if (raw.photos && Array.isArray(raw.photos)) {
    data.photo_urls = raw.photos.slice(0, 10).map(p => p.photoUrl || p.url || p).filter(Boolean);
  }

  console.log('Redfin: Normalized data - beds:', data.beds, 'baths:', data.baths, 'mls:', data.mls_number, 'agent:', data.listing_agent_name);

  return data;
}

// ============================================
// NORMALIZE SEARCH RESULT (for bulk operations)
// ============================================
function normalizeRedfinSearchResult(home) {
  const data = {
    redfin_id: home.propertyId?.toString() || home.listingId?.toString() || null,
    mls_number: home.mlsId || null,
    address: home.streetAddress?.assembledAddress || home.streetAddress || home.address || null,
    city: home.city || null,
    state: home.state || null,
    zip: home.zip || home.zipCode || null,
    price: home.price?.value || home.listPrice || home.price || null,
    beds: home.beds ?? home.numBeds ?? null,
    baths: home.baths ?? home.numBaths ?? null,
    sqft: home.sqFt?.value || home.sqFt || null,
    lot_acres: parseLotSize(home),
    year_built: home.yearBuilt || null,
    latitude: home.latitude || home.lat || null,
    longitude: home.longitude || home.long || null,
    status: home.listingStatus || home.status || null,
    days_on_market: home.dom || home.daysOnMarket || null,
    url: home.url || (home.propertyId ? `https://www.redfin.com/home/${home.propertyId}` : null),
    source: 'redfin',
    isSearchResult: true,
    // For bulk export
    listing_agent_name: home.listingAgent?.name || null,
    listing_agent_phone: home.listingAgent?.phone || null,
  };

  return data;
}

// ============================================
// PARSE REDFIN DOM CARD
// ============================================
function parseRedfinCard(card) {
  const data = {
    source: 'redfin',
    isSearchResult: true
  };

  // Get ALL text from the card for fallback parsing
  const fullText = card.textContent || '';
  console.log('Redfin: Parsing card with text length:', fullText.length);

  // Get link and property ID - try multiple patterns
  let link = card.querySelector('a[href*="/home/"]');
  if (!link) {
    // Try finding any link in the card
    const allLinks = card.querySelectorAll('a[href]');
    for (const l of allLinks) {
      if (l.href && l.href.includes('redfin.com')) {
        link = l;
        break;
      }
    }
  }

  if (link) {
    data.url = link.href.startsWith('http') ? link.href : 'https://www.redfin.com' + link.getAttribute('href');
    const idMatch = data.url.match(/\/home\/(\d+)/);
    if (idMatch) data.redfin_id = idMatch[1];
  }

  // ALWAYS parse price from full text (most reliable)
  const priceMatch = fullText.match(/\$\s*([\d,]+)/);
  if (priceMatch) {
    data.price = parseInt(priceMatch[1].replace(/,/g, ''));
  }

  // ALWAYS parse beds/baths/sqft from full text
  const bedsMatch = fullText.match(/(\d+)\s*(?:bed|bd)/i);
  const bathsMatch = fullText.match(/([\d.]+)\s*(?:bath|ba)/i);
  const sqftMatch = fullText.match(/([\d,]+)\s*(?:sq\s*ft|sqft|sf)/i);

  if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
  if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
  if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));

  // Try to extract address - look for address-like patterns
  // Pattern: number + street name + city + state + zip
  const addressPatterns = [
    /(\d+\s+[A-Za-z\s]+(?:St|Ave|Rd|Dr|Ln|Way|Blvd|Ct|Cir|Pl)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})/i,
    /(\d+\s+[A-Za-z\s]+(?:Street|Avenue|Road|Drive|Lane|Way|Boulevard|Court|Circle|Place)[^,]*,\s*[A-Za-z\s]+)/i,
    /(\d+\s+[A-Za-z\s]+,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})/,
    /(\d+\s+[A-Za-z0-9\s]+,\s*[A-Za-z\s]+,\s*[A-Z]{2})/
  ];

  for (const pattern of addressPatterns) {
    const match = fullText.match(pattern);
    if (match) {
      let addr = match[1].trim();
      // Clean up: remove price/stats that might have been captured
      addr = addr.replace(/\$[\d,]+.*$/, '').trim();
      addr = addr.replace(/\d+\s*(?:bed|bath|sq).*$/i, '').trim();
      if (addr.length > 10 && addr.length < 100) {
        data.address = addr;
        break;
      }
    }
  }

  // If still no address, try specific selectors
  if (!data.address) {
    const addressSelectors = [
      '.homeAddressV2',
      '.HomeCardAddress',
      '[data-rf-test-id="home-card-address"]',
      '.bp-Homecard__Address',
      '.link-and-anchor',
      '[class*="address"]',
      '[class*="Address"]',
      '.streetAddress',
      'span[class*="street"]'
    ];
    for (const sel of addressSelectors) {
      const el = card.querySelector(sel);
      if (el && el.textContent.trim().length > 5) {
        data.address = el.textContent.trim();
        break;
      }
    }
  }

  console.log('Redfin: Card parsed -', 'price:', data.price, 'beds:', data.beds, 'address:', data.address?.substring(0, 30));
  return data;
}

// ============================================
// PARSE REDFIN CARD FROM CONTAINER (Link-based fallback)
// ============================================
function parseRedfinCardFromContainer(container, link) {
  const data = {
    source: 'redfin',
    isSearchResult: true
  };

  // Get URL and property ID from the link
  data.url = link.href.startsWith('http') ? link.href : 'https://www.redfin.com' + link.getAttribute('href');
  const idMatch = data.url.match(/\/home\/(\d+)/);
  if (idMatch) data.redfin_id = idMatch[1];

  // Parse text content from container
  const text = container.textContent || '';

  // Extract price
  const priceMatch = text.match(/\$([\d,]+)/);
  if (priceMatch) {
    data.price = parseInt(priceMatch[1].replace(/,/g, ''));
  }

  // Extract beds, baths, sqft
  const bedsMatch = text.match(/(\d+)\s*(?:bed|bd)/i);
  const bathsMatch = text.match(/([\d.]+)\s*(?:bath|ba)/i);
  const sqftMatch = text.match(/([\d,]+)\s*(?:sq\s*ft|sqft|sf)/i);

  if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
  if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
  if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));

  // Extract address - look for patterns like "123 Street Name, City, ST 12345"
  // Try to find text that looks like an address (has comma and state abbreviation or zip)
  const addressMatch = text.match(/(\d+[^$\d]+(?:,\s*[A-Za-z\s]+)+(?:,\s*[A-Z]{2}\s*\d{5})?)/);
  if (addressMatch) {
    // Clean up the address
    let addr = addressMatch[1].trim();
    // Remove stats from address if they got included
    addr = addr.replace(/\d+\s*(?:bed|bath|sq\s*ft|sqft|bd|ba|sf).*$/i, '').trim();
    if (addr.length > 5 && addr.length < 100) {
      data.address = addr;
    }
  }

  // If no address found, try link text or alt text
  if (!data.address) {
    const linkText = link.textContent?.trim();
    if (linkText && linkText.length > 5 && linkText.length < 100 && !linkText.includes('$')) {
      data.address = linkText;
    }
  }

  return data;
}

// ============================================
// SCRAPE REDFIN DOM (Enhanced Fallback)
// ============================================
function scrapeRedfinDOM() {
  const data = {};
  const bodyText = document.body.innerText;

  console.log('Redfin: Starting DOM scrape...');

  // Price - try multiple selectors
  const priceSelectors = [
    '[data-rf-test-id="abp-price"]',
    '.statsValue',
    '.price-section .price',
    '.home-main-stats-variant .stat-value',
    'span[data-testid="price"]'
  ];
  for (const sel of priceSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const priceMatch = el.textContent.match(/\$([\d,]+)/);
      if (priceMatch) {
        data.price = parseInt(priceMatch[1].replace(/,/g, ''));
        console.log('Redfin DOM: Found price via', sel);
        break;
      }
    }
  }

  // Address - try multiple selectors
  const addressSelectors = [
    '[data-rf-test-id="abp-streetLine"]',
    '.street-address',
    '.full-address',
    'h1.address',
    '[data-testid="address"]'
  ];
  for (const sel of addressSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      data.address = el.textContent.trim();
      console.log('Redfin DOM: Found address via', sel);
      break;
    }
  }

  // City/State/Zip
  const cityStateSelectors = [
    '[data-rf-test-id="abp-cityStateZip"]',
    '.dp-subtext',
    '.city-state-zip'
  ];
  for (const sel of cityStateSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = el.textContent;
      const parts = text.split(',');
      if (parts.length >= 2) {
        data.city = parts[0].trim();
        const stateZip = parts[1].trim().match(/([A-Z]{2})\s*(\d{5})/);
        if (stateZip) {
          data.state = stateZip[1];
          data.zip = stateZip[2];
        }
      }
      break;
    }
  }

  // Beds/Baths/Sqft - comprehensive search
  // Method 1: Look for stat blocks
  const statBlocks = document.querySelectorAll('.stat-block, .home-main-stats-variant .stat, [class*="KeyFact"]');
  statBlocks.forEach(block => {
    const text = block.textContent.toLowerCase();
    const numbers = text.match(/[\d,.]+/g);
    if (numbers && numbers.length > 0) {
      const value = numbers[0];
      if (text.includes('bed')) data.beds = parseInt(value);
      else if (text.includes('bath')) data.baths = parseFloat(value);
      else if (text.includes('sq') && !text.includes('lot')) data.sqft = parseInt(value.replace(/,/g, ''));
    }
  });

  // Method 2: Look for specific test IDs
  const bedsEl = document.querySelector('[data-rf-test-id="abp-beds"] .statsValue, [data-testid="beds"]');
  const bathsEl = document.querySelector('[data-rf-test-id="abp-baths"] .statsValue, [data-testid="baths"]');
  const sqftEl = document.querySelector('[data-rf-test-id="abp-sqFt"] .statsValue, [data-testid="sqft"]');

  if (bedsEl && !data.beds) data.beds = parseInt(bedsEl.textContent);
  if (bathsEl && !data.baths) data.baths = parseFloat(bathsEl.textContent);
  if (sqftEl && !data.sqft) data.sqft = parseInt(sqftEl.textContent.replace(/,/g, ''));

  // Method 3: Parse from body text patterns
  if (!data.beds) {
    const bedsMatch = bodyText.match(/(\d+)\s*(?:Beds?|Bedrooms?|BR)\b/i);
    if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
  }
  if (!data.baths) {
    const bathsMatch = bodyText.match(/([\d.]+)\s*(?:Baths?|Bathrooms?|BA)\b/i);
    if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
  }
  if (!data.sqft) {
    const sqftMatch = bodyText.match(/([\d,]+)\s*(?:Sq\.?\s*Ft\.?|Square\s*Feet|SF)\b/i);
    if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
  }

  // Year Built
  const yearMatch = bodyText.match(/(?:Year\s*Built|Built\s*in|Yr\s*Built)[:\s]*(\d{4})/i);
  if (yearMatch) data.year_built = parseInt(yearMatch[1]);

  // Property Type - look in facts section and body text
  const propertyTypePatterns = [
    /(?:Property|Home)\s*Type[:\s]*(Single\s*Family|Condo|Townhouse|Townhome|Multi[\s-]*Family|Manufactured|Mobile|Land|Lot|Farm|Ranch|Co-op|Cooperative)/i,
    /(?:Style|Type)[:\s]*(Single\s*Family|Condo|Townhouse|Townhome|Multi[\s-]*Family|Manufactured|Mobile)/i,
    /(Single\s*Family\s*(?:Home|Residence|Residential)?|Condo(?:minium)?|Townhouse|Townhome|Multi[\s-]*Family)/i
  ];
  for (const pattern of propertyTypePatterns) {
    const match = bodyText.match(pattern);
    if (match) {
      data.property_type = match[1].trim();
      console.log('Redfin DOM: Found property type:', data.property_type);
      break;
    }
  }

  // Heating, Cooling, Garage - look in property facts sections
  const propFactsSections = document.querySelectorAll('.amenity-group, .facts-table, [class*="PropertyFacts"], [class*="keyDetails"], .super-group-content, .amenities-container');
  for (const section of propFactsSections) {
    const sectionText = section.innerText || '';

    // Heating
    if (!data.heating) {
      const heatingMatch = sectionText.match(/Heating[:\s]*([^\n,]+)/i);
      if (heatingMatch) {
        data.heating = heatingMatch[1].trim();
        console.log('Redfin DOM: Found heating:', data.heating);
      }
    }

    // Cooling
    if (!data.cooling) {
      const coolingMatch = sectionText.match(/(?:Cooling|A\/C|Air\s*Condition)[:\s]*([^\n,]+)/i);
      if (coolingMatch) {
        data.cooling = coolingMatch[1].trim();
        console.log('Redfin DOM: Found cooling:', data.cooling);
      }
    }

    // Garage
    if (!data.garage) {
      const garagePatterns = [
        /Garage[:\s]*([^\n]+)/i,
        /Parking[:\s]*([^\n]+)/i,
        /(\d+)\s*(?:Car\s*)?Garage/i
      ];
      for (const pattern of garagePatterns) {
        const match = sectionText.match(pattern);
        if (match) {
          data.garage = match[1].trim();
          console.log('Redfin DOM: Found garage:', data.garage);
          break;
        }
      }
    }
  }

  // Fallback: search body text for heating/cooling/garage
  if (!data.heating) {
    const match = bodyText.match(/Heating[:\s]*([\w\s,]+?)(?:\.|Cooling|$)/i);
    if (match) data.heating = match[1].trim();
  }
  if (!data.cooling) {
    const match = bodyText.match(/(?:Cooling|A\/C)[:\s]*([\w\s,]+?)(?:\.|Heating|$)/i);
    if (match) data.cooling = match[1].trim();
  }
  if (!data.garage) {
    const match = bodyText.match(/(\d+)\s*(?:Car\s*)?Garage/i);
    if (match) data.garage = match[0];
  }

  // MLS number - multiple patterns
  // Look in specific DOM elements first
  const mlsSelectors = [
    '[data-rf-test-id="abp-mls"]',
    '.mls-id',
    '[class*="mlsId"]',
    '.listing-mls'
  ];
  for (const sel of mlsSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const mlsText = el.textContent.trim();
      const mlsMatch = mlsText.match(/([A-Z0-9-]{5,20})/i);
      if (mlsMatch && /\d/.test(mlsMatch[1])) {
        data.mls_number = mlsMatch[1];
        console.log('Redfin DOM: Found MLS via', sel, ':', data.mls_number);
        break;
      }
    }
  }

  // Fall back to text patterns if not found
  if (!data.mls_number) {
    const mlsPatterns = [
      /MLS\s*Grid\s*#\s*(\d+)/i,                    // "MLS Grid #3078662"
      /MLS\s*#\s*(\d+)/i,                           // "MLS #3078662"
      /MLS[#:\s]*#?\s*([A-Z0-9-]{5,20})/i,
      /Listing\s*(?:ID|#)[:\s]*([A-Z0-9-]{5,20})/i,
      /Source:[^#]*#\s*(\d{5,})/i,                  // "Source: ... #3078662"
      /#\s*([A-Z]{0,3}\d{5,})/i
    ];
    for (const pattern of mlsPatterns) {
      const match = bodyText.match(pattern);
      if (match && match[1].length >= 5 && match[1].length <= 20 && /\d/.test(match[1])) {
        // Make sure it's not "ConsumerAccess" or similar
        if (!/^[A-Za-z]+$/.test(match[1])) {
          data.mls_number = match[1];
          console.log('Redfin DOM: Found MLS via text pattern:', data.mls_number);
          break;
        }
      }
    }
  }

  // Days on market, Views, Favorites - pattern: "16 days on Redfin • 208 views • 6 favorites"
  const statsMatch = bodyText.match(/(\d+)\s*days?\s*on\s*Redfin\s*[•·]\s*(\d+)\s*views?\s*[•·]\s*(\d+)\s*favorites?/i);
  if (statsMatch) {
    data.days_on_market = parseInt(statsMatch[1]);
    data.page_views = parseInt(statsMatch[2]);
    data.favorites_count = parseInt(statsMatch[3]);
    console.log('Redfin DOM: Found stats - DOM:', data.days_on_market, 'views:', data.page_views, 'favorites:', data.favorites_count);
  } else {
    // Fallback: try to get days on market separately
    const domMatch = bodyText.match(/(\d+)\s*days?\s*on\s*Redfin/i);
    if (domMatch) data.days_on_market = parseInt(domMatch[1]);

    // Try views separately
    const viewsMatch = bodyText.match(/(\d+)\s*views?(?:\s|$)/i);
    if (viewsMatch) {
      data.page_views = parseInt(viewsMatch[1]);
      console.log('Redfin DOM: Found views:', data.page_views);
    }

    // Try favorites separately
    const favMatch = bodyText.match(/(\d+)\s*favorites?/i);
    if (favMatch) {
      data.favorites_count = parseInt(favMatch[1]);
      console.log('Redfin DOM: Found favorites:', data.favorites_count);
    }
  }

  // MLS Source extraction - multiple patterns to handle different formats
  // Pattern 1: "Source: CANOPYMLS as Distributed by MLS Grid #4331717"
  let mlsSourceMatch = bodyText.match(/Source:\s*([A-Z0-9]+)\s*as\s*Distributed\s*by\s*MLS\s*Grid\s*#(\d+)/i);
  if (mlsSourceMatch) {
    data.mls_source = mlsSourceMatch[1];
    if (!data.mls_number) {
      data.mls_number = mlsSourceMatch[2];
    }
    console.log('Redfin DOM: Found MLS source (pattern 1):', data.mls_source, 'MLS#:', data.mls_number);
  }

  // Pattern 2: "Source: CSAOR #12345" (without "as Distributed")
  if (!data.mls_source) {
    mlsSourceMatch = bodyText.match(/Source:\s*([A-Z0-9]{3,})\s*#(\d+)/i);
    if (mlsSourceMatch) {
      data.mls_source = mlsSourceMatch[1];
      if (!data.mls_number) {
        data.mls_number = mlsSourceMatch[2];
      }
      console.log('Redfin DOM: Found MLS source (pattern 2):', data.mls_source, 'MLS#:', data.mls_number);
    }
  }

  // Pattern 3: "CANOPYMLS as Distributed" or "CSAOR as Distributed" (without Source: prefix)
  if (!data.mls_source) {
    mlsSourceMatch = bodyText.match(/([A-Z0-9]{3,})\s*as\s*Distributed/i);
    if (mlsSourceMatch) {
      data.mls_source = mlsSourceMatch[1];
      console.log('Redfin DOM: Found MLS source (pattern 3):', data.mls_source);
    }
  }

  // Pattern 4: Look for known MLS names in the text
  if (!data.mls_source) {
    const knownMLS = ['CANOPYMLS', 'CSAOR', 'CTMLS', 'ARMLS', 'NTREIS', 'FMLS', 'GAMLS', 'NCRMLS', 'IRMLS'];
    for (const mls of knownMLS) {
      if (bodyText.includes(mls)) {
        data.mls_source = mls;
        console.log('Redfin DOM: Found MLS source (known list):', data.mls_source);
        break;
      }
    }
  }

  // Agent email - pattern: "Contact: rmcclure@mccluregrouprealty.com"
  const emailMatch = bodyText.match(/Contact:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/i);
  if (emailMatch) {
    data.listing_agent_email = emailMatch[1];
    console.log('Redfin DOM: Found agent email:', data.listing_agent_email);
  }

  // Agent name and brokerage - pattern: "Listed by Robert McClure Jr • McClure Group Realty LLC"
  const listedByMatch = bodyText.match(/Listed\s+by\s+([^•\n]+?)\s*[•·]\s*([^•\n]+?)(?:\n|Contact|Listing)/i);
  if (listedByMatch) {
    data.listing_agent_name = listedByMatch[1].trim();
    data.listing_brokerage = listedByMatch[2].trim();
    console.log('Redfin DOM: Found agent:', data.listing_agent_name, 'brokerage:', data.listing_brokerage);
  }

  // Agent info - look in multiple places
  const agentSelectors = [
    '.listing-agent',
    '.agent-info',
    '[data-rf-test-id="listing-agent"]',
    '.agent-basic-details',
    '[class*="ListingAgent"]',
    '[class*="listingAgent"]',
    '.agent-contact'
  ];

  for (const sel of agentSelectors) {
    const section = document.querySelector(sel);
    if (section) {
      // Phone number - look for various patterns
      const phoneMatch = section.textContent.match(/(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/);
      if (phoneMatch) {
        data.listing_agent_phone = phoneMatch[1];
        console.log('Redfin DOM: Found agent phone via', sel);
      }

      // Agent name - look for name-like element, get full text
      const nameEl = section.querySelector('.agent-name, [class*="agentName"], [class*="AgentName"]');
      if (nameEl) {
        const fullName = nameEl.textContent.trim();
        // Only use if it looks like a full name (has space, reasonable length)
        if (fullName.includes(' ') && fullName.length >= 5 && fullName.length <= 50) {
          data.listing_agent_name = fullName;
          console.log('Redfin DOM: Found agent name via element:', data.listing_agent_name);
        }
      }

      // Fallback: extract name from section text using pattern
      if (!data.listing_agent_name) {
        const sectionText = section.textContent || '';
        // Look for name pattern in section - handles McClure, McDonald, etc.
        const nameMatch = sectionText.match(/([A-Z][a-zA-Z'-]+\s+[A-Z][a-zA-Z'-]+)/);
        if (nameMatch && nameMatch[1].length >= 5 && nameMatch[1].length <= 40) {
          // Make sure it's not a common non-name phrase
          const candidate = nameMatch[1];
          if (!/(Real Estate|Realty|Group|Property|Contact|Request)/i.test(candidate)) {
            data.listing_agent_name = candidate;
            console.log('Redfin DOM: Found agent name via section text:', data.listing_agent_name);
          }
        }
      }

      if (data.listing_agent_name || data.listing_agent_phone) break;
    }
  }

  // Look for Contact Agent buttons/links with phone numbers
  if (!data.listing_agent_phone) {
    const contactEls = document.querySelectorAll('a[href^="tel:"], button[class*="contact"], [class*="Contact"]');
    for (const el of contactEls) {
      const href = el.getAttribute('href');
      if (href && href.startsWith('tel:')) {
        data.listing_agent_phone = href.replace('tel:', '').trim();
        console.log('Redfin DOM: Found agent phone via tel: link');
        break;
      }
      // Check text content for phone pattern
      const phoneMatch = el.textContent.match(/(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/);
      if (phoneMatch) {
        data.listing_agent_phone = phoneMatch[1];
        console.log('Redfin DOM: Found agent phone in contact element');
        break;
      }
    }
  }

  // Search body text for phone near agent-related keywords
  if (!data.listing_agent_phone) {
    const phonePatterns = [
      /Contact:\s*(\d{10,})/i,                        // "Contact: 6155455272"
      /Contact:\s*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/i,
      /(?:Agent|Listed by)[^0-9]*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/i,
      /(?:Call|Phone|Tel)[:\s]*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/i
    ];
    for (const pattern of phonePatterns) {
      const match = bodyText.match(pattern);
      if (match) {
        data.listing_agent_phone = match[1];
        console.log('Redfin DOM: Found agent phone via text pattern:', data.listing_agent_phone);
        break;
      }
    }
  }

  // Also search for agent in common page patterns
  if (!data.listing_agent_name) {
    // Pattern handles names like McClure, McDonald, O'Brien, etc.
    const agentPatterns = [
      /(?:Listed by|Listing Agent)[:\s]*([A-Z][a-z]+\s+(?:Mc|Mac|O')[A-Z][a-z]+)/,  // McClure, McDonald, O'Brien
      /(?:Listed by|Listing Agent)[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)/,  // Regular + hyphenated
      /(?:Listed by|Listing Agent)[:\s]*([A-Z][a-zA-Z'-]+\s+[A-Z][a-zA-Z'-]+)/,  // More permissive
    ];
    for (const pattern of agentPatterns) {
      const match = bodyText.match(pattern);
      if (match && match[1].length > 4) {
        data.listing_agent_name = match[1].trim();
        console.log('Redfin DOM: Found agent name via text pattern:', data.listing_agent_name);
        break;
      }
    }
  }

  // Lot size
  const lotMatch = bodyText.match(/([\d,.]+)\s*(?:Acre|AC)\s*(?:Lot)?/i);
  if (lotMatch) data.lot_acres = parseFloat(lotMatch[1].replace(/,/g, ''));

  // HOA - look in property details/facts section first
  const hoaFactsSections = document.querySelectorAll('.amenity-group, .facts-table, [class*="PropertyFacts"], [class*="keyDetails"], .super-group-content, [class*="HomeInfo"]');
  for (const section of hoaFactsSections) {
    const sectionText = section.innerText || '';
    // Look for HOA patterns with amount and frequency
    const hoaPatterns = [
      /HOA\s*(?:Fee|Dues)?[:\s]*\$?([\d,]+)\s*(?:\/\s*(?:mo|month|monthly)|per\s*month)?/i,
      /HOA[:\s]*\$?([\d,]+)/i,
      /(?:Homeowners?|Home\s*Owners?)\s*(?:Association|Assoc\.?)?\s*(?:Fee|Dues)?[:\s]*\$?([\d,]+)/i
    ];
    for (const pattern of hoaPatterns) {
      const match = sectionText.match(pattern);
      if (match) {
        const hoaVal = parseInt(match[1].replace(/,/g, ''));
        // HOA fees are typically $50-$2000/month
        if (hoaVal >= 10 && hoaVal <= 5000) {
          data.hoa_fee = hoaVal;
          console.log('Redfin DOM: Found HOA fee in facts section:', data.hoa_fee);
          break;
        }
      }
    }
    if (data.hoa_fee) break;
  }

  // Fallback: search body text for HOA
  if (!data.hoa_fee) {
    const hoaPatterns = [
      /HOA\s*(?:Fee|Dues)?[:\s]*\$?([\d,]+)\s*(?:\/\s*(?:mo|month)|per\s*month)/i,
      /HOA[:\s]*\$?([\d,]+)/i
    ];
    for (const pattern of hoaPatterns) {
      const match = bodyText.match(pattern);
      if (match) {
        const hoaVal = parseInt(match[1].replace(/,/g, ''));
        if (hoaVal >= 10 && hoaVal <= 5000) {
          data.hoa_fee = hoaVal;
          console.log('Redfin DOM: Found HOA fee via text pattern:', data.hoa_fee);
          break;
        }
      }
    }
  }

  // County - look for county name in the page (more specific patterns)
  const countyPatterns = [
    /(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+County(?:\s|,|$)/gm,  // "Cherokee County" or "Cherokee County,"
    /County:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i,                      // "County: Cherokee"
    /in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+County/i                   // "in Cherokee County"
  ];
  // Words to exclude from county matches
  const countyExclusions = ['or', 'and', 'the', 'realtor', 'real', 'estate', 'your', 'our', 'any', 'some'];
  for (const pattern of countyPatterns) {
    const countyMatch = bodyText.match(pattern);
    if (countyMatch && countyMatch[1]) {
      const candidate = countyMatch[1].trim();
      // Validate: length check and not in exclusions
      if (candidate.length > 3 && candidate.length < 25 &&
          !countyExclusions.includes(candidate.toLowerCase())) {
        data.county = candidate;
        console.log('Redfin DOM: Found county:', data.county);
        break;
      }
    }
  }

  // Status - look for listing status
  const statusPatterns = [
    /Status[:\s]*(Active|Pending|Sold|Under Contract|Contingent|Coming Soon|Off Market|Expired)/i,
    /(Active|Pending|Sold|Under Contract|Contingent)\s*(?:listing|status)?/i
  ];
  for (const pattern of statusPatterns) {
    const statusMatch = bodyText.match(pattern);
    if (statusMatch) {
      data.status = statusMatch[1].toLowerCase();
      console.log('Redfin DOM: Found status:', data.status);
      break;
    }
  }

  // Tax information - look for ANNUAL tax in property details (not monthly payment)
  // Look in property facts/details sections first
  const factsSections = document.querySelectorAll('.amenity-group, .facts-table, [class*="PropertyFacts"], [class*="keyDetails"], .super-group-content');
  for (const section of factsSections) {
    const sectionText = section.innerText || '';
    // Look for annual tax patterns
    const annualTaxPatterns = [
      /(?:Annual\s+)?Tax(?:es)?\s*\$?([\d,]+)\s*(?:\/\s*year|annually|per\s*year)?/i,
      /Tax\s*(?:Amount|Annual)\s*\$?([\d,]+)/i,
      /\$?([\d,]+)\s*(?:\/\s*year|annually)\s*(?:tax|property)/i
    ];
    for (const pattern of annualTaxPatterns) {
      const match = sectionText.match(pattern);
      if (match) {
        const taxVal = parseInt(match[1].replace(/,/g, ''));
        // Annual tax should be reasonable (500 to 100000) - higher threshold than monthly
        if (taxVal >= 500 && taxVal <= 100000) {
          data.tax_annual_amount = taxVal;
          console.log('Redfin DOM: Found annual tax in facts section:', data.tax_annual_amount);
          break;
        }
      }
    }
    if (data.tax_annual_amount) break;
  }

  // Fallback: search full body but be more specific about annual
  if (!data.tax_annual_amount) {
    const annualPatterns = [
      /(?:Property\s+)?Tax(?:es)?[:\s]*\$?([\d,]+)\s*(?:\/\s*year|annually|per\s*year)/i,
      /Annual\s+(?:Property\s+)?Tax(?:es)?[:\s]*\$?([\d,]+)/i,
      /Tax\s+Assessment[:\s]*\$?([\d,]+)/i
    ];
    for (const pattern of annualPatterns) {
      const match = bodyText.match(pattern);
      if (match) {
        const taxVal = parseInt(match[1].replace(/,/g, ''));
        if (taxVal >= 500 && taxVal <= 100000) {
          data.tax_annual_amount = taxVal;
          console.log('Redfin DOM: Found annual tax via text pattern:', data.tax_annual_amount);
          break;
        }
      }
    }
  }

  // Parcel ID / APN - look in facts section (must contain digits)
  const parcelPatterns = [
    /(?:Parcel\s*(?:Number|#|ID)?|APN)[:\s#]*([A-Z0-9][-A-Z0-9.]+[0-9][-A-Z0-9.]*)/i,  // Must have digits
    /(?:Tax\s*(?:ID|Parcel))[:\s#]*([0-9][-A-Z0-9.]+)/i                                  // Tax ID with numbers
  ];
  for (const pattern of parcelPatterns) {
    const match = bodyText.match(pattern);
    // Parcel IDs must contain at least one digit and be reasonable length
    if (match && match[1].length >= 5 && match[1].length <= 30 && /\d/.test(match[1])) {
      data.parcel_id = match[1];
      console.log('Redfin DOM: Found parcel ID:', data.parcel_id);
      break;
    }
  }

  // Latitude/Longitude - try to extract from page scripts or map elements
  // These are often in data attributes or inline scripts
  const mapEl = document.querySelector('[data-lat], [data-latitude], .map-container');
  if (mapEl) {
    const lat = mapEl.getAttribute('data-lat') || mapEl.getAttribute('data-latitude');
    const lng = mapEl.getAttribute('data-lng') || mapEl.getAttribute('data-longitude');
    if (lat) data.latitude = parseFloat(lat);
    if (lng) data.longitude = parseFloat(lng);
  }

  // Also look in inline scripts for coordinates
  if (!data.latitude || !data.longitude) {
    const scripts = document.querySelectorAll('script:not([src])');
    for (const script of scripts) {
      const text = script.textContent || '';
      if (text.includes('latitude') || text.includes('"lat"')) {
        const latMatch = text.match(/"(?:latitude|lat)"\s*:\s*([\d.-]+)/);
        const lngMatch = text.match(/"(?:longitude|lng|long)"\s*:\s*([\d.-]+)/);
        if (latMatch && !data.latitude) data.latitude = parseFloat(latMatch[1]);
        if (lngMatch && !data.longitude) data.longitude = parseFloat(lngMatch[1]);
        if (data.latitude && data.longitude) break;
      }
    }
  }

  console.log('Redfin DOM extracted:', Object.keys(data).filter(k => data[k] !== undefined && data[k] !== null));
  console.log('Redfin DOM critical fields - lat:', data.latitude, 'lng:', data.longitude, 'parcel:', data.parcel_id);
  return data;
}

// ============================================
// HELPER FUNCTIONS
// ============================================
function initRedfinPropertyData() {
  return {
    redfin_id: null,
    mls_number: null,
    mls_source: null,
    address: null,
    city: null,
    state: null,
    zip: null,
    county: null,
    price: null,
    beds: null,
    baths: null,
    sqft: null,
    lot_acres: null,
    year_built: null,
    property_type: null,
    status: null,
    days_on_market: null,
    hoa_fee: null,
    tax_assessed_value: null,
    tax_annual_amount: null,
    page_views: null,
    favorites_count: null,
    parcel_id: null,
    listing_agent_name: null,
    listing_agent_phone: null,
    listing_agent_email: null,
    listing_brokerage: null,
    latitude: null,
    longitude: null,
    heating: null,
    cooling: null,
    garage: null,
    photo_urls: [],
    source: 'redfin',
    url: null,
    scraped_at: null,
    confidence: 0
  };
}

function mergeData(target, source) {
  if (!source) return target;
  for (const key of Object.keys(source)) {
    if (source[key] !== null && source[key] !== undefined && source[key] !== '') {
      target[key] = source[key];
    }
  }
  return target;
}

function parseAddressComponents(address) {
  // Parse city, state, zip from address like "370 Fire House Rd, Otto, NC 28763"
  const result = { city: null, state: null, zip: null };

  if (!address) return result;

  // Pattern: "Street, City, ST ZIP" or "Street, City, ST"
  const match = address.match(/,\s*([^,]+),\s*([A-Z]{2})\s*(\d{5})?/);
  if (match) {
    result.city = match[1].trim();
    result.state = match[2];
    if (match[3]) result.zip = match[3];
  }

  // Try alternate pattern: just "City, ST ZIP" at the end
  if (!result.city) {
    const altMatch = address.match(/([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})/);
    if (altMatch) {
      result.city = altMatch[1].trim();
      result.state = altMatch[2];
      result.zip = altMatch[3];
    }
  }

  return result;
}

function parseLotSize(raw) {
  if (raw.lotSize?.value) {
    const val = raw.lotSize.value;
    const unit = raw.lotSize.unit || '';
    if (unit.toLowerCase().includes('acre')) return val;
    if (val > 100) return Math.round((val / 43560) * 100) / 100; // sqft to acres
    return val;
  }
  if (raw.lotSqFt) {
    return Math.round((raw.lotSqFt / 43560) * 100) / 100;
  }
  return null;
}

function extractAmenity(amenities, ...keywords) {
  if (!amenities) return null;
  for (const item of amenities) {
    const name = (item.name || item.amenityName || '').toLowerCase();
    for (const kw of keywords) {
      if (name.includes(kw)) {
        return item.value || item.repiValue || item.amenityValue || name;
      }
    }
  }
  return null;
}

function calculateConfidence(data) {
  let score = 0;
  const required = ['address', 'price', 'beds', 'baths'];
  const optional = ['sqft', 'year_built', 'mls_number', 'listing_agent_name', 'lot_acres'];

  for (const f of required) if (data[f]) score += 20;
  for (const f of optional) if (data[f]) score += 4;

  return Math.min(score, 100);
}

// ============================================
// DIAGNOSTIC: DUMP ALL AVAILABLE DATA
// Run window.RedfinScraper.dumpAllData() in console
// ============================================
function dumpAllAvailableData() {
  console.log('=== REDFIN COMPLETE DATA DUMP ===');
  const allData = {};

  // Method 1: Find ALL JSON objects in scripts
  const scripts = document.querySelectorAll('script:not([src])');
  console.log(`Scanning ${scripts.length} inline scripts...`);

  for (let i = 0; i < scripts.length; i++) {
    const text = scripts[i].textContent || '';
    if (text.length < 500) continue;

    // Look for large JSON assignments
    const assignments = [
      /root\.__reactServerState\s*=\s*(\{[\s\S]*?\});?\s*(?=root\.|window\.|<\/script|$)/,
      /window\.__reactServerState\s*=\s*(\{[\s\S]*?\});?\s*(?=window\.|$)/,
      /window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]*?\});/,
      /window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});/,
    ];

    for (const pattern of assignments) {
      const match = text.match(pattern);
      if (match) {
        try {
          const parsed = JSON.parse(match[1]);
          console.log(`Found data blob (${Object.keys(parsed).length} top-level keys)`);

          // Deep search for property-related data
          const propertyData = deepExtractAllFields(parsed, 'root', 0);
          Object.assign(allData, propertyData);
        } catch (e) {
          console.log('Parse failed for pattern, trying brace-matching...');
          // Try brace matching
          const startIdx = text.indexOf(match[0]);
          const jsonStart = text.indexOf('{', startIdx);
          if (jsonStart > -1) {
            const jsonStr = extractJsonObject(text, jsonStart);
            if (jsonStr) {
              try {
                const parsed = JSON.parse(jsonStr);
                const propertyData = deepExtractAllFields(parsed, 'root', 0);
                Object.assign(allData, propertyData);
              } catch (e2) {}
            }
          }
        }
      }
    }
  }

  // Method 2: Check window objects directly
  if (window.__reactServerState) {
    console.log('Found window.__reactServerState');
    const data = deepExtractAllFields(window.__reactServerState, 'serverState', 0);
    Object.assign(allData, data);
  }

  // Log all found fields
  const fieldNames = Object.keys(allData).sort();
  console.log(`\n=== FOUND ${fieldNames.length} UNIQUE FIELDS ===`);

  // Group by category
  const categories = {
    'Address': fieldNames.filter(f => /address|street|city|state|zip|county/i.test(f)),
    'Price': fieldNames.filter(f => /price|cost|value|zestimate/i.test(f)),
    'Property': fieldNames.filter(f => /bed|bath|sqft|lot|acre|year|type|style/i.test(f)),
    'Agent': fieldNames.filter(f => /agent|broker|office|phone|email/i.test(f)),
    'MLS': fieldNames.filter(f => /mls|listing|source/i.test(f)),
    'Tax': fieldNames.filter(f => /tax|assess/i.test(f)),
    'Stats': fieldNames.filter(f => /view|favorite|save|dom|days/i.test(f)),
    'Location': fieldNames.filter(f => /lat|lng|long|coord/i.test(f)),
  };

  for (const [cat, fields] of Object.entries(categories)) {
    if (fields.length > 0) {
      console.log(`\n--- ${cat} ---`);
      fields.forEach(f => console.log(`  ${f}: ${JSON.stringify(allData[f])}`));
    }
  }

  console.log('\n=== ALL DATA AS OBJECT ===');
  console.log(allData);

  return allData;
}

function deepExtractAllFields(obj, path, depth) {
  const result = {};
  if (depth > 12 || !obj || typeof obj !== 'object') return result;

  // Skip arrays of non-objects (like photo URLs)
  if (Array.isArray(obj)) {
    if (obj.length > 0 && typeof obj[0] !== 'object') {
      return result;
    }
    for (let i = 0; i < Math.min(obj.length, 3); i++) {
      Object.assign(result, deepExtractAllFields(obj[i], `${path}[${i}]`, depth + 1));
    }
    return result;
  }

  // Property-like field names we want to capture
  const interestingFields = [
    'beds', 'baths', 'sqft', 'sqFt', 'price', 'listPrice', 'salePrice',
    'address', 'streetAddress', 'city', 'state', 'zip', 'zipCode', 'county', 'countyName',
    'propertyId', 'listingId', 'mlsId', 'mlsNumber', 'mlsSource', 'sourceName',
    'status', 'listingStatus', 'propertyType', 'homeType',
    'yearBuilt', 'lotSize', 'lotSqFt', 'lotAcres', 'acreage',
    'latitude', 'longitude', 'lat', 'lng',
    'dom', 'daysOnMarket', 'timeOnRedfin',
    'pageViews', 'views', 'favorites', 'saves', 'numFavorites',
    'taxAssessedValue', 'taxAnnualAmount', 'taxes', 'propertyTax',
    'hoaDues', 'hoaFee', 'hoa',
    'listingAgent', 'agentName', 'agentPhone', 'agentEmail', 'brokerName', 'brokerageName',
    'parcelId', 'parcelNumber', 'apn',
    'zestimate', 'rentZestimate', 'pricePerSqFt',
    'heating', 'cooling', 'garage', 'parking',
    'stories', 'subdivision', 'neighborhood',
  ];

  for (const key of Object.keys(obj)) {
    const val = obj[key];
    const lowerKey = key.toLowerCase();

    // Check if this is an interesting field
    const isInteresting = interestingFields.some(f => lowerKey.includes(f.toLowerCase()));

    if (isInteresting && val !== null && val !== undefined && val !== '') {
      // For nested objects with a value property, extract the value
      if (typeof val === 'object' && !Array.isArray(val) && val.value !== undefined) {
        result[key] = val.value;
      } else if (typeof val !== 'object') {
        result[key] = val;
      } else if (typeof val === 'object' && !Array.isArray(val)) {
        // For agent objects, flatten them
        if (lowerKey.includes('agent') || lowerKey.includes('broker')) {
          for (const [k, v] of Object.entries(val)) {
            if (v && typeof v !== 'object') {
              result[`${key}_${k}`] = v;
            }
          }
        }
      }
    }

    // Recurse into objects
    if (typeof val === 'object' && val !== null) {
      // Skip known non-property paths
      const skipPaths = ['schools', 'similarHomes', 'nearbyHomes', 'comparables', 'photos', 'floorPlans'];
      if (!skipPaths.includes(key)) {
        Object.assign(result, deepExtractAllFields(val, `${path}.${key}`, depth + 1));
      }
    }
  }

  return result;
}

function extractJsonObject(text, startIdx) {
  let depth = 0;
  let inString = false;
  let escape = false;

  for (let i = startIdx; i < text.length && i < startIdx + 500000; i++) {
    const char = text[i];

    if (escape) {
      escape = false;
      continue;
    }

    if (char === '\\' && inString) {
      escape = true;
      continue;
    }

    if (char === '"' && !escape) {
      inString = !inString;
      continue;
    }

    if (!inString) {
      if (char === '{') depth++;
      else if (char === '}') {
        depth--;
        if (depth === 0) {
          return text.substring(startIdx, i + 1);
        }
      }
    }
  }
  return null;
}

// Export for use in main content script
window.RedfinScraper = {
  detectPageType: detectRedfinPageType,
  scrapeProperty: scrapeRedfinProperty,
  scrapeSearchResults: scrapeRedfinSearchResults,
  dumpAllData: dumpAllAvailableData
};

console.log('Redfin scraper v' + REDFIN_VERSION + ' ready');
