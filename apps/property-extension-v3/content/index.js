/**
 * DREAMS Property Scraper v3.2.0 - Content Script
 * Multi-source support: Zillow, Redfin, Realtor.com
 * Designed for bulk operations and data export
 */

const VERSION = '3.9.27';
console.log(`DREAMS Property Scraper v${VERSION}: Content script loaded`);

// Detect which site we're on
const SITE = window.location.hostname.includes('zillow') ? 'zillow'
           : window.location.hostname.includes('redfin') ? 'redfin'
           : window.location.hostname.includes('realtor') ? 'realtor'
           : 'unknown';

console.log(`DREAMS: Detected site: ${SITE}`);

// Diagnostic: dump data structure on load (only for Zillow - Redfin has its own)
if (SITE === 'zillow') {
  setTimeout(() => {
    const script = document.getElementById('__NEXT_DATA__');
    if (!script) {
      console.log('DEBUG: No __NEXT_DATA__ found');
      return;
    }

    try {
      const data = JSON.parse(script.textContent);
      console.log('DEBUG __NEXT_DATA__ structure:');
      console.log('  - buildId:', data.buildId);
      console.log('  - page:', data.page);

      if (data.props?.pageProps) {
        const pp = data.props.pageProps;
        console.log('  - pageProps keys:', Object.keys(pp));

        // Check gdpClientCache
        if (pp.gdpClientCache) {
          const cacheType = typeof pp.gdpClientCache;
          console.log('  - gdpClientCache type:', cacheType);

          let cache = pp.gdpClientCache;
          if (cacheType === 'string') {
            try {
              cache = JSON.parse(cache);
              console.log('  - gdpClientCache (parsed) keys:', Object.keys(cache).slice(0, 10));
            } catch (e) {
              console.log('  - gdpClientCache parse failed');
            }
          } else {
            console.log('  - gdpClientCache keys:', Object.keys(cache).slice(0, 10));
          }

          // Look for property data
          for (const key of Object.keys(cache)) {
            let val = cache[key];
            if (typeof val === 'string' && val.startsWith('{')) {
              try { val = JSON.parse(val); } catch (e) { continue; }
            }
            if (val?.property) {
              console.log(`  - Found property in "${key.substring(0, 50)}...":`);
              console.log('    zpid:', val.property.zpid);
              console.log('    bedrooms:', val.property.bedrooms);
              console.log('    bathrooms:', val.property.bathrooms);
              console.log('    address:', val.property.address);
            }
          }
        }

        if (pp.initialData) console.log('  - initialData keys:', Object.keys(pp.initialData));
        if (pp.property) console.log('  - property found directly');
        if (pp.componentProps) console.log('  - componentProps keys:', Object.keys(pp.componentProps));
      }
    } catch (e) {
      console.log('DEBUG: Failed to parse __NEXT_DATA__:', e.message);
    }
  }, 1000);
}

// ============================================
// PAGE TYPE DETECTION
// ============================================
function detectPageType() {
  const url = window.location.href;
  const path = window.location.pathname;

  if (SITE === 'zillow') {
    if (url.includes('/homedetails/') || url.includes('_zpid')) {
      return 'property';
    }
    if (url.includes('/homes/') || url.includes('/for_sale/') || url.includes('searchQueryState')) {
      return 'search';
    }
  }

  if (SITE === 'redfin') {
    // Use the Redfin scraper's detection if available
    if (window.RedfinScraper?.detectPageType) {
      return window.RedfinScraper.detectPageType();
    }
    // Fallback detection
    if (path.includes('/home/') || url.includes('property_id=')) {
      return 'property';
    }
    if (path.includes('/city/') || path.includes('/zipcode/') ||
        path.includes('/neighborhood/') || path.includes('/filter/') ||
        path.includes('/county/') || url.includes('market=') ||
        url.includes('min-price=') || url.includes('max-price=')) {
      return 'search';
    }
  }

  if (SITE === 'realtor') {
    if (url.includes('/realestateandhomes-detail/')) {
      return 'property';
    }
    if (url.includes('/realestateandhomes-search/')) {
      return 'search';
    }
  }

  return 'unknown';
}

