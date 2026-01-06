// content.js - Scrapes property data from current page

console.log('myDREAMS Property Capture: Content script loaded');

// Listen for scrape requests from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrapeProperty') {
    console.log('Scraping property data...');
    const propertyData = scrapeCurrentPage();
    sendResponse(propertyData);
  }
  return true;
});

function scrapeCurrentPage() {
  const url = window.location.href;
  const hostname = window.location.hostname;
  
  let data = {
    url: url,
    source: detectSource(hostname),
    address: null,
    city: null,
    state: null,
    zip: null,
    price: null,
    bedrooms: null,
    bathrooms: null,
    sqft: null,
    acreage: null,
    parcel_id: null,
    mls_number: null,
    listing_agent: null,
    listing_company: null,
    zillow_views: null,
    zillow_saves: null,
    status: 'Active',
    dom: null,
    year_built: null,
    style: null,
    county: null,
    subdivision: null
  };

  if (hostname.includes('zillow.com')) {
    data = scrapeZillowByText(data);
  } else if (hostname.includes('realtor.com')) {
    data = scrapeRealtor(data);
  } else if (hostname.includes('smokymountainhomes4sale.com')) {
    data = scrapeSmokyMountainHomes(data);
  }

  console.log('Scraped data:', data);
  return data;
}

function detectSource(hostname) {
  if (hostname.includes('zillow')) return 'Zillow';
  if (hostname.includes('realtor')) return 'Realtor.com';
  if (hostname.includes('trulia')) return 'Trulia';
  if (hostname.includes('homes.com')) return 'Homes.com';
  if (hostname.includes('smokymountainhomes4sale')) return 'Jon Tharp Team IDX';
  return 'Unknown';
}

