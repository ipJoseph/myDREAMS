/**
 * DREAMS Property Scraper - Realtor.com Module
 * Version 1.0.0 - Initial implementation
 *
 * Extracts property data from Realtor.com property detail and search pages.
 * Uses __NEXT_DATA__ JSON extraction with DOM fallback.
 */

const REALTOR_VERSION = '1.0.0';
console.log(`DREAMS Realtor Scraper v${REALTOR_VERSION} loaded`);

// ============================================
// PAGE TYPE DETECTION
// ============================================
function detectRealtorPageType() {
  const url = window.location.href;
  const path = window.location.pathname;

  // Property detail page: /realestateandhomes-detail/ADDRESS_NUMBER
  if (path.includes('/realestateandhomes-detail/')) {
    return 'property';
  }

  // Search results: /realestateandhomes-search/LOCATION
  if (path.includes('/realestateandhomes-search/')) {
    return 'search';
  }

  return 'unknown';
}

// ============================================
// INITIALIZE PROPERTY DATA
// ============================================
function initRealtorPropertyData() {
  return {
    realtor_id: null,
    mls_number: null,
    address: null,
    city: null,
    state: null,
    zip: null,
    county: null,
    price: null,
    beds: null,
    baths: null,
    baths_full: null,
    baths_half: null,
    sqft: null,
    lot_sqft: null,
    lot_acres: null,
    year_built: null,
    property_type: null,
    status: null,
    listing_agent_name: null,
    listing_agent_phone: null,
    listing_agent_email: null,
    listing_brokerage: null,
    hoa_fee: null,
    tax_assessed_value: null,
    tax_annual_amount: null,
    days_on_market: null,
    heating: null,
    cooling: null,
    garage: null,
    stories: null,
    subdivision: null,
    latitude: null,
    longitude: null,
    photo_urls: [],
    description: null,
    source: 'realtor.com',
    url: null,
    scraped_at: null,
    confidence: 0
  };
}

// ============================================
// MAIN SCRAPE FUNCTION
// ============================================
function scrapeRealtorProperty() {
  console.log('=== REALTOR SCRAPER v' + REALTOR_VERSION + ' ===');
  console.log('URL:', window.location.href);

  let data = initRealtorPropertyData();

  // Method 1: Extract from __NEXT_DATA__ JSON
  console.log('\n[Method 1] __NEXT_DATA__ extraction...');
  const nextData = extractNextData();
  if (nextData) {
    console.log('  Found __NEXT_DATA__, extracting property...');
    data = mergeRealtorData(data, normalizeRealtorProperty(nextData));
  } else {
    console.log('  No __NEXT_DATA__ found');
  }

  // Method 2: DOM fallback
  console.log('\n[Method 2] DOM scraping...');
  const domData = scrapeRealtorDOM();
  data = mergeRealtorData(data, domData);

  // Set metadata
  data.source = 'realtor.com';
  data.url = window.location.href;
  data.scraped_at = new Date().toISOString();
  data.confidence = calculateRealtorConfidence(data);

  // Log results
  console.log('\n=== FINAL SCRAPED DATA ===');
  const populated = {};
  for (const [key, val] of Object.entries(data)) {
    if (val !== null && val !== undefined && val !== '' &&
        !(Array.isArray(val) && val.length === 0)) {
      populated[key] = val;
    }
  }
  console.log('Populated fields:', Object.keys(populated));
  console.log('Data:', populated);
  console.log('=== END SCRAPE ===\n');

  return data;
}

// ============================================
// EXTRACT FROM __NEXT_DATA__
// ============================================
function extractNextData() {
  const script = document.getElementById('__NEXT_DATA__');
  if (!script) {
    console.log('No __NEXT_DATA__ script found');
    return null;
  }

  try {
    const json = JSON.parse(script.textContent);
    console.log('__NEXT_DATA__ parsed, keys:', Object.keys(json));

    // Realtor.com structure: props.pageProps.property or props.pageProps.initialState
    const pageProps = json?.props?.pageProps;
    if (!pageProps) {
      console.log('No pageProps in __NEXT_DATA__');
      return null;
    }

    console.log('pageProps keys:', Object.keys(pageProps));

    // Check for property directly
    if (pageProps.property) {
      console.log('Found property in pageProps');
      return pageProps.property;
    }

    // Check initialState.propertyDetails
    if (pageProps.initialState?.propertyDetails) {
      console.log('Found property in initialState.propertyDetails');
      return pageProps.initialState.propertyDetails;
    }

    // Check initialReduxState
    if (pageProps.initialReduxState?.propertyDetails?.propertyDetails) {
      console.log('Found property in initialReduxState');
      return pageProps.initialReduxState.propertyDetails.propertyDetails;
    }

    // Check for listing data
    if (pageProps.listing) {
      console.log('Found listing in pageProps');
      return pageProps.listing;
    }

    // Deep search for property object
    const found = deepFindRealtorProperty(pageProps);
    if (found) {
      console.log('Found property via deep search');
      return found;
    }

  } catch (e) {
    console.log('Failed to parse __NEXT_DATA__:', e.message);
  }

  return null;
}