// ============================================
// INITIALIZE EMPTY PROPERTY DATA
// ============================================
function initPropertyData() {
  return {
    zpid: null,
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
    mls_number: null,
    mls_source: null,
    parcel_id: null,
    listing_agent_name: null,
    listing_agent_phone: null,
    listing_agent_email: null,
    listing_brokerage: null,
    hoa_fee: null,
    tax_assessed_value: null,
    tax_annual_amount: null,
    zestimate: null,
    rent_zestimate: null,
    days_on_market: null,
    page_views: null,
    favorites_count: null,
    heating: null,
    cooling: null,
    garage: null,
    sewer: null,
    roof: null,
    stories: null,
    subdivision: null,
    latitude: null,
    longitude: null,
    photo_urls: [],
    source: 'zillow',
    url: null,
    scraped_at: null,
    confidence: 0
  };
}

// ============================================
// MERGE PROPERTY DATA (non-null values only)
// ============================================
function mergePropertyData(target, source) {
  if (!source) return target;

  for (const key of Object.keys(source)) {
    if (source[key] !== null && source[key] !== undefined && source[key] !== '') {
      target[key] = source[key];
    }
  }
  return target;
}

// ============================================
// SCRAPE CURRENT PROPERTY (Multi-source)
// ============================================
function scrapeCurrentProperty() {
  console.log(`Scraping property from ${SITE}...`);

  // Use site-specific scrapers
  if (SITE === 'redfin' && window.RedfinScraper?.scrapeProperty) {
    console.log('Using Redfin scraper');
    return window.RedfinScraper.scrapeProperty();
  }

  if (SITE === 'realtor' && window.RealtorScraper?.scrapeProperty) {
    console.log('Using Realtor.com scraper');
    return window.RealtorScraper.scrapeProperty();
  }

  // Zillow scraping (or fallback for other sites)
  let data = initPropertyData();

  // Get ZPID from URL (Zillow)
  const zpidMatch = window.location.href.match(/(\d+)_zpid/);
  const targetZpid = zpidMatch ? zpidMatch[1] : null;
  console.log('Target ZPID:', targetZpid);

  // Method 1: Extract from embedded JSON
  const embeddedData = extractEmbeddedJSON(targetZpid);
  if (embeddedData) {
    data = mergePropertyData(data, embeddedData);
    console.log('Extracted from JSON:', data);
  }

  // Method 2: DOM scraping as backup
  const domData = scrapeDOMData();
  data = mergePropertyData(data, domData);

  // Set metadata
  data.zpid = data.zpid || targetZpid;
  data.source = SITE;
  data.url = window.location.href;
  data.scraped_at = new Date().toISOString();
  data.confidence = calculateConfidence(data);

  console.log('Final data:', data);
  return data;
}

// ============================================
// EXTRACT FROM EMBEDDED JSON
// ============================================
function extractEmbeddedJSON(targetZpid) {
  // Method 1: __NEXT_DATA__
  const nextDataScript = document.getElementById('__NEXT_DATA__');
  if (nextDataScript) {
    try {
      const nextData = JSON.parse(nextDataScript.textContent);
      console.log('__NEXT_DATA__ top keys:', Object.keys(nextData));
      if (nextData.props?.pageProps) {
        console.log('pageProps keys:', Object.keys(nextData.props.pageProps));
      }
      const result = extractFromNextData(nextData, targetZpid);
      if (result && result.beds !== null) return result;
    } catch (e) {
      console.log('Failed to parse __NEXT_DATA__:', e);
    }
  }

  // Method 2: Look for Apollo cache in inline scripts
  const scripts = document.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';

    if (text.includes('gdpClientCache') || text.includes('__APOLLO_STATE__')) {
      try {
        const match = text.match(/gdpClientCache\s*=\s*(\{.+?\});/s) ||
                      text.match(/__APOLLO_STATE__\s*=\s*(\{.+?\});/s);
        if (match) {
          const cache = JSON.parse(match[1]);
          const result = extractFromApolloCache(cache, targetZpid);
          if (result && result.beds !== null) return result;
        }
      } catch (e) {
        continue;
      }
    }
  }

  return null;
}

