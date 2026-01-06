// content.js - Enhanced Zillow Data Extraction
// Extracts data from: embedded JSON, API interception, and DOM scraping

console.log('myDREAMS Property Capture v2: Content script loaded');

// ============================================================================
// MAIN MESSAGE HANDLER
// ============================================================================
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrapeProperty') {
    console.log('Scraping single property...');
    const data = scrapeCurrentProperty();
    sendResponse(data);
  } else if (request.action === 'scrapeSearchResults') {
    console.log('Scraping search results...');
    const data = scrapeSearchResults();
    sendResponse(data);
  } else if (request.action === 'getPageType') {
    sendResponse({ pageType: detectPageType() });
  }
  return true;
});

// ============================================================================
// PAGE TYPE DETECTION
// ============================================================================
function detectPageType() {
  const url = window.location.href;
  
  // Property detail pages
  if (url.includes('/homedetails/') || url.includes('_zpid')) {
    return 'property';
  }
  
  // Search results pages - various formats
  if (url.includes('/homes/') || 
      url.includes('/for_sale/') ||
      url.includes('/sold/') ||
      url.includes('searchQueryState') ||
      url.match(/zillow\.com\/[a-zA-Z-]+\/$/)) {
    return 'search';
  }
  
  // Check if there's property data on the page (backup detection)
  const hasPropertyData = document.querySelector('[data-testid="price"]') || 
                          document.querySelector('.summary-container') ||
                          document.body.textContent.includes('Zestimate');
  if (hasPropertyData) {
    return 'property';
  }
  
  // Check for search results
  const hasSearchResults = document.querySelector('[data-test="property-card"]') ||
                           document.querySelector('article[data-test]');
  if (hasSearchResults) {
    return 'search';
  }
  
  return 'unknown';
}

// ============================================================================
// SINGLE PROPERTY EXTRACTION (Detail Page)
// ============================================================================
function scrapeCurrentProperty() {
  let data = initPropertyData();
  
  // FIRST: Get ZPID from URL - this is our anchor
  const zpidMatch = window.location.href.match(/(\d+)_zpid/);
  const targetZpid = zpidMatch ? zpidMatch[1] : null;
  console.log('Target ZPID from URL:', targetZpid);
  
  // Method 1: Extract from embedded JSON (most reliable, has everything)
  // But ONLY if it matches our target ZPID
  const embeddedData = extractEmbeddedJSON(targetZpid);
  if (embeddedData) {
    data = mergePropertyData(data, embeddedData);
    console.log('Extracted from embedded JSON:', data);
  }
  
  // Method 2: DOM scraping (backup/supplement) - also ZPID-aware
  const domData = scrapeDOMData(targetZpid);
  data = mergePropertyData(data, domData);
  
  // Set ZPID if we found it
  if (!data.zpid && targetZpid) {
    data.zpid = targetZpid;
  }
  
  data.source = 'Zillow';
  data.url = window.location.href;
  data.scrapedAt = new Date().toISOString();
  
  console.log('Final scraped data:', data);
  return data;
}

// ============================================================================
// EMBEDDED JSON EXTRACTION (The Gold Mine!)
// ============================================================================
function extractEmbeddedJSON(targetZpid) {
  // Zillow embeds property data in script tags
  // Look for Next.js data, Apollo cache, or direct JSON
  
  let propertyData = null;
  
  // Method 1: __NEXT_DATA__ (Next.js apps)
  const nextDataScript = document.getElementById('__NEXT_DATA__');
  if (nextDataScript) {
    try {
      const nextData = JSON.parse(nextDataScript.textContent);
      propertyData = extractFromNextData(nextData, targetZpid);
      if (propertyData) return propertyData;
    } catch (e) {
      console.log('Failed to parse __NEXT_DATA__:', e);
    }
  }
  
  // Method 2: Look for inline scripts with property data
  const scripts = document.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    
    // Look for Apollo/GraphQL cache
    if (text.includes('__APOLLO_STATE__') || text.includes('gdpClientCache')) {
      try {
        // Extract JSON object
        const match = text.match(/window\.__APOLLO_STATE__\s*=\s*({.+?});/s) ||
                      text.match(/gdpClientCache\s*=\s*({.+?});/s);
        if (match) {
          const apolloData = JSON.parse(match[1]);
          propertyData = extractFromApolloCache(apolloData, targetZpid);
          if (propertyData) return propertyData;
        }
      } catch (e) {
        console.log('Failed to parse Apollo cache:', e);
      }
    }
    
    // Look for preloaded data with matching ZPID
    if (targetZpid && text.includes(`"zpid":${targetZpid}`) || text.includes(`"zpid":"${targetZpid}"`)) {
      try {
        // Try to extract property object for this specific ZPID
        const propertyMatch = text.match(new RegExp(`"zpid"\\s*:\\s*${targetZpid}[^}]+(?:{[^}]*}[^}]*)*}`));
        if (propertyMatch) {
          // Find the complete object containing this zpid
          propertyData = findPropertyObjectWithZpid(text, targetZpid);
          if (propertyData) return normalizePropertyData(propertyData);
        }
      } catch (e) {
        // Continue to next script
      }
    }
  }
  
  // Method 3: Check for data in global variables
  try {
    if (window.__PRELOADED_STATE__) {
      propertyData = extractFromPreloadedState(window.__PRELOADED_STATE__, targetZpid);
      if (propertyData) return propertyData;
    }
  } catch (e) {}
  
  return null;
}