// ============================================
// DEEP FIND PROPERTY
// ============================================
function deepFindRealtorProperty(obj, depth = 0) {
  if (depth > 10 || !obj || typeof obj !== 'object') return null;

  // Check if this looks like a property object
  if (obj.property_id || obj.listing_id) {
    if (obj.location?.address || obj.address) {
      console.log('Found property object with ID and address');
      return obj;
    }
  }

  // Check for nested property
  if (obj.home && typeof obj.home === 'object') {
    if (obj.home.property_id || obj.home.beds !== undefined) {
      return obj.home;
    }
  }

  // Recurse into object
  for (const key of Object.keys(obj)) {
    if (['photos', 'similar', 'nearby', 'schools'].includes(key)) continue;
    const result = deepFindRealtorProperty(obj[key], depth + 1);
    if (result) return result;
  }

  return null;
}

// ============================================
// NORMALIZE REALTOR PROPERTY DATA
// ============================================
function normalizeRealtorProperty(raw) {
  const data = initRealtorPropertyData();
  if (!raw) return data;

  console.log('Normalizing property with keys:', Object.keys(raw).slice(0, 20));

  // Property ID
  data.realtor_id = raw.property_id || raw.listing_id || null;

  // MLS
  data.mls_number = raw.mls_id || raw.mls?.id || null;

  // Price
  data.price = raw.list_price || raw.price || raw.listPrice || null;
  if (typeof data.price === 'object') {
    data.price = data.price.value || data.price.amount || null;
  }

  // Beds/Baths
  data.beds = raw.beds || raw.bedrooms || raw.description?.beds || null;
  data.baths = raw.baths || raw.bathrooms || raw.description?.baths || null;
  data.baths_full = raw.baths_full || raw.description?.baths_full || null;
  data.baths_half = raw.baths_half || raw.description?.baths_half || null;

  // Calculate total baths if we have full/half breakdown
  if (data.baths === null && (data.baths_full || data.baths_half)) {
    data.baths = (data.baths_full || 0) + (data.baths_half || 0) * 0.5;
  }

  // Square footage
  data.sqft = raw.sqft || raw.description?.sqft || raw.building_size?.size || null;
  data.lot_sqft = raw.lot_sqft || raw.description?.lot_sqft || null;

  // Convert lot to acres
  if (data.lot_sqft && data.lot_sqft > 0) {
    data.lot_acres = Math.round((data.lot_sqft / 43560) * 100) / 100;
  }

  // Year built
  data.year_built = raw.year_built || raw.description?.year_built || null;

  // Property type
  data.property_type = raw.type || raw.prop_type || raw.description?.type || null;

  // Status
  data.status = raw.status || raw.prop_status || null;

  // Address - Realtor.com uses nested location object
  const location = raw.location || {};
  const address = location.address || raw.address || {};

  if (typeof address === 'string') {
    data.address = address;
  } else {
    data.address = address.line || address.street_address || address.street || null;
    data.city = address.city || location.city || null;
    data.state = address.state_code || address.state || location.state_code || null;
    data.zip = address.postal_code || address.zip || location.postal_code || null;
    data.county = address.county || location.county || null;
  }

  // Coordinates
  const coords = location.coordinate || raw.coordinate || {};
  data.latitude = coords.lat || raw.latitude || null;
  data.longitude = coords.lon || coords.lng || raw.longitude || null;

  // Agent/Broker info
  const agent = raw.agent || raw.agents?.[0] || raw.advertisers?.[0] || {};
  data.listing_agent_name = agent.name || agent.full_name || null;
  data.listing_agent_phone = agent.phone || agent.office_phone || null;
  data.listing_agent_email = agent.email || null;
  data.listing_brokerage = agent.office?.name || agent.broker?.name || raw.branding?.[0]?.name || null;

  // Days on market
  data.days_on_market = raw.days_on_market || raw.list_date_delta || null;

  // HOA
  const hoa = raw.hoa || {};
  data.hoa_fee = hoa.fee || raw.hoa_fee || null;

  // Tax info
  const tax = raw.tax_history?.[0] || {};
  data.tax_assessed_value = tax.assessment?.total || raw.tax_assessed_value || null;
  data.tax_annual_amount = tax.tax || raw.property_taxes || null;

  // Features from details
  const details = raw.details || [];
  for (const section of details) {
    if (!section.category) continue;
    const cat = section.category.toLowerCase();

    if (cat === 'heating and cooling' || cat === 'utilities') {
      for (const item of section.text || []) {
        if (item.toLowerCase().includes('heating')) {
          data.heating = item;
        }
        if (item.toLowerCase().includes('cooling') || item.toLowerCase().includes('air')) {
          data.cooling = item;
        }
      }
    }

    if (cat === 'garage and parking') {
      data.garage = (section.text || []).join(', ') || null;
    }
  }

  // Stories
  data.stories = raw.stories || raw.description?.stories || null;

  // Subdivision
  data.subdivision = raw.subdivision || raw.description?.sub_type || null;

  // Photos
  if (raw.photos && Array.isArray(raw.photos)) {
    data.photo_urls = raw.photos.slice(0, 10).map(p => {
      if (typeof p === 'string') return p;
      return p.href || p.url || '';
    }).filter(Boolean);
  }

  // Description
  data.description = raw.description?.text || raw.remarks || null;

  console.log('Normalized: beds=', data.beds, 'baths=', data.baths, 'price=', data.price);

  return data;
}