// ============================================
// EXTRACT FROM NEXT.JS DATA
// ============================================
function extractFromNextData(nextData, targetZpid) {
  try {
    const props = nextData.props?.pageProps;
    if (!props) {
      console.log('No pageProps found');
      return null;
    }

    // gdpClientCache might be a JSON string - parse it first
    let gdpCache = props.gdpClientCache;
    if (typeof gdpCache === 'string') {
      try {
        gdpCache = JSON.parse(gdpCache);
        console.log('Parsed gdpClientCache from string');
      } catch (e) {
        console.log('Failed to parse gdpClientCache string');
      }
    }

    // Check gdpClientCache - this has the full data
    if (gdpCache && typeof gdpCache === 'object') {
      console.log('gdpClientCache keys:', Object.keys(gdpCache).slice(0, 5));

      for (const key of Object.keys(gdpCache)) {
        if (key.includes('FullRenderQuery') || key.includes('ForSaleDoubleScroll')) {
          console.log('Checking cache key:', key);
          let queryData = gdpCache[key];

          // The value might also be a JSON string
          if (typeof queryData === 'string') {
            try {
              queryData = JSON.parse(queryData);
            } catch (e) {
              continue;
            }
          }

          if (queryData?.property) {
            const prop = queryData.property;
            console.log('Found property in cache, zpid:', prop.zpid, 'bedrooms:', prop.bedrooms);
            if (!targetZpid || String(prop.zpid) === targetZpid) {
              console.log('Found in gdpClientCache FullRenderQuery');
              return normalizePropertyData(prop);
            }
          }
        }
      }
    }

    // Check componentProps.gdpClientCache
    let compCache = props.componentProps?.gdpClientCache;
    if (typeof compCache === 'string') {
      try {
        compCache = JSON.parse(compCache);
      } catch (e) {}
    }

    if (compCache && typeof compCache === 'object') {
      for (const key of Object.keys(compCache)) {
        if (key.includes('FullRenderQuery')) {
          let queryData = compCache[key];
          if (typeof queryData === 'string') {
            try { queryData = JSON.parse(queryData); } catch (e) { continue; }
          }
          if (queryData?.property) {
            const prop = queryData.property;
            if (!targetZpid || String(prop.zpid) === targetZpid) {
              console.log('Found in componentProps.gdpClientCache');
              return normalizePropertyData(prop);
            }
          }
        }
      }
    }

    // Check initialData.property
    if (props?.initialData?.property) {
      const prop = props.initialData.property;
      if (!targetZpid || String(prop.zpid) === targetZpid) {
        console.log('Found in initialData.property');
        return normalizePropertyData(prop);
      }
    }

    // Check direct property
    if (props?.property) {
      const prop = props.property;
      if (!targetZpid || String(prop.zpid) === targetZpid) {
        console.log('Found in props.property');
        return normalizePropertyData(prop);
      }
    }

    // Check initialReduxState.gdp
    if (nextData.props?.initialReduxState?.gdp?.building) {
      const building = nextData.props.initialReduxState.gdp.building;
      if (building[targetZpid]) {
        console.log('Found in initialReduxState.gdp.building');
        return normalizePropertyData(building[targetZpid]);
      }
    }

    // Deep search as last resort - but with better validation
    console.log('Attempting deep search for zpid:', targetZpid);
    const found = deepFindProperty(nextData, targetZpid);
    if (found) {
      console.log('Found via deep search, has data:', {
        zpid: found.zpid,
        bedrooms: found.bedrooms,
        price: found.price,
        address: found.address || found.streetAddress
      });
      return normalizePropertyData(found);
    }

  } catch (e) {
    console.log('Error in extractFromNextData:', e);
  }
  return null;
}