function findPropertyObjectWithZpid(text, targetZpid) {
  // Try to find a complete property object with this ZPID
  // This is tricky because we need to match balanced braces
  
  const zpidIndex = text.indexOf(`"zpid":${targetZpid}`);
  if (zpidIndex === -1) {
    const altIndex = text.indexOf(`"zpid":"${targetZpid}"`);
    if (altIndex === -1) return null;
  }
  
  // For now, try to parse key fields directly around this zpid
  return null; // Let other methods handle it
}

function extractFromNextData(nextData, targetZpid) {
  try {
    // Navigate Next.js data structure to find property
    const props = nextData.props?.pageProps;
    
    // Check initialData.property first
    if (props?.initialData?.property) {
      const prop = props.initialData.property;
      if (!targetZpid || prop.zpid?.toString() === targetZpid) {
        return normalizePropertyData(prop);
      }
    }
    
    // Check direct property
    if (props?.property) {
      const prop = props.property;
      if (!targetZpid || prop.zpid?.toString() === targetZpid) {
        return normalizePropertyData(prop);
      }
    }
    
    // Deep search for property object with matching ZPID
    if (targetZpid) {
      const property = deepFindByZpid(nextData, targetZpid);
      if (property) return normalizePropertyData(property);
    }
  } catch (e) {
    console.log('Error extracting from Next.js data:', e);
  }
  return null;
}

function extractFromApolloCache(cache, targetZpid) {
  // Apollo cache stores data with keys like "Property:123456"
  
  // First, try to find by exact ZPID key
  if (targetZpid) {
    const exactKey = `Property:${targetZpid}`;
    if (cache[exactKey]) {
      return normalizePropertyData(cache[exactKey]);
    }
  }
  
  // Search for ForSaleShopperPlatformFullRenderQuery or similar
  for (const key of Object.keys(cache)) {
    if (key.includes('ForSaleShopperPlatformFullRenderQuery') || 
        key.includes('FullRenderQuery')) {
      const data = cache[key];
      if (data?.property) {
        const prop = data.property;
        if (!targetZpid || prop.zpid?.toString() === targetZpid) {
          return normalizePropertyData(prop);
        }
      }
    }
  }
  
  // Last resort: search all properties
  for (const key of Object.keys(cache)) {
    if (key.startsWith('Property:')) {
      const data = cache[key];
      if (data && data.zpid) {
        if (!targetZpid || data.zpid.toString() === targetZpid) {
          return normalizePropertyData(data);
        }
      }
    }
  }
  
  return null;
}

function extractFromPreloadedState(state, targetZpid) {
  if (targetZpid) {
    const property = deepFindByZpid(state, targetZpid);
    if (property) return normalizePropertyData(property);
  }
  return null;
}

function deepFindByZpid(obj, targetZpid) {
  // Recursively find a property object with the matching ZPID
  if (!obj || typeof obj !== 'object') return null;
  
  // Check if this object has the matching zpid
  if (obj.zpid !== undefined) {
    if (obj.zpid.toString() === targetZpid) {
      return obj;
    }
    // This is a property but wrong zpid, don't search its children
    return null;
  }
  
  // Search children
  for (const key of Object.keys(obj)) {
    // Skip arrays of comps/comparables
    if (key === 'comps' || key === 'comparables' || key === 'nearbyHomes') {
      continue;
    }
    const result = deepFindByZpid(obj[key], targetZpid);
    if (result) return result;
  }
  
  return null;
}