// ============================================
// DOM SCRAPING (Fallback)
// ============================================
function scrapeRealtorDOM() {
  const data = {};
  const bodyText = document.body.innerText;

  // Price - multiple selectors for different layouts
  const priceSelectors = [
    '[data-testid="list-price"]',
    '[data-testid="ldp-list-price"]',
    '.price-details .price',
    '.listing-price',
    '.property-price'
  ];

  for (const sel of priceSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const priceMatch = el.textContent.match(/\$([\d,]+)/);
      if (priceMatch) {
        data.price = parseInt(priceMatch[1].replace(/,/g, ''));
        break;
      }
    }
  }

  // Address
  const addressSelectors = [
    '[data-testid="address"]',
    '[data-testid="ldp-address"]',
    '.property-address h1',
    '.address-main'
  ];

  for (const sel of addressSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const fullAddress = el.textContent.trim();
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
      break;
    }
  }

  // Beds/Baths/Sqft from property summary
  const summarySelectors = [
    '[data-testid="property-summary"]',
    '.property-meta',
    '.key-facts'
  ];

  for (const sel of summarySelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = el.textContent;
      const bedsMatch = text.match(/(\d+)\s*(?:bed|bd)/i);
      const bathsMatch = text.match(/([\d.]+)\s*(?:bath|ba)/i);
      const sqftMatch = text.match(/([\d,]+)\s*(?:sqft|sq\s*ft)/i);

      if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
      if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
      if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
      break;
    }
  }

  // Fallback: search entire page text
  if (!data.beds) {
    const bedsMatch = bodyText.match(/(\d+)\s*(?:Beds?|Bedrooms?|bd)/i);
    if (bedsMatch) data.beds = parseInt(bedsMatch[1]);
  }

  if (!data.baths) {
    const bathsMatch = bodyText.match(/([\d.]+)\s*(?:Baths?|Bathrooms?|ba)/i);
    if (bathsMatch) data.baths = parseFloat(bathsMatch[1]);
  }

  if (!data.sqft) {
    const sqftMatch = bodyText.match(/([\d,]+)\s*(?:sqft|square\s*feet)/i);
    if (sqftMatch) {
      const sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
      if (sqft > 200 && sqft < 50000) data.sqft = sqft;
    }
  }

  // Year built
  const yearMatch = bodyText.match(/(?:Year\s*Built|Built\s*in)[:\s]*(\d{4})/i);
  if (yearMatch) data.year_built = parseInt(yearMatch[1]);

  // MLS number
  const mlsMatch = bodyText.match(/MLS[#:\s]*([A-Z0-9-]+)/i);
  if (mlsMatch && mlsMatch[1].length >= 5) {
    data.mls_number = mlsMatch[1];
  }

  // Days on market
  const domMatch = bodyText.match(/(\d+)\s*days?\s*(?:on\s*)?(?:Realtor|market)/i);
  if (domMatch) data.days_on_market = parseInt(domMatch[1]);

  // Agent info
  const agentSelectors = [
    '[data-testid="listing-agent"]',
    '.listing-agent-info',
    '.agent-card'
  ];

  for (const sel of agentSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = el.textContent;
      const phoneMatch = text.match(/(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})/);
      if (phoneMatch) data.listing_agent_phone = phoneMatch[1];

      // Try to extract agent name
      const nameEl = el.querySelector('.agent-name, [data-testid="agent-name"]');
      if (nameEl) {
        data.listing_agent_name = nameEl.textContent.trim();
      }
      break;
    }
  }

  // Lot size
  const lotMatch = bodyText.match(/Lot\s*Size[:\s]*([\d,.]+)\s*(acres?|sqft|sq\s*ft)/i);
  if (lotMatch) {
    const value = parseFloat(lotMatch[1].replace(/,/g, ''));
    if (lotMatch[2].toLowerCase().includes('acre')) {
      data.lot_acres = value;
    } else {
      data.lot_sqft = value;
      data.lot_acres = Math.round((value / 43560) * 100) / 100;
    }
  }

  console.log('DOM scrape found:', Object.keys(data).filter(k => data[k] !== undefined));

  return data;
}