// ============================================
// EXTRACT FROM APOLLO CACHE
// ============================================
function extractFromApolloCache(cache, targetZpid) {
  // If cache is a string, parse it
  if (typeof cache === 'string') {
    try {
      cache = JSON.parse(cache);
    } catch (e) {
      return null;
    }
  }

  console.log('Searching Apollo cache, keys:', Object.keys(cache).slice(0, 5));

  // Try exact key
  if (targetZpid) {
    const exactKey = `Property:${targetZpid}`;
    if (cache[exactKey]) {
      let propData = cache[exactKey];
      if (typeof propData === 'string') {
        try { propData = JSON.parse(propData); } catch (e) {}
      }
      if (propData.bedrooms !== undefined) {
        console.log('Found exact Property key in Apollo cache');
        return normalizePropertyData(propData);
      }
    }
  }

  // Search FullRenderQuery and other query types
  for (const key of Object.keys(cache)) {
    if (key.includes('FullRenderQuery') || key.includes('ForSaleDoubleScroll')) {
      let data = cache[key];
      if (typeof data === 'string') {
        try { data = JSON.parse(data); } catch (e) { continue; }
      }
      if (data?.property) {
        const prop = data.property;
        if (prop.bedrooms !== undefined && (!targetZpid || String(prop.zpid) === targetZpid)) {
          console.log('Found in Apollo cache FullRenderQuery');
          return normalizePropertyData(prop);
        }
      }
    }
  }

  // Search Property keys
  for (const key of Object.keys(cache)) {
    if (key.startsWith('Property:')) {
      let data = cache[key];
      if (typeof data === 'string') {
        try { data = JSON.parse(data); } catch (e) { continue; }
      }
      if (data?.zpid && data.bedrooms !== undefined && (!targetZpid || String(data.zpid) === targetZpid)) {
        console.log('Found Property key in Apollo cache');
        return normalizePropertyData(data);
      }
    }
  }

  return null;
}

// ============================================
// DEEP FIND PROPERTY BY ZPID
// ============================================
function deepFindProperty(obj, targetZpid, depth = 0, path = '') {
  if (depth > 15 || !obj || typeof obj !== 'object') return null;

  // Skip arrays/objects that contain other properties (comps, nearby, etc.)
  const skipKeys = ['comps', 'comparables', 'nearbyHomes', 'similarHomes',
                    'rentals', 'nearbyCities', 'nearbyZipcodes', 'nearbyNeighborhoods',
                    'onsiteMessage', 'adTargetingParams', 'tourDetails', 'buildingPermits'];

  // If this is a string that looks like JSON, try to parse it
  if (typeof obj === 'string' && obj.startsWith('{')) {
    try {
      obj = JSON.parse(obj);
    } catch (e) {
      return null;
    }
  }

  // If this object has zpid, check if it matches AND has real data
  if (obj.zpid !== undefined) {
    const zpidStr = String(obj.zpid);
    if (zpidStr === targetZpid) {
      // Require MULTIPLE property indicators to confirm this is real data
      const hasPrice = obj.price !== undefined || obj.listPrice !== undefined;
      const hasBeds = obj.bedrooms !== undefined;
      const hasBaths = obj.bathrooms !== undefined;
      const hasAddress = obj.address !== undefined || obj.streetAddress !== undefined;
      const hasAttr = obj.attributionInfo !== undefined;

      const score = (hasPrice ? 1 : 0) + (hasBeds ? 1 : 0) + (hasBaths ? 1 : 0) +
                   (hasAddress ? 1 : 0) + (hasAttr ? 1 : 0);

      // Need at least 3 indicators to confirm this is the full property
      if (score >= 3) {
        console.log(`Found full property at path: ${path}, score: ${score}`);
        return obj;
      } else {
        console.log(`Found zpid match at ${path} but only score ${score}, skipping`);
      }
    }
    // Has zpid but wrong one or incomplete - don't search children
    return null;
  }

  // Check for 'property' key specifically - Zillow often nests full data here
  if (obj.property && typeof obj.property === 'object' && obj.property.zpid) {
    const prop = obj.property;
    if (String(prop.zpid) === targetZpid) {
      const hasPrice = prop.price !== undefined || prop.listPrice !== undefined;
      const hasBeds = prop.bedrooms !== undefined;
      const hasBaths = prop.bathrooms !== undefined;

      if (hasPrice && hasBeds && hasBaths) {
        console.log(`Found property object at path: ${path}.property`);
        return prop;
      }
    }
  }

  // Recurse into object keys
  const keys = Array.isArray(obj) ? obj.keys() : Object.keys(obj);
  for (const key of keys) {
    if (skipKeys.includes(key)) continue;
    const childPath = path ? `${path}.${key}` : key;
    const result = deepFindProperty(obj[key], targetZpid, depth + 1, childPath);
    if (result) return result;
  }

  return null;
}