// ============================================================================
// NORMALIZE PROPERTY DATA (Convert Zillow format to our format)
// ============================================================================
function normalizePropertyData(zillowData) {
  const data = initPropertyData();
  
  // Basic info
  data.zpid = zillowData.zpid?.toString() || null;
  data.price = zillowData.price || zillowData.listPrice || null;
  data.bedrooms = zillowData.bedrooms || zillowData.beds || null;
  data.bathrooms = zillowData.bathrooms || zillowData.baths || null;
  data.sqft = zillowData.livingArea || zillowData.livingAreaValue || null;
  data.lotSize = zillowData.lotSize || null;
  data.lotAcres = zillowData.lotAreaValue || (data.lotSize ? data.lotSize / 43560 : null);
  data.yearBuilt = zillowData.yearBuilt || null;
  data.homeType = zillowData.homeType || zillowData.propertyTypeDimension || null;
  data.homeStatus = zillowData.homeStatus || null;
  data.hoaFee = zillowData.monthlyHoaFee || zillowData.hoaFee || null;
  
  // Address
  if (zillowData.address) {
    data.address = zillowData.address.streetAddress || null;
    data.city = zillowData.address.city || null;
    data.state = zillowData.address.state || null;
    data.zipcode = zillowData.address.zipcode || null;
  }
  
  // County - validate it's a real county name (3+ chars, not common words)
  if (zillowData.county && zillowData.county.length >= 3) {
    const county = zillowData.county;
    const invalidCounties = ['the', 'this', 'that', 'and', 'for', 'not'];
    if (!invalidCounties.includes(county.toLowerCase())) {
      data.county = county;
    }
  }
  
  // Location
  data.latitude = zillowData.latitude || null;
  data.longitude = zillowData.longitude || null;
  
  // MLS & Listing Info
  if (zillowData.attributionInfo) {
    data.mlsId = zillowData.attributionInfo.mlsId || null;
    data.mlsSource = zillowData.attributionInfo.mlsName || null;  // MLS Source
    data.agentName = zillowData.attributionInfo.agentName || null;
    
    // Check agentPhoneNumber field - could be phone OR email
    const agentPhoneValue = zillowData.attributionInfo.agentPhoneNumber || null;
    if (agentPhoneValue) {
      if (agentPhoneValue.includes('@')) {
        // It's actually an email stored in the phone field
        data.agentEmail = agentPhoneValue;
      } else if (agentPhoneValue.match(/\d{7,}/)) {
        // It's a real phone number
        data.agentPhone = agentPhoneValue;
      }
    }
    
    // Check dedicated email field (may exist separately)
    if (zillowData.attributionInfo.agentEmail) {
      data.agentEmail = zillowData.attributionInfo.agentEmail;
    }
    
    // Check broker phone for agent phone (sometimes listed there)
    if (!data.agentPhone && zillowData.attributionInfo.brokerPhoneNumber) {
      const brokerPhone = zillowData.attributionInfo.brokerPhoneNumber;
      if (brokerPhone.match(/\d{7,}/) && !brokerPhone.includes('@')) {
        // Don't overwrite - broker phone is different
        data.brokerPhone = brokerPhone;
      }
    }
    
    data.brokerName = zillowData.attributionInfo.brokerName || null;
    if (!data.brokerPhone) {
      data.brokerPhone = zillowData.attributionInfo.brokerPhoneNumber || null;
    }
  }
  
  // Parcel & Tax Info
  data.parcelId = zillowData.parcelId || zillowData.parcelNumber || null;
  data.taxAssessedValue = zillowData.taxAssessedValue || null;
  data.taxAnnualAmount = zillowData.taxAnnualAmount || null;
  data.lastTaxPaid = zillowData.taxAnnualAmount || zillowData.propertyTaxRate || null;
  
  // Sale History - get last sale from priceHistory if available
  if (zillowData.priceHistory && Array.isArray(zillowData.priceHistory)) {
    // Find the most recent SOLD entry
    const soldEntry = zillowData.priceHistory.find(entry => 
      entry.event === 'Sold' || entry.event === 'SOLD'
    );
    if (soldEntry) {
      data.lastSalePrice = soldEntry.price || null;
      data.lastSaleDate = soldEntry.date || null;
    }
  }
  
  // Zillow Metrics - note: zestimate only captured if visible on page (handled in scrapeDOMData)
  data.daysOnZillow = zillowData.daysOnZillow || zillowData.timeOnZillow || null;
  data.pageViewCount = zillowData.pageViewCount || zillowData.pageViews || null;
  data.favoriteCount = zillowData.favoriteCount || zillowData.savedCount || null;
  // zestimate intentionally not set here - only captured if displayed on page
  data.rentZestimate = zillowData.rentZestimate || null;
  
  // Listing details
  data.description = zillowData.description || null;
  data.datePosted = zillowData.datePosted || zillowData.dateSold || null;
  
  // Photos
  if (zillowData.photos || zillowData.miniCardPhotos) {
    const photos = zillowData.photos || zillowData.miniCardPhotos;
    data.photoCount = photos.length;
    data.primaryPhoto = photos[0]?.url || photos[0]?.mixedSources?.jpeg?.[0]?.url || null;
  }
  
  // Price history
  if (zillowData.priceHistory) {
    data.priceHistory = zillowData.priceHistory;
  }
  
  // Tax history  
  if (zillowData.taxHistory) {
    data.taxHistory = zillowData.taxHistory;
    // Try to get last tax paid from tax history
    if (!data.lastTaxPaid && Array.isArray(zillowData.taxHistory) && zillowData.taxHistory.length > 0) {
      data.lastTaxPaid = zillowData.taxHistory[0].taxPaid || zillowData.taxHistory[0].value || null;
    }
  }
  
  return data;
}