function scrapeSmokyMountainHomes(data) {
  // Get cleaner text from main content area
  const detailsSection = document.querySelector('main') || document.body;
  const bodyText = detailsSection.textContent;
  
  console.log('Scraping IDX site...');
  
  // Address from page - look for the property address pattern
  const addressMatch = bodyText.match(/(\d+[^,\n]+?),\s*([^,\n]+?),\s*([A-Z]{2})\s*(\d{5})/);
  if (addressMatch) {
    data.address = addressMatch[1].trim();
    data.city = addressMatch[2].trim();
    data.state = addressMatch[3];
    data.zip = addressMatch[4];
  }
  
  // Price - Look for $XXX,XXX pattern
  const priceMatch = bodyText.match(/\$\s*([\d,]+)/);
  if (priceMatch) {
    data.price = parseInt(priceMatch[1].replace(/,/g, ''));
  }
  
  // MLS# - Pattern: "MLS#: 4332701" or just the number near property details
  const mlsMatch = bodyText.match(/MLS\s*#?\s*:?\s*(\d{6,})/i) ||
                   bodyText.match(/\b(\d{7})\b/); // 7-digit number (common MLS format)
  if (mlsMatch) {
    data.mls_number = mlsMatch[1];
  }
  
  // Bedrooms - Look for number followed by "BD" or "bed"
  const bedsMatch = bodyText.match(/\b(\d+)\s*BD\b/i) ||
                    bodyText.match(/(\d+)\s*bed/i);
  if (bedsMatch) {
    data.bedrooms = parseInt(bedsMatch[1]);
  }
  
  // Bathrooms - Look for number (with optional decimal) followed by "BA" or "bath"
  const bathsMatch = bodyText.match(/\b(\d+(?:\.\d+)?)\s*BA\b/i) ||
                     bodyText.match(/(\d+(?:\.\d+)?)\s*bath/i);
  if (bathsMatch) {
    data.bathrooms = parseFloat(bathsMatch[1]);
  }
  
  // Square Feet - Look for number with comma followed by "SqFt" or "sqft"
  const sqftMatch = bodyText.match(/([\d,]+)\s*SqFt/i) ||
                    bodyText.match(/([\d,]+)\s*sqft/i);
  if (sqftMatch) {
    data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
  }
  
  // Try structured fields if abbreviated ones didn't work
  if (!data.price) {
    const priceMatch2 = bodyText.match(/List\s*Price:\s*\$?([\d,]+)/i);
    if (priceMatch2) data.price = parseInt(priceMatch2[1].replace(/,/g, ''));
  }
  
  if (!data.bedrooms) {
    const bedsMatch2 = bodyText.match(/Bedrooms?:\s*(\d+)/i);
    if (bedsMatch2) data.bedrooms = parseInt(bedsMatch2[1]);
  }
  
  if (!data.bathrooms) {
    const bathsMatch2 = bodyText.match(/(?:Full\s*)?Bathrooms?:\s*(\d+)/i);
    if (bathsMatch2) data.bathrooms = parseInt(bathsMatch2[1]);
  }
  
  if (!data.sqft) {
    const sqftMatch2 = bodyText.match(/Living\s*Area:\s*([\d,]+)/i);
    if (sqftMatch2) data.sqft = parseInt(sqftMatch2[1].replace(/,/g, ''));
  }
  
  // ==========================================
  // DOM-BASED EXTRACTION SETUP
  // ==========================================
  // Extract all <dt> elements for structured field matching
  const dtElements = Array.from(document.querySelectorAll('dt'));
  
  // ==========================================
  // ACREAGE - DOM-BASED EXTRACTION (ROBUST)
  // ==========================================
  // Priority 1: Find "Parcel Size:" in <dt> tags (structured data)
  const parcelSizeDt = dtElements.find(dt => /Parcel\s*Size/i.test(dt.textContent));
  
  if (parcelSizeDt) {
    // Get the corresponding <dd> value
    const ddElement = parcelSizeDt.nextElementSibling;
    if (ddElement && ddElement.tagName === 'DD') {
      const acreageText = ddElement.textContent.trim();
      const acreageValue = parseFloat(acreageText);
      if (!isNaN(acreageValue) && acreageValue > 0) {
        data.acreage = acreageValue;
        console.log('Acreage from Parcel Size DOM element:', data.acreage);
      }
    }
  }
  
  // Priority 2: Fallback to text-based matching with flexible whitespace
  if (!data.acreage) {
    // Allow for newlines and multiple spaces between "Parcel Size:" and the number
    const parcelSizeMatch = bodyText.match(/Parcel\s*Size:[\s\n]*([\d.]+)/i);
    if (parcelSizeMatch) {
      data.acreage = parseFloat(parcelSizeMatch[1]);
      console.log('Acreage from Parcel Size text pattern:', data.acreage);
    }
  }
  
  // Priority 3: Fallback to description text with "acres"
  if (!data.acreage) {
    const acreageDescMatch = bodyText.match(/([\d.]+)\s*[Aa]cres?/i);
    if (acreageDescMatch) {
      data.acreage = parseFloat(acreageDescMatch[1]);
      console.log('Acreage from description:', data.acreage);
    }
  }
  
  // ==========================================
  // PARCEL ID - DOM + TEXT PATTERN DETECTION
  // ==========================================
  // Priority 1: Find in <dt>/<dd> structure (like we do for acreage)
  const parcelIdDt = dtElements.find(dt => 
    /Parcel\s*(?:ID|Number|#)/i.test(dt.textContent) ||
    /Tax\s*(?:ID|Parcel)/i.test(dt.textContent) ||
    /APN/i.test(dt.textContent)
  );
  
  if (parcelIdDt) {
    const ddElement = parcelIdDt.nextElementSibling;
    if (ddElement && ddElement.tagName === 'DD') {
      const parcelIdText = ddElement.textContent.trim();
      if (parcelIdText && parcelIdText !== '—' && parcelIdText !== '-') {
        data.parcel_id = parcelIdText;
        console.log('Parcel ID from DOM element:', data.parcel_id);
      }
    }
  }
  
  // Priority 2: Text-based patterns (fallback)
  if (!data.parcel_id) {
    let parcelIdMatch = bodyText.match(/Parcel\s*(?:ID|Number|#):[\s\n]*([A-Z0-9\-]+)/i);
    if (!parcelIdMatch) {
      parcelIdMatch = bodyText.match(/Tax\s*(?:ID|Parcel):[\s\n]*([A-Z0-9\-]+)/i);
    }
    if (!parcelIdMatch) {
      parcelIdMatch = bodyText.match(/APN:[\s\n]*([A-Z0-9\-]+)/i);
    }
    if (parcelIdMatch) {
      data.parcel_id = parcelIdMatch[1].trim();
      console.log('Parcel ID from text pattern:', data.parcel_id);
    }
  }
  
  // Year Built
  const yearMatch = bodyText.match(/Year\s*Built:?\s*(\d{4})/i) ||
                    bodyText.match(/\b(19\d{2}|20\d{2})\b/); // 4-digit year
  if (yearMatch) {
    const year = parseInt(yearMatch[1]);
    if (year >= 1800 && year <= 2030) {
      data.year_built = year;
    }
  }
  
  // Days on Market
  const domMatch = bodyText.match(/Days?\s*on\s*Market:?\s*(\d+)/i) ||
                   bodyText.match(/DOM:?\s*(\d+)/i);
  if (domMatch) {
    data.dom = parseInt(domMatch[1]);
  }
  
  // Status - Look for ACTIVE, PENDING, SOLD
  if (bodyText.match(/\bACTIVE\b/i)) {
    data.status = 'Active';
  } else if (bodyText.match(/\bPENDING\b/i)) {
    data.status = 'Pending';
  } else if (bodyText.match(/\bSOLD\b/i)) {
    data.status = 'Sold';
  } else if (bodyText.match(/Status:\s*([A-Za-z]+)/i)) {
    data.status = bodyText.match(/Status:\s*([A-Za-z]+)/i)[1];
  }
  
  // Style
  const styleMatch = bodyText.match(/Style:\s*([A-Za-z\s]+?)(?:\n|Bed|Bath|Year)/i);
  if (styleMatch) {
    data.style = styleMatch[1].trim();
  }
  
  // County
  const countyMatch = bodyText.match(/County:\s*([A-Za-z\s]+?)(?:\n|Exterior|Subdivision)/i);
  if (countyMatch) {
    data.county = countyMatch[1].trim();
  }
  
  // Subdivision
  const subdivisionMatch = bodyText.match(/Subdivision:\s*([A-Za-z\s]+?)(?:\n|Sewer|Exterior)/i);
  if (subdivisionMatch) {
    data.subdivision = subdivisionMatch[1].trim();
  }
  
  console.log('IDX scrape result:', data);
  return data;
}


function scrapeZillowByText(data) {
  const bodyText = document.body.textContent;
  
  // Address
  const h1 = document.querySelector('h1');
  const addressElem = document.querySelector('address');
  
  if (h1 && h1.textContent.match(/\d+.*,.*\d{5}/)) {
    parseAddress(h1.textContent.trim(), data);
  } else if (addressElem) {
    parseAddress(addressElem.textContent.trim(), data);
  }
  
  // Price
  const spans = Array.from(document.querySelectorAll('span'));
  const priceSpan = spans.find(span => {
    const text = span.textContent.trim();
    return /^\$[\d,]+$/.test(text) && text.length > 4;
  });
  if (priceSpan) {
    data.price = parsePrice(priceSpan.textContent);
  }
  
  // Beds/Baths/Sqft - Facts & Features first
  const bedsClean = bodyText.match(/Bedrooms?:\s*(\d+)/i);
  if (bedsClean) {
    data.bedrooms = parseInt(bedsClean[1]);
  }

  const bathsClean = bodyText.match(/Bathrooms?:\s*(\d+)/i);
  if (bathsClean) {
    data.bathrooms = parseInt(bathsClean[1]);
  }

  const sqftClean = bodyText.match(/Total\s*interior\s*livable\s*area:\s*([\d,]+)\s*sqft/i) ||
                    bodyText.match(/\b([\d,]+)\s*sqft/i);
  if (sqftClean) {
    const sqft = parseInt(sqftClean[1].replace(/,/g, ''));
    if (sqft > 500 && sqft < 20000) {
      data.sqft = sqft;
    }
  }

  // Fallback for beds/baths if not found
  if (!data.bedrooms) {
    const allBedsMatches = [...bodyText.matchAll(/(\d+)beds?/gi)];
    if (allBedsMatches.length > 0) {
      for (let i = allBedsMatches.length - 1; i >= 0; i--) {
        const beds = parseInt(allBedsMatches[i][1]);
        if (beds >= 1 && beds <= 9) {
          data.bedrooms = beds;
          break;
        }
      }
    }
  }

  if (!data.bathrooms) {
    const allBathsMatches = bodyText.match(/(\d+(?:\.\d+)?)baths?/gi);
    if (allBathsMatches) {
      for (let i = allBathsMatches.length - 1; i >= 0; i--) {
        const baths = parseFloat(allBathsMatches[i]);
        if (baths >= 1 && baths <= 20) {
          data.bathrooms = baths;
          break;
        }
      }
    }
  }
  
  // Acreage - Hierarchical extraction
  const acreageSizeMatch = bodyText.match(/Size:\s*([\d.]+)\s*Acres?/i);
  if (acreageSizeMatch) {
    data.acreage = parseFloat(acreageSizeMatch[1]);
  } else {
    const acreageMatch = bodyText.match(/([\d.]+)\s*[Aa]cres?/i);
    if (acreageMatch) {
      data.acreage = parseFloat(acreageMatch[1]);
    }
  }
  
  // Parcel ID - Multiple patterns
  let parcelMatch = bodyText.match(/Parcel\s*(?:number|ID):\s*([A-Z0-9\-]+)/i);
  if (!parcelMatch) {
    parcelMatch = bodyText.match(/APN:\s*([A-Z0-9\-]+)/i);
  }
  if (parcelMatch) {
    data.parcel_id = parcelMatch[1];
  }
  
  // MLS #
  const mlsMatch = bodyText.match(/MLS#?:\s*(\d+)/i);
  if (mlsMatch) data.mls_number = mlsMatch[1];
  
  // DOM
  const domMatch = bodyText.match(/(\d+)\s*days?\s*on\s*zillow/i);
  if (domMatch) data.dom = parseInt(domMatch[1]);
  
  // Views
  const viewsMatch = bodyText.match(/([\d,]+)\s*views/i);
  if (viewsMatch) data.zillow_views = parseInt(viewsMatch[1].replace(/,/g, ''));
  
  // Saves
  const savesMatch = bodyText.match(/(\d+)\s*saves/i);
  if (savesMatch) data.zillow_saves = parseInt(savesMatch[1]);
  
  // Listing Agent
  try {
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of scripts) {
      const jsonData = JSON.parse(script.textContent);
      if (jsonData.provider && jsonData.provider.name) {
        data.listing_agent = jsonData.provider.name;
        break;
      }
    }
  } catch (e) {}

  if (!data.listing_agent) {
    const allText = Array.from(document.querySelectorAll('*'))
      .map(el => el.innerText || '')
      .filter(text => text.includes('Listed by'));
    
    for (const text of allText) {
      const agentMatch = text.match(/Listed\s*by:\s*([A-Z][a-z]+\s+[A-Z]\.?\s*[A-Z][a-z]+)/);
      if (agentMatch) {
        data.listing_agent = agentMatch[1].trim();
        break;
      }
    }
  }
  
  // Status
  if (bodyText.includes('Pending')) {
    data.status = 'Pending';
  } else if (bodyText.includes('Sold')) {
    data.status = 'Sold';
  } else if (bodyText.includes('Off Market')) {
    data.status = 'Off Market';
  }
  
  return data;
}

function scrapeRealtor(data) {
  // Address
  const addressElem = document.querySelector('[data-testid="property-address"]') ||
                      document.querySelector('h1');
  if (addressElem) {
    parseAddress(addressElem.textContent.trim(), data);
  }
  
  // Price
  const priceElem = document.querySelector('[data-testid="list-price"]');
  if (priceElem) {
    data.price = parsePrice(priceElem.textContent);
  }
  
  // Beds/Baths/Sqft from text
  const bodyText = document.body.textContent;
  const bedsMatch = bodyText.match(/(\d+)\s*bed/i);
  const bathsMatch = bodyText.match(/(\d+(?:\.\d+)?)\s*bath/i);
  const sqftMatch = bodyText.match(/([\d,]+)\s*sqft/i);
  
  if (bedsMatch) data.bedrooms = parseInt(bedsMatch[1]);
  if (bathsMatch) data.bathrooms = parseFloat(bathsMatch[1]);
  if (sqftMatch) data.sqft = parseInt(sqftMatch[1].replace(/,/g, ''));
  
  return data;
}

function parsePrice(priceText) {
  if (!priceText) return null;
  const cleaned = priceText.replace(/[$,\s]/g, '');
  const price = parseInt(cleaned);
  return isNaN(price) ? null : price;
}

function parseAddress(fullAddress, data) {
  const parts = fullAddress.split(',').map(s => s.trim());
  
  if (parts.length >= 1) data.address = parts[0];
  if (parts.length >= 2) data.city = parts[1];
  if (parts.length >= 3) {
    const stateZip = parts[2].split(/\s+/);
    if (stateZip.length >= 1) data.state = stateZip[0];
    if (stateZip.length >= 2) data.zip = stateZip[1];
  }
}