// ============================================
// NORMALIZE PROPERTY DATA
// ============================================
function normalizePropertyData(raw) {
  const data = initPropertyData();

  if (!raw) return data;

  // Debug - show what we're working with
  console.log('Normalizing property with keys:', Object.keys(raw).slice(0, 30));
  console.log('Raw bedrooms:', raw.bedrooms, 'bathrooms:', raw.bathrooms, 'price:', raw.price);

  // Basic info - check multiple possible field names
  data.zpid = raw.zpid?.toString() || null;
  data.price = raw.price ?? raw.listPrice ?? raw.unformattedPrice ?? null;

  // Beds/Baths - Zillow uses different field names in different places
  data.beds = raw.bedrooms ?? raw.beds ?? raw.bd ?? null;
  data.baths = raw.bathrooms ?? raw.baths ?? raw.ba ??
               (raw.bathroomsFull !== undefined ? raw.bathroomsFull + (raw.bathroomsHalf || 0) * 0.5 : null);

  data.sqft = raw.livingArea ?? raw.livingAreaValue ?? raw.area ?? null;
  data.lot_acres = parseLotAcres(raw);
  data.year_built = raw.yearBuilt ?? raw.year ?? null;
  data.property_type = raw.homeType ?? raw.propertyType ?? null;
  data.status = raw.homeStatus ?? raw.listingStatus ?? null;
  data.hoa_fee = raw.monthlyHoaFee ?? raw.hoaFee ?? null;

  // Address - handle nested object or flattened structure
  if (raw.address && typeof raw.address === 'object') {
    data.address = raw.address.streetAddress ?? raw.address.street ?? null;
    data.city = raw.address.city ?? null;
    data.state = raw.address.state ?? raw.address.stateId ?? null;
    data.zip = raw.address.zipcode ?? raw.address.zip ?? null;
  } else {
    data.address = raw.streetAddress ?? raw.fullAddress ?? raw.formattedAddress ?? null;
    data.city = raw.city ?? null;
    data.state = raw.state ?? raw.stateId ?? null;
    data.zip = raw.zipcode ?? raw.zip ?? null;
  }

  // County
  if (raw.county && typeof raw.county === 'string' && raw.county.length >= 3) {
    const invalidCounties = ['the', 'this', 'that', 'and', 'for', 'not', 'a', 'an'];
    if (!invalidCounties.includes(raw.county.toLowerCase())) {
      data.county = raw.county;
    }
  }

  // Location
  data.latitude = raw.latitude ?? raw.lat ?? null;
  data.longitude = raw.longitude ?? raw.lng ?? raw.lon ?? null;

  // Attribution info (MLS, Agent) - check multiple locations
  const attr = raw.attributionInfo ?? raw.attribution ?? {};
  if (Object.keys(attr).length > 0) {
    console.log('Attribution info keys:', Object.keys(attr));
    data.mls_number = attr.mlsId ?? attr.mlsNumber ?? attr.mls ?? null;
    data.mls_source = attr.mlsName ?? attr.mlsSource ?? null;
    data.listing_agent_name = attr.agentName ?? attr.listingAgent ?? null;
    data.listing_brokerage = attr.brokerName ?? attr.brokerage ?? attr.broker ?? null;

    // Agent phone
    const phoneValue = attr.agentPhoneNumber ?? attr.agentPhone ?? '';
    if (phoneValue) {
      if (phoneValue.includes('@')) {
        data.listing_agent_email = phoneValue;
      } else if (/\d{7,}/.test(phoneValue.replace(/\D/g, ''))) {
        data.listing_agent_phone = phoneValue;
      }
    }

    // Check dedicated email field
    if (attr.agentEmail) {
      data.listing_agent_email = attr.agentEmail;
    }
  }

  // Also check top-level agent fields
  if (!data.listing_agent_name && raw.listingAgent) {
    data.listing_agent_name = raw.listingAgent;
  }
  if (!data.mls_number && raw.mlsId) {
    data.mls_number = raw.mlsId;
  }
  if (!data.mls_number && raw.mlsNumber) {
    data.mls_number = raw.mlsNumber;
  }

  // Tax info
  data.parcel_id = raw.parcelId ?? raw.parcelNumber ?? null;
  data.tax_assessed_value = raw.taxAssessedValue ?? null;
  data.tax_annual_amount = raw.taxAnnualAmount ?? null;

  // Metrics
  data.days_on_market = raw.daysOnZillow ?? raw.timeOnZillow ?? raw.dom ?? null;
  data.page_views = raw.pageViewCount ?? raw.views ?? null;
  data.favorites_count = raw.favoriteCount ?? raw.favorites ?? null;
  data.rent_zestimate = raw.rentZestimate ?? null;
  data.zestimate = raw.zestimate ?? null;

  // resoFacts extras (property details)
  if (raw.resoFacts) {
    const rf = raw.resoFacts;
    data.heating = arrayToString(rf.heating);
    data.cooling = arrayToString(rf.cooling);
    data.sewer = arrayToString(rf.sewer);
    data.roof = arrayToString(rf.roofType ?? rf.roof);
    data.stories = rf.stories ?? null;
    data.subdivision = rf.subdivisionName ?? null;
    data.garage = rf.garageParkingCapacity ? `${rf.garageParkingCapacity} Car` : null;

    if (!data.parcel_id) {
      data.parcel_id = rf.parcelNumber ?? null;
    }

    // Get beds/baths from resoFacts if not found
    if (data.beds === null && rf.bedrooms !== undefined) {
      data.beds = rf.bedrooms;
    }
    if (data.baths === null && rf.bathrooms !== undefined) {
      data.baths = rf.bathrooms;
    }
  }

  // Photos
  if (raw.photos && Array.isArray(raw.photos)) {
    data.photo_urls = raw.photos.slice(0, 10).map(p => {
      return p.mixedSources?.jpeg?.[0]?.url ?? p.url ?? '';
    }).filter(Boolean);
  }

  console.log('Normalized result - beds:', data.beds, 'baths:', data.baths,
              'mls:', data.mls_number, 'agent:', data.listing_agent_name);

  return data;
}