// ============================================================================
// DOM SCRAPING (Backup method)
// ============================================================================
function scrapeDOMData(targetZpid) {
  const data = initPropertyData();
  const bodyText = document.body.textContent;
  
  // Check once if Zestimate is visible on the page
  const hasVisibleZestimate = bodyText.includes('Zestimate') && 
                              (bodyText.match(/Zestimate[:\s®]*\$[\d,]+/) || 
                               bodyText.match(/\$[\d,]+\s*Zestimate/));
  
  // IMPORTANT: For Zestimate, Views, Saves - scrape from visible DOM, not JSON
  // This ensures we get the actual displayed values, not comp data
  
  // Extract visible Zestimate from DOM
  if (hasVisibleZestimate) {
    const zestimateMatch = bodyText.match(/\$\s*([\d,]+)\s*Zestimate/) ||
                           bodyText.match(/Zestimate[®\s]*\$\s*([\d,]+)/);
    if (zestimateMatch) {
      data.zestimate = parseInt(zestimateMatch[1].replace(/,/g, ''));
    }
  }
  
  // Extract visible Views and Saves from DOM
  const viewsSavesMatch = bodyText.match(/(\d[\d,]*)\s*views?\s*[|\s]+(\d+)\s*saves?/i);
  if (viewsSavesMatch) {
    data.pageViewCount = parseInt(viewsSavesMatch[1].replace(/,/g, ''));
    data.favoriteCount = parseInt(viewsSavesMatch[2]);
  } else {
    // Try separate patterns
    const viewsMatch = bodyText.match(/(\d[\d,]*)\s*views?/i);
    if (viewsMatch) data.pageViewCount = parseInt(viewsMatch[1].replace(/,/g, ''));
    
    const savesMatch = bodyText.match(/(\d+)\s*saves?/i);
    if (savesMatch) data.favoriteCount = parseInt(savesMatch[1]);
  }
  
  // Also check all script tags for embedded JSON data - but ONLY for target ZPID
  const scripts = document.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    
    // Only process scripts that contain our target ZPID
    if (targetZpid && !text.includes(targetZpid)) {
      continue;
    }
    
    if (text.includes('zpid')) {
      // Extract bedrooms - multiple patterns
      if (!data.bedrooms) {
        const bedsMatch = text.match(/"numberOfBedrooms"\s*:\s*(\d+)/) ||
                          text.match(/"bedrooms"\s*:\s*(\d+)/) ||
                          text.match(/\\"bedrooms\\":\s*(\d+)/) ||
                          text.match(/"beds"\s*:\s*(\d+)/);
        if (bedsMatch) data.bedrooms = parseInt(bedsMatch[1]);
      }
      
      // Extract bathrooms - multiple patterns
      if (!data.bathrooms) {
        const bathsMatch = text.match(/"numberOfBathrooms"\s*:\s*([\d.]+)/) ||
                           text.match(/"bathrooms"\s*:\s*([\d.]+)/) ||
                           text.match(/\\"bathrooms\\":\s*([\d.]+)/) ||
                           text.match(/"baths"\s*:\s*([\d.]+)/);
        if (bathsMatch) data.bathrooms = parseFloat(bathsMatch[1]);
      }
      
      // Extract sqft
      if (!data.sqft) {
        const sqftMatch = text.match(/"livingArea"\s*:\s*(\d+)/) ||
                          text.match(/"livingAreaValue"\s*:\s*(\d+)/) ||
                          text.match(/\\"livingArea\\":\s*(\d+)/);
        if (sqftMatch) data.sqft = parseInt(sqftMatch[1]);
      }
      
      // Extract lot size / acreage
      if (!data.lotAcres) {
        const lotMatch = text.match(/"lotAreaValue"\s*:\s*([\d.]+)/) ||
                         text.match(/\\"lotAreaValue\\":\s*([\d.]+)/);
        if (lotMatch) {
          const val = parseFloat(lotMatch[1]);
          // Check if it's already in acres (small number) or sqft (large number)
          if (val < 100) {
            data.lotAcres = val;
          } else {
            data.lotAcres = val / 43560; // Convert sqft to acres
          }
        }
      }
      
      // Extract latitude/longitude
      if (!data.latitude) {
        const latMatch = text.match(/"latitude"\s*:\s*([\d.-]+)/) ||
                         text.match(/\\"latitude\\":\s*([\d.-]+)/);
        if (latMatch) data.latitude = parseFloat(latMatch[1]);
      }
      if (!data.longitude) {
        const lngMatch = text.match(/"longitude"\s*:\s*([\d.-]+)/) ||
                         text.match(/\\"longitude\\":\s*([\d.-]+)/);
        if (lngMatch) data.longitude = parseFloat(lngMatch[1]);
      }
      
      // Extract agent/broker info
      if (!data.agentName) {
        const agentMatch = text.match(/"agentName"\s*:\s*"([^"]+)"/) ||
                           text.match(/\\"agentName\\":\s*\\"([^\\]+)\\"/);
        if (agentMatch) data.agentName = agentMatch[1];
      }
      if (!data.brokerName) {
        const brokerMatch = text.match(/"brokerName"\s*:\s*"([^"]+)"/) ||
                            text.match(/\\"brokerName\\":\s*\\"([^\\]+)\\"/);
        if (brokerMatch) data.brokerName = brokerMatch[1];
      }
      
      // Extract MLS ID
      if (!data.mlsId) {
        const mlsMatch = text.match(/"mlsId"\s*:\s*"([^"]+)"/) ||
                         text.match(/\\"mlsId\\":\s*\\"([^\\]+)\\"/);
        if (mlsMatch) data.mlsId = mlsMatch[1];
      }
      
      // Extract MLS Source
      if (!data.mlsSource) {
        const mlsSourceMatch = text.match(/"mlsName"\s*:\s*"([^"]+)"/) ||
                               text.match(/\\"mlsName\\":\s*\\"([^\\]+)\\"/);
        if (mlsSourceMatch) data.mlsSource = mlsSourceMatch[1];
      }
      
      // Extract county from JSON (with validation)
      if (!data.county) {
        const countyJsonMatch = text.match(/"county"\s*:\s*"([^"]+)"/) ||
                                text.match(/\\"county\\":\s*\\"([^\\]+)\\"/);
        if (countyJsonMatch) {
          const county = countyJsonMatch[1];
          const invalidCounties = ['the', 'this', 'that', 'and', 'for', 'not', 'a', 'an'];
          if (county.length >= 3 && !invalidCounties.includes(county.toLowerCase())) {
            data.county = county;
          }
        }
      }
      
      // Extract home status
      if (!data.homeStatus) {
        const statusMatch = text.match(/"homeStatus"\s*:\s*"([^"]+)"/) ||
                            text.match(/\\"homeStatus\\":\s*\\"([^\\]+)\\"/);
        if (statusMatch) data.homeStatus = statusMatch[1];
      }
      
      // Extract HOA fee
      if (!data.hoaFee) {
        const hoaMatch = text.match(/"monthlyHoaFee"\s*:\s*(\d+)/) ||
                         text.match(/"hoaFee"\s*:\s*(\d+)/) ||
                         text.match(/\\"monthlyHoaFee\\":\s*(\d+)/);
        if (hoaMatch) data.hoaFee = parseInt(hoaMatch[1]);
      }
      
      // Extract home type / style
      if (!data.homeType) {
        const typeMatch = text.match(/"homeType"\s*:\s*"([^"]+)"/) ||
                          text.match(/"propertyTypeDimension"\s*:\s*"([^"]+)"/) ||
                          text.match(/\\"homeType\\":\s*\\"([^\\]+)\\"/);
        if (typeMatch) data.homeType = typeMatch[1];
      }
      
      // Extract agent phone - look for phone number pattern (digits only)
      if (!data.agentPhone) {
        const phoneMatch = text.match(/"agentPhoneNumber"\s*:\s*"(\+?[\d\s\-\(\)]{10,})"/) ||
                           text.match(/\\"agentPhoneNumber\\":\s*\\"(\+?[\d\s\-\(\)]{10,})\\"/);
        if (phoneMatch && !phoneMatch[1].includes('@')) {
          data.agentPhone = phoneMatch[1];
        }
      }
      
      // Extract agent email - look for @ symbol
      if (!data.agentEmail) {
        // Check agentPhoneNumber field (sometimes Zillow puts email here)
        const contactMatch = text.match(/"agentPhoneNumber"\s*:\s*"([^"]+@[^"]+)"/) ||
                             text.match(/\\"agentPhoneNumber\\":\s*\\"([^\\]+@[^\\]+)\\"/);
        if (contactMatch) {
          data.agentEmail = contactMatch[1];
        }
        
        // Also check dedicated agentEmail field
        if (!data.agentEmail) {
          const emailMatch = text.match(/"agentEmail"\s*:\s*"([^"]+@[^"]+)"/) ||
                             text.match(/\\"agentEmail\\":\s*\\"([^\\]+@[^\\]+)\\"/);
          if (emailMatch) {
            data.agentEmail = emailMatch[1];
          }
        }
      }
    }
  }
  
  // Address from h1 or structured data
  const h1 = document.querySelector('h1');
  if (h1) {
    const addrMatch = h1.textContent.match(/(.+),\s*(.+),\s*([A-Z]{2})\s*(\d{5})/);
    if (addrMatch) {
      data.address = addrMatch[1].trim();
      data.city = addrMatch[2].trim();
      data.state = addrMatch[3];
      data.zipcode = addrMatch[4];
    }
  }
  
  // Price from DOM
  if (!data.price) {
    const priceEl = document.querySelector('[data-testid="price"] span, .summary-container .price');
    if (priceEl) {
      data.price = parsePrice(priceEl.textContent);
    } else {
      const priceMatch = bodyText.match(/\$\s*([\d,]+)/);
      if (priceMatch) data.price = parsePrice(priceMatch[0]);
    }
  }
  
  // Year Built from DOM
  if (!data.yearBuilt) {
    const yearMatch = bodyText.match(/Year\s*[Bb]uilt:?\s*(\d{4})/) ||
                      bodyText.match(/Built\s*(?:in\s*)?(\d{4})/);
    if (yearMatch) data.yearBuilt = parseInt(yearMatch[1]);
  }
  
  // Days on Zillow from DOM
  if (!data.daysOnZillow) {
    const domMatch = bodyText.match(/(\d+)\s*days?\s*on\s*[Zz]illow/);
    if (domMatch) data.daysOnZillow = parseInt(domMatch[1]);
  }
  
  // Parcel ID from DOM - match "Parcel number: 7505517842" format
  if (!data.parcelId) {
    const parcelMatch = bodyText.match(/Parcel\s*(?:number|ID|#)\s*:?\s*(\d{7,15})/i);
    if (parcelMatch) data.parcelId = parcelMatch[1];
  }
  
  // MLS Source from visible text (backup)
  if (!data.mlsSource) {
    const sourceMatch = bodyText.match(/Source:\s*([^,]+(?:MLS|Realty|Board)[^,]*)/i);
    if (sourceMatch) data.mlsSource = sourceMatch[1].trim();
  }
  
  // County from visible text - look for "X County" pattern
  if (!data.county) {
    // Pattern: Look for proper noun + "County" (at least 3 chars, starts uppercase)
    // Avoid matching "the County" or similar
    const countyMatch = bodyText.match(/\b([A-Z][a-z]{2,})\s+County\b/);
    if (countyMatch) {
      const county = countyMatch[1].trim();
      // Skip common words that might precede "County"
      if (!['The', 'This', 'That', 'Each', 'Every', 'Any'].includes(county)) {
        data.county = county;
      }
    }
  }
  
  // Last Sale Price and Date from visible text
  if (!data.lastSalePrice) {
    // Look for "Sold: $XXX,XXX on MM/DD/YYYY" or similar patterns
    const saleMatch = bodyText.match(/Sold[:\s]+\$\s*([\d,]+)(?:\s+on\s+|\s+)(\d{1,2}\/\d{1,2}\/\d{2,4})/i) ||
                      bodyText.match(/Last\s+sold[:\s]+\$\s*([\d,]+)/i);
    if (saleMatch) {
      data.lastSalePrice = parseInt(saleMatch[1].replace(/,/g, ''));
      if (saleMatch[2]) {
        // Convert date to ISO format
        const dateParts = saleMatch[2].split('/');
        if (dateParts.length === 3) {
          let year = dateParts[2];
          if (year.length === 2) year = '20' + year;
          data.lastSaleDate = `${year}-${dateParts[0].padStart(2, '0')}-${dateParts[1].padStart(2, '0')}`;
        }
      }
    }
  }
  
  // Tax paid from visible text
  if (!data.lastTaxPaid) {
    const taxMatch = bodyText.match(/(?:Property\s+)?[Tt]ax(?:es)?[:\s]+\$\s*([\d,]+)(?:\s*\/\s*year)?/i) ||
                     bodyText.match(/Annual\s+tax[:\s]+\$\s*([\d,]+)/i);
    if (taxMatch) data.lastTaxPaid = parseInt(taxMatch[1].replace(/,/g, ''));
  }
  
  // Agent phone from visible DOM text - look for phone number pattern near agent info
  if (!data.agentPhone) {
    // Look for "Listing provided by: Name phone" or similar patterns
    const listingByMatch = bodyText.match(/Listing\s+(?:provided\s+)?by[:\s]*([^,\n]+?)[\s,]+(\(?[\d]{3}\)?[\s.-]?[\d]{3}[\s.-]?[\d]{4})/i);
    if (listingByMatch) {
      data.agentPhone = listingByMatch[2].replace(/[^\d]/g, '').replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3');
    }
  }
  
  // Agent email from visible DOM text
  if (!data.agentEmail) {
    // Look for email near "Listing provided by" or agent name
    const emailInTextMatch = bodyText.match(/Listing\s+(?:provided\s+)?by[:\s]*[^@\n]*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/i);
    if (emailInTextMatch) {
      data.agentEmail = emailInTextMatch[1];
    }
  }
  
  return data;
}

// ============================================================================
// SEARCH RESULTS SCRAPING (Bulk Mode)
// ============================================================================
function scrapeSearchResults() {
  const results = [];
  
  // Method 1: Try to extract from embedded search results JSON (gets ALL results)
  const embeddedResults = extractSearchResultsJSON();
  if (embeddedResults && embeddedResults.length > 0) {
    console.log(`Found ${embeddedResults.length} properties from embedded JSON`);
    return embeddedResults;
  }
  
  // Method 2: Scrape from DOM cards (only visible ones)
  // Try multiple selectors that Zillow uses
  const selectors = [
    '[data-test="property-card"]',
    'article[data-test="property-card-listing"]',
    '[class*="property-card"]',
    '[class*="PropertyCard"]',
    'article[role="listitem"]',
    '.list-card',
    '[data-test="search-result-list"] > li',
    '#grid-search-results > li'
  ];
  
  let cards = [];
  for (const selector of selectors) {
    cards = document.querySelectorAll(selector);
    if (cards.length > 0) {
      console.log(`Found ${cards.length} cards with selector: ${selector}`);
      break;
    }
  }
  
  cards.forEach((card, index) => {
    try {
      const property = scrapePropertyCard(card);
      if (property && property.address) {
        property.resultIndex = index + 1;
        results.push(property);
      }
    } catch (e) {
      console.log('Error scraping card:', e);
    }
  });
  
  console.log(`Scraped ${results.length} properties from search results (DOM)`);
  return results;
}

function extractSearchResultsJSON() {
  // Look for search results in embedded data
  const scripts = document.querySelectorAll('script');
  
  for (const script of scripts) {
    const text = script.textContent || '';
    
    // Look for various Zillow data structures
    if (text.includes('searchResults') || text.includes('listResults') || text.includes('cat1') || text.includes('mapResults')) {
      
      // Try __NEXT_DATA__ first (most reliable)
      if (script.id === '__NEXT_DATA__') {
        try {
          const data = JSON.parse(text);
          const results = findSearchResults(data);
          if (results && results.length > 0) {
            console.log('Found results in __NEXT_DATA__');
            return results.map(r => normalizeSearchResult(r));
          }
        } catch (e) {
          console.log('Failed to parse __NEXT_DATA__:', e);
        }
      }
      
      // Try to find listResults array
      try {
        // Match listResults with nested objects
        const listMatch = text.match(/"listResults"\s*:\s*(\[[\s\S]*?\])(?=,")/);
        if (listMatch) {
          try {
            const results = JSON.parse(listMatch[1]);
            if (results.length > 0) {
              console.log('Found results in listResults');
              return results.map(r => normalizeSearchResult(r));
            }
          } catch (e) {}
        }
        
        // Try cat1.searchResults
        const cat1Match = text.match(/"cat1"\s*:\s*\{[^}]*"searchResults"\s*:\s*\{[^}]*"listResults"\s*:\s*(\[[\s\S]*?\])(?=,)/);
        if (cat1Match) {
          try {
            const results = JSON.parse(cat1Match[1]);
            if (results.length > 0) {
              console.log('Found results in cat1.searchResults');
              return results.map(r => normalizeSearchResult(r));
            }
          } catch (e) {}
        }
      } catch (e) {
        console.log('Failed to parse search results JSON:', e);
      }
    }
  }
  
  return null;
}

function findSearchResults(obj, depth = 0) {
  if (depth > 10) return null;
  if (!obj || typeof obj !== 'object') return null;
  
  // Look for listResults array
  if (obj.listResults && Array.isArray(obj.listResults)) {
    return obj.listResults;
  }
  
  // Look for searchResults.listResults
  if (obj.searchResults?.listResults) {
    return obj.searchResults.listResults;
  }
  
  // Look for cat1.searchResults.listResults
  if (obj.cat1?.searchResults?.listResults) {
    return obj.cat1.searchResults.listResults;
  }
  
  // Recurse into children
  for (const key of Object.keys(obj)) {
    if (['props', 'pageProps', 'searchPageState', 'queryState', 'cat1', 'searchResults'].includes(key)) {
      const result = findSearchResults(obj[key], depth + 1);
      if (result) return result;
    }
  }
  
  return null;
}

function normalizeSearchResult(item) {
  const data = initPropertyData();
  
  // Identifiers
  data.zpid = item.zpid?.toString() || item.id?.toString() || null;
  data.mlsId = item.mlsId || item.attributionInfo?.mlsId || null;
  
  // Price and basic info
  data.price = item.price || item.unformattedPrice || item.hdpData?.homeInfo?.price || null;
  data.bedrooms = item.beds || item.bedrooms || item.hdpData?.homeInfo?.bedrooms || null;
  data.bathrooms = item.baths || item.bathrooms || item.hdpData?.homeInfo?.bathrooms || null;
  data.sqft = item.area || item.livingArea || item.hdpData?.homeInfo?.livingArea || null;
  data.lotAcres = item.lotAreaValue || item.hdpData?.homeInfo?.lotAreaValue || null;
  
  // Address - handle multiple formats
  if (item.address) {
    if (typeof item.address === 'string') {
      const parts = item.address.split(',');
      data.address = parts[0]?.trim();
      data.city = parts[1]?.trim();
      if (parts[2]) {
        const stateZip = parts[2].trim().split(/\s+/);
        data.state = stateZip[0];
        data.zipcode = stateZip[1];
      }
    } else {
      data.address = item.address.streetAddress || null;
      data.city = item.address.city || null;
      data.state = item.address.state || null;
      data.zipcode = item.address.zipcode || null;
    }
  } else if (item.streetAddress) {
    data.address = item.streetAddress;
    data.city = item.city;
    data.state = item.state;
    data.zipcode = item.zipcode;
  } else if (item.hdpData?.homeInfo) {
    const info = item.hdpData.homeInfo;
    data.address = info.streetAddress;
    data.city = info.city;
    data.state = info.state;
    data.zipcode = info.zipcode;
  }
  
  // Latitude/Longitude - multiple possible locations in the data
  data.latitude = item.latitude || item.latLong?.latitude || item.hdpData?.homeInfo?.latitude || null;
  data.longitude = item.longitude || item.latLong?.longitude || item.hdpData?.homeInfo?.longitude || null;
  
  // Days on Zillow / DOM
  data.daysOnZillow = item.daysOnZillow || item.timeOnZillow || item.hdpData?.homeInfo?.daysOnZillow || null;
  
  // Agent/Broker info (sometimes available)
  if (item.attributionInfo) {
    data.agentName = item.attributionInfo.agentName || null;
    const phone = item.attributionInfo.agentPhoneNumber;
    if (phone) {
      if (phone.includes('@')) {
        data.agentEmail = phone;
      } else {
        data.agentPhone = phone;
      }
    }
    data.brokerName = item.attributionInfo.brokerName || null;
    data.mlsSource = item.attributionInfo.mlsName || null;
  }
  
  // URL
  if (item.detailUrl) {
    data.url = item.detailUrl.startsWith('http') ? item.detailUrl : `https://www.zillow.com${item.detailUrl}`;
  } else if (data.zpid) {
    data.url = `https://www.zillow.com/homedetails/${data.zpid}_zpid/`;
  }
  
  // Property type and status
  data.homeType = item.homeType || item.propertyType || item.hdpData?.homeInfo?.homeType || null;
  data.homeStatus = item.homeStatus || item.statusType || item.hdpData?.homeInfo?.homeStatus || null;
  
  // Year built (sometimes available)
  data.yearBuilt = item.yearBuilt || item.hdpData?.homeInfo?.yearBuilt || null;
  
  // Zestimate (sometimes in search results)
  data.zestimate = item.zestimate || item.hdpData?.homeInfo?.zestimate || null;
  
  // Photo
  data.primaryPhoto = item.imgSrc || item.miniCardPhotos?.[0]?.url || null;
  data.source = 'Zillow';
  
  return data;
}

function scrapePropertyCard(card) {
  const data = initPropertyData();
  
  // Address
  const addressEl = card.querySelector('address, [data-test="property-card-addr"]');
  if (addressEl) {
    const fullAddr = addressEl.textContent.trim();
    const parts = fullAddr.split(',');
    if (parts.length >= 1) data.address = parts[0].trim();
    if (parts.length >= 2) data.city = parts[1].trim();
    if (parts.length >= 3) {
      const stateZip = parts[2].trim().split(/\s+/);
      data.state = stateZip[0];
      data.zipcode = stateZip[1];
    }
  }
  
  // Price
  const priceEl = card.querySelector('[data-test="property-card-price"]');
  if (priceEl) data.price = parsePrice(priceEl.textContent);
  
  // Beds/Baths/Sqft
  const detailsEl = card.querySelector('[data-test="property-card-details"]');
  if (detailsEl) {
    const text = detailsEl.textContent;
    const bedsMatch = text.match(/(\d+)\s*bd/i);
    const bathsMatch = text.match(/([\d.]+)\s*ba/i);
    const sqftMatch = text.match(/([\d,]+)\s*sqft/i);
    const acreMatch = text.match(/([\d.]+)\s*(?:ac|acre)/i);
    
    if (bedsMatch) data.bedrooms = parseInt(bedsMatch[1]);
    if (bathsMatch) data.bathrooms = parseFloat(bathsMatch[1]);
    if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
    if (acreMatch) data.lotAcres = parseFloat(acreMatch[1]);
  }
  
  // Link (contains zpid)
  const linkEl = card.querySelector('a[href*="_zpid"]');
  if (linkEl) {
    data.url = linkEl.href;
    const zpidMatch = linkEl.href.match(/(\d+)_zpid/);
    if (zpidMatch) data.zpid = zpidMatch[1];
  }
  
  // Try to get additional data from card's data attributes or nearby elements
  const cardText = card.textContent;
  
  // Days on Zillow
  const domMatch = cardText.match(/(\d+)\s*days?\s*on\s*zillow/i);
  if (domMatch) data.daysOnZillow = parseInt(domMatch[1]);
  
  // Image
  const imgEl = card.querySelector('img');
  if (imgEl) data.primaryPhoto = imgEl.src;
  
  data.source = 'Zillow';
  return data;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
function initPropertyData() {
  return {
    // Identifiers
    zpid: null,
    mlsId: null,
    mlsSource: null,  // Which MLS the listing is from
    parcelId: null,
    
    // Address
    address: null,
    city: null,
    state: null,
    zipcode: null,
    county: null,
    
    // Property Details
    price: null,
    bedrooms: null,
    bathrooms: null,
    sqft: null,
    lotSize: null,
    lotAcres: null,
    yearBuilt: null,
    homeType: null,
    homeStatus: null,
    hoaFee: null,  // Monthly HOA amount
    
    // Location
    latitude: null,
    longitude: null,
    
    // Agent/MLS Info
    agentName: null,
    agentPhone: null,
    agentEmail: null,
    brokerName: null,
    brokerPhone: null,
    
    // Tax Info
    taxAssessedValue: null,
    taxAnnualAmount: null,
    lastTaxPaid: null,
    
    // Sale History
    lastSalePrice: null,
    lastSaleDate: null,
    
    // Zillow Metrics
    daysOnZillow: null,
    pageViewCount: null,
    favoriteCount: null,
    zestimate: null,
    rentZestimate: null,
    
    // Meta
    source: null,
    url: null,
    primaryPhoto: null,
    photoCount: null,
    scrapedAt: null,
    
    // History (arrays)
    priceHistory: null,
    taxHistory: null
  };
}

function parsePrice(priceText) {
  if (!priceText) return null;
  const cleaned = priceText.replace(/[$,\s]/g, '');
  const price = parseInt(cleaned);
  return isNaN(price) ? null : price;
}

function deepFind(obj, targetKey) {
  // Recursively find an object containing the target key
  if (!obj || typeof obj !== 'object') return null;
  
  if (obj[targetKey] !== undefined) return obj;
  
  for (const key of Object.keys(obj)) {
    const result = deepFind(obj[key], targetKey);
    if (result) return result;
  }
  
  return null;
}

function mergePropertyData(target, source) {
  // Merge source into target, only overwriting null values
  if (!source) return target;
  
  for (const key of Object.keys(target)) {
    if (target[key] === null && source[key] !== null && source[key] !== undefined) {
      target[key] = source[key];
    }
  }
  
  return target;
}