// ============================================
// SEARCH RESULTS SCRAPING
// ============================================
function scrapeRealtorSearchResults() {
  console.log('Scraping Realtor.com search results...');

  const results = [];

  // Property cards on search pages
  const cardSelectors = [
    '[data-testid="property-card"]',
    '[data-testid="srp-property-card"]',
    '.property-listing',
    '.card-wrap'
  ];

  let cards = [];
  for (const sel of cardSelectors) {
    cards = document.querySelectorAll(sel);
    if (cards.length > 0) break;
  }

  console.log(`Found ${cards.length} property cards`);

  cards.forEach((card, index) => {
    try {
      const link = card.querySelector('a[href*="/realestateandhomes-detail/"]');
      const url = link?.href || '';

      // Extract property ID from URL
      const idMatch = url.match(/M(\d+)/);
      const propertyId = idMatch ? idMatch[1] : null;

      // Address
      const addressEl = card.querySelector('[data-testid="card-address"], .card-address');
      const address = addressEl?.textContent?.trim() || '';

      // Price
      const priceEl = card.querySelector('[data-testid="card-price"], .card-price');
      const priceText = priceEl?.textContent?.replace(/[^0-9]/g, '') || '';
      const price = parseInt(priceText) || null;

      // Stats (beds, baths, sqft)
      const statsText = card.textContent || '';
      const bedsMatch = statsText.match(/(\d+)\s*(?:bed|bd)/i);
      const bathsMatch = statsText.match(/([\d.]+)\s*(?:bath|ba)/i);
      const sqftMatch = statsText.match(/([\d,]+)\s*(?:sqft|sq)/i);

      results.push({
        realtor_id: propertyId,
        address,
        price,
        beds: bedsMatch ? parseInt(bedsMatch[1]) : null,
        baths: bathsMatch ? parseFloat(bathsMatch[1]) : null,
        sqft: sqftMatch ? parseInt(sqftMatch[1].replace(/,/g, '')) : null,
        url,
        source: 'realtor.com',
        isSearchResult: true
      });
    } catch (e) {
      console.warn(`Failed to parse card ${index}:`, e);
    }
  });

  console.log(`Extracted ${results.length} search results`);
  return results;
}

// ============================================
// HELPER FUNCTIONS
// ============================================
function mergeRealtorData(target, source) {
  if (!source) return target;

  for (const key of Object.keys(source)) {
    if (source[key] !== null && source[key] !== undefined && source[key] !== '') {
      // Don't overwrite existing values with weaker ones
      if (target[key] === null || target[key] === undefined || target[key] === '') {
        target[key] = source[key];
      }
    }
  }
  return target;
}

function calculateRealtorConfidence(data) {
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
// EXPORT TO WINDOW (for content script)
// ============================================
window.RealtorScraper = {
  scrapeProperty: scrapeRealtorProperty,
  scrapeSearchResults: scrapeRealtorSearchResults,
  detectPageType: detectRealtorPageType,
  version: REALTOR_VERSION
};

console.log('Realtor scraper exported to window.RealtorScraper');