// ============================================
// HELPER FUNCTIONS
// ============================================
function parseLotAcres(raw) {
  if (raw.lotAreaValue && raw.lotAreaUnits === 'acres') {
    return raw.lotAreaValue;
  }
  if (raw.lotAreaValue && raw.lotAreaValue > 0) {
    // If > 100, probably sqft
    if (raw.lotAreaValue > 100) {
      return Math.round((raw.lotAreaValue / 43560) * 100) / 100;
    }
    return raw.lotAreaValue;
  }
  if (raw.lotSize) {
    return Math.round((raw.lotSize / 43560) * 100) / 100;
  }
  return null;
}

function arrayToString(val) {
  if (Array.isArray(val)) return val.join(', ');
  return val || null;
}

function calculateConfidence(data) {
  let score = 0;
  const required = ['address', 'price', 'beds', 'baths'];
  const optional = ['sqft', 'year_built', 'mls_number', 'listing_agent_name', 'lot_acres'];

  for (const f of required) {
    if (data[f]) score += 20;
  }
  for (const f of optional) {
    if (data[f]) score += 4;
  }

  return Math.min(score, 100);
}

// ============================================
// DOM SCRAPING (Backup)
// ============================================
function scrapeDOMData() {
  const data = {};
  const bodyText = document.body.innerText;

  // Views and saves
  const viewsMatch = bodyText.match(/([\d,]+)\s*views?/i);
  if (viewsMatch) data.page_views = parseInt(viewsMatch[1].replace(/,/g, ''));

  const savesMatch = bodyText.match(/([\d,]+)\s*(?:saves?|favorited)/i);
  if (savesMatch) data.favorites_count = parseInt(savesMatch[1].replace(/,/g, ''));

  // Zestimate (only if visible on page)
  const zestEl = document.querySelector('[data-testid="zestimate-text"]');
  if (zestEl) {
    const zestMatch = zestEl.textContent.match(/\$([\d,]+)/);
    if (zestMatch) data.zestimate = parseInt(zestMatch[1].replace(/,/g, ''));
  }

  // Price from DOM
  const priceEl = document.querySelector('[data-testid="price"], .summary-container [class*="Price"], span[data-testid="on-market-price-message"]');
  if (priceEl) {
    const priceMatch = priceEl.textContent.match(/\$([\d,]+)/);
    if (priceMatch) data.price = parseInt(priceMatch[1].replace(/,/g, ''));
  }

  // Address from DOM
  const addressEl = document.querySelector('[data-testid="bdp-header-address"], h1[class*="address"]');
  if (addressEl) {
    const fullAddress = addressEl.textContent.trim();
    // Try to parse: "123 Main St, City, ST 12345"
    const parts = fullAddress.split(',');
    if (parts.length >= 1) data.address = parts[0].trim();
    if (parts.length >= 2) data.city = parts[1].trim();
    if (parts.length >= 3) {
      const stateZip = parts[2].trim();
      const match = stateZip.match(/([A-Z]{2})\s*(\d{5})/);
      if (match) {
        data.state = match[1];
        data.zip = match[2];
      }
    }
  }

  // Beds/Baths/Sqft from summary
  const summaryText = document.querySelector('.summary-container, [data-testid="bed-bath-sqft-fact-container"]')?.textContent || '';
  const bedsMatch = summaryText.match(/(\d+)\s*(?:bed|bd)/i);
  const bathsMatch = summaryText.match(/([\d.]+)\s*(?:bath|ba)/i);
  const sqftMatch = summaryText.match(/([\d,]+)\s*(?:sqft|sq\s*ft)/i);

  if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
  if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
  if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));

  // MLS number from page text
  const mlsMatch = bodyText.match(/MLS[#:\s]*([A-Z0-9-]+)/i);
  if (mlsMatch && mlsMatch[1].length >= 5 && mlsMatch[1].length <= 20) {
    data.mls_number = mlsMatch[1];
  }

  // Agent info - look for common patterns
  const agentSection = document.querySelector('[data-testid="listing-agent-info"], .listing-agent, .agent-info');
  if (agentSection) {
    const agentText = agentSection.textContent;
    // Look for phone number pattern
    const phoneMatch = agentText.match(/(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/);
    if (phoneMatch) data.listing_agent_phone = phoneMatch[1];

    // Agent name is usually before phone
    const nameMatch = agentText.match(/(?:Agent|Listed by|Contact)[:\s]*([A-Za-z\s]+?)(?:\d|\(|$)/i);
    if (nameMatch) data.listing_agent_name = nameMatch[1].trim();
  }

  // Days on market
  const domMatch = bodyText.match(/(\d+)\s*day(?:s)?\s*(?:on\s*)?(?:Zillow|market)/i);
  if (domMatch) data.days_on_market = parseInt(domMatch[1]);

  // Year built from facts section
  const yearMatch = bodyText.match(/(?:Year\s*built|Built\s*in)[:\s]*(\d{4})/i);
  if (yearMatch) data.year_built = parseInt(yearMatch[1]);

  console.log('DOM scrape extracted:', Object.keys(data).filter(k => data[k] !== undefined));

  return data;
}

// ============================================
// SEARCH RESULTS SCRAPING (Multi-source, for bulk operations)
// ============================================
function scrapeSearchResults() {
  console.log(`Scraping search results from ${SITE}...`);

  // Use Redfin scraper if available
  if (SITE === 'redfin' && window.RedfinScraper?.scrapeSearchResults) {
    console.log('Using Redfin search scraper');
    return window.RedfinScraper.scrapeSearchResults();
  }

  // Use Realtor.com scraper if available
  if (SITE === 'realtor' && window.RealtorScraper?.scrapeSearchResults) {
    console.log('Using Realtor.com search scraper');
    return window.RealtorScraper.scrapeSearchResults();
  }

  // Zillow search scraping
  const results = [];
  const cards = document.querySelectorAll(
    '[data-test="property-card"], article[data-test], .list-card, .property-card'
  );

  console.log(`Found ${cards.length} property cards`);

  cards.forEach((card, index) => {
    try {
      const link = card.querySelector('a[href*="_zpid"]');
      const zpidMatch = link?.href?.match(/(\d+)_zpid/);
      const zpid = zpidMatch ? zpidMatch[1] : null;

      const addressEl = card.querySelector('[data-test="property-card-addr"], address');
      const priceEl = card.querySelector('[data-test="property-card-price"]');

      // Try to get beds/baths from card
      const statsText = card.textContent || '';
      const bedsMatch = statsText.match(/(\d+)\s*(?:bed|bd)/i);
      const bathsMatch = statsText.match(/([\d.]+)\s*(?:bath|ba)/i);
      const sqftMatch = statsText.match(/([\d,]+)\s*(?:sqft|sq)/i);

      const address = addressEl?.textContent?.trim() || '';
      const priceText = priceEl?.textContent?.replace(/[^0-9]/g, '') || '';

      results.push({
        zpid,
        address,
        price: parseInt(priceText) || null,
        beds: bedsMatch ? parseInt(bedsMatch[1]) : null,
        baths: bathsMatch ? parseFloat(bathsMatch[1]) : null,
        sqft: sqftMatch ? parseInt(sqftMatch[1].replace(/,/g, '')) : null,
        url: link?.href || '',
        source: SITE,
        isSearchResult: true
      });
    } catch (e) {
      console.warn('Failed to parse card:', e);
    }
  });

  console.log(`Extracted ${results.length} search results`);
  return results;
}

// ============================================
// MESSAGE HANDLER
// ============================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Content script received message:', message.type);

  const pageType = detectPageType();

  if (message.type === 'SCRAPE_PROPERTY') {
    if (pageType === 'property') {
      const data = scrapeCurrentProperty();
      sendResponse({ data, pageType: 'property', source: SITE });
    } else {
      sendResponse({ error: 'Not a property page', pageType, source: SITE });
    }
  } else if (message.type === 'SCRAPE_SEARCH') {
    if (pageType === 'search') {
      const data = scrapeSearchResults();
      sendResponse({ data, pageType: 'search', count: data.length, source: SITE });
    } else {
      sendResponse({ error: 'Not a search page', pageType, source: SITE });
    }
  } else if (message.type === 'GET_PAGE_INFO') {
    sendResponse({ site: SITE, pageType, url: window.location.href, source: SITE });
  } else {
    sendResponse({ error: 'Unknown message', source: SITE });
  }

  return true;
});

console.log(`DREAMS v${VERSION} loaded on ${SITE} (${detectPageType()} page)`);
