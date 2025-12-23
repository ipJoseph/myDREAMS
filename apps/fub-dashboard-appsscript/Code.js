/**
 * John Tharp Team Lead Intelligence Dashboard - v4
 * Single source of truth: Contacts sheet -> getDashboardData()
 * Client renders everything from one payload.
 */

const APP_VERSION = '1.0.0';

const CONFIG = {
  SHEET_NAME: 'Contacts',
  TARGETS: {
    HOT_TOP_N: 12,      // daily call list target
    VALUE_TOP_N: 20     // daily high-value focus target
  },
  FLOORS: {
    HOT_PRIORITY_FLOOR: 10,
    VALUE_FLOOR: 10
  },
  RULES: {
    INTENT_MIN_SIGNALS: 2,
    ACTIVE_DAYS: 7
  }
};

// ---------------------------
// Web app
// ---------------------------
function doGet() {
  return HtmlService.createHtmlOutputFromFile('fub_dashboard_enhanced')
    .setTitle('Jon Tharp Team Lead Intelligence Dashboard')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ---------------------------
// Public API for client
// ---------------------------
function getDashboardData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG.SHEET_NAME);

  if (!sheet) {
    return {
      leads: [],
      actionQueue: [],
      thresholds: null,
      counts: null,
      stats: null,
      metrics: emptyMetrics(),
      meta: {
        error: `Sheet not found: ${CONFIG.SHEET_NAME}`,
        updatedAt: new Date().toISOString()
      }
    };
  }

  const values = sheet.getDataRange().getValues();
  if (!values || values.length < 2) {
    return {
      leads: [],
      actionQueue: [],
      thresholds: null,
      counts: null,
      stats: null,
      metrics: emptyMetrics(),
      meta: {
        error: 'No data in sheet',
        updatedAt: new Date().toISOString()
      }
    };
  }

  const headers = values[0];
  const rows = values.slice(1);
  const cols = getColumnIndices(headers);

  const required = [
    'id','firstName','lastName','stage','primaryEmail','primaryPhone','lastActivity',
    'priority_score','heat_score','value_score','relationship_score',
    'intent_repeat_views','intent_high_favorites','intent_activity_burst','intent_sharing'
  ];

  const missing = required.filter(k => cols[k] === undefined);
  if (missing.length) {
    return {
      leads: [],
      actionQueue: [],
      thresholds: null,
      counts: null,
      stats: null,
      metrics: emptyMetrics(),
      meta: {
        error: 'Missing required columns',
        missing,
        headers,
        updatedAt: new Date().toISOString()
      }
    };
  }

  const leads = rows
    .filter(r => r.some(cell => cell !== '' && cell !== null && cell !== undefined))
    .map(r => normalizeLead(r, cols));

  const metrics = computeMetrics(leads);
  const thresholds = computeAdaptiveThresholds(leads);
  const counts = computeCounts(leads, thresholds);
  const stats = scoreStats(leads);
  const actionQueue = computeActionQueue(leads);

  return {
    leads,
    actionQueue,
    thresholds,
    counts,
    stats,
    metrics,
    meta: {
      sheet: CONFIG.SHEET_NAME,
      rowCount: leads.length,
      updatedAt: new Date().toISOString()
    }
  };
}

// ---------------------------
// Normalization
// ---------------------------
function normalizeLead(row, cols) {
  const email = String(row[cols.primaryEmail] || '').trim();
  const idRaw = String(row[cols.id] || '').trim();
  const id = email || idRaw || Utilities.getUuid();

  const first = String(row[cols.firstName] || '').trim();
  const last = String(row[cols.lastName] || '').trim();
  const name = `${first} ${last}`.trim() || 'Unknown';

  const stage = String(row[cols.stage] || 'N/A').trim();

  const priority = toNumber(row[cols.priority_score]);
  const heat = toNumber(row[cols.heat_score]);
  const value = toNumber(row[cols.value_score]);
  const relationship = toNumber(row[cols.relationship_score]);

  const lastActivityRaw = row[cols.lastActivity];
  const lastActivityIso = toIsoDate(lastActivityRaw);
  const daysSinceActivity = daysSince(lastActivityRaw);

  const intentSignals = [];
  if (row[cols.intent_repeat_views]) intentSignals.push('repeat_views');
  if (row[cols.intent_high_favorites]) intentSignals.push('high_favorites');
  if (row[cols.intent_activity_burst]) intentSignals.push('activity_burst');
  if (row[cols.intent_sharing]) intentSignals.push('sharing');

  return {
    id,
    name,
    firstName: first,
    lastName: last,
    email,
    phone: String(row[cols.primaryPhone] || '').trim(),
    stage,

    priority,
    heat,
    value,
    relationship,

    lastActivity: lastActivityIso,
    daysSinceActivity,

    intentSignals,
    intentCount: intentSignals.length
  };
}

// ---------------------------
// Metrics / Thresholds / Counts / Stats
// ---------------------------
function emptyMetrics() {
  return {
    totalLeads: 0,
    hotLeads: 0,
    highValue: 0,
    active7d: 0,
    avgPriority: 0,
    highIntent: 0
  };
}

function computeMetrics(leads) {
  const total = leads.length;

  const hotLeads = 0; // replaced by adaptive cutoff in counts; keep card values aligned via counts in HTML if desired
  const highValue = 0;

  const active7d = leads.filter(l => (Number(l.daysSinceActivity) || 999) <= CONFIG.RULES.ACTIVE_DAYS).length;
  const highIntent = leads.filter(l => (Number(l.intentCount) || 0) >= CONFIG.RULES.INTENT_MIN_SIGNALS).length;

  const avgPriority =
    total > 0 ? (leads.reduce((sum, l) => sum + (Number(l.priority) || 0), 0) / total) : 0;

  return {
    totalLeads: total,
    hotLeads,
    highValue,
    active7d,
    avgPriority: round1(avgPriority),
    highIntent
  };
}

function computeAdaptiveThresholds(leads) {
  const hot = topNCutoff(leads, 'priority', CONFIG.TARGETS.HOT_TOP_N);
  const val = topNCutoff(leads, 'value', CONFIG.TARGETS.VALUE_TOP_N);

  const hotPriorityCutoff = Math.max(CONFIG.FLOORS.HOT_PRIORITY_FLOOR, hot.cutoff);
  const valueCutoff = Math.max(CONFIG.FLOORS.VALUE_FLOOR, val.cutoff);

  return {
    hotTopN: CONFIG.TARGETS.HOT_TOP_N,
    hotPriorityCutoff: round1(hotPriorityCutoff),

    valueTopN: CONFIG.TARGETS.VALUE_TOP_N,
    valueCutoff: round1(valueCutoff),

    intentMinSignals: CONFIG.RULES.INTENT_MIN_SIGNALS,
    activeDays: CONFIG.RULES.ACTIVE_DAYS
  };
}

function computeCounts(leads, thresholds) {
  const all = leads.length;

  const hot = leads.filter(l => (Number(l.priority) || 0) >= (Number(thresholds.hotPriorityCutoff) || 0)).length;
  const value = leads.filter(l => (Number(l.value) || 0) >= (Number(thresholds.valueCutoff) || 0)).length;
  const intent = leads.filter(l => (Number(l.intentCount) || 0) >= CONFIG.RULES.INTENT_MIN_SIGNALS).length;
  const active7 = leads.filter(l => (Number(l.daysSinceActivity) || 999) <= CONFIG.RULES.ACTIVE_DAYS).length;

  // Keep “p90” as a traditional view: priority >= 90
  const p90 = leads.filter(l => (Number(l.priority) || 0) >= 90).length;

  return { all, hot, p90, value, intent, active7 };
}

function scoreStats(leads) {
  const get = (key) => leads.map(l => Number(l[key]) || 0).sort((a,b) => a-b);

  const pack = (arr) => ({
    min: round1(arr[0] ?? 0),
    p25: round1(percentile(arr, 0.25)),
    p50: round1(percentile(arr, 0.50)),
    p75: round1(percentile(arr, 0.75)),
    p90: round1(percentile(arr, 0.90)),
    max: round1(arr[arr.length - 1] ?? 0)
  });

  return {
    priority: pack(get('priority')),
    heat: pack(get('heat')),
    value: pack(get('value')),
    relationship: pack(get('relationship'))
  };
}

function percentile(sortedNums, p) {
  if (!sortedNums.length) return 0;
  const idx = (sortedNums.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  const w = idx - lo;
  if (hi >= sortedNums.length) return sortedNums[lo];
  return sortedNums[lo] * (1 - w) + sortedNums[hi] * w;
}

function topNCutoff(leads, key, topN) {
  const n = Math.max(0, Math.min(topN || 0, leads.length));
  if (n === 0) return { cutoff: 0 };

  const sorted = leads
    .slice()
    .sort((a,b) => (Number(b[key]) || 0) - (Number(a[key]) || 0));

  const cutoff = Number(sorted[n - 1][key]) || 0;
  return { cutoff };
}

function round1(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  return Math.round(x * 10) / 10;
}

// ---------------------------
// Action Queue (server-side)
// ---------------------------
function computeActionQueue(leads) {
  const queue = [];
  const seen = new Set();

  const add = (lead, tier, reason) => {
    const key = lead.id || lead.email || lead.name;
    if (!key || seen.has(key)) return;
    seen.add(key);

    queue.push({
      id: lead.id,
      name: lead.name,
      email: lead.email,
      phone: lead.phone,
      stage: lead.stage,
      tier,
      reason,
      priority: lead.priority,
      heat: lead.heat,
      value: lead.value,
      relationship: lead.relationship,
      intentCount: lead.intentCount,
      daysSinceActivity: lead.daysSinceActivity
    });
  };

  // Tier 1
  leads
    .filter(l => (l.priority >= 80) && (l.daysSinceActivity <= 7))
    .sort((a,b) => (b.priority - a.priority) || (a.daysSinceActivity - b.daysSinceActivity))
    .forEach(l => add(l, 1, 'Immediate contact'));

  // Tier 2
  leads
    .filter(l => (l.value >= 70) && (l.heat >= 50) && (l.priority < 80))
    .sort((a,b) => (b.value - a.value) || (b.heat - a.heat))
    .forEach(l => add(l, 2, 'High value warm'));

  // Tier 3
  leads
    .filter(l => (l.relationship >= 60) && (l.priority >= 50) && (l.priority < 75))
    .sort((a,b) => (b.relationship - a.relationship) || (b.priority - a.priority))
    .forEach(l => add(l, 3, 'Nurture'));

  // Tier 4
  leads
    .filter(l => (l.daysSinceActivity > 30) && (l.value >= 50))
    .sort((a,b) => (b.value - a.value) || (b.daysSinceActivity - a.daysSinceActivity))
    .forEach(l => add(l, 4, 'Re-engage'));

  return queue;
}

// ---------------------------
// Header mapping (robust)
// ---------------------------
function normHeader(h) {
  return String(h || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^a-z0-9_]/g, '');
}

function getColumnIndices(headers) {
  const indices = {};
  const aliases = {
    id: ['id'],
    firstName: ['firstname','first_name'],
    lastName: ['lastname','last_name'],
    stage: ['stage'],
    primaryEmail: ['primaryemail','primary_email','email'],
    primaryPhone: ['primaryphone','primary_phone','phone'],
    lastActivity: ['lastactivity','last_activity','lastactivityat','last_activity_at'],

    priority_score: ['priority_score','priorityscore','priority'],
    heat_score: ['heat_score','heatscore','heat'],
    value_score: ['value_score','valuescore','value'],
    relationship_score: ['relationship_score','relationshipscore','relationship'],

    intent_repeat_views: ['intent_repeat_views','intentrepeatviews'],
    intent_high_favorites: ['intent_high_favorites','intenthighfavorites'],
    intent_activity_burst: ['intent_activity_burst','intentactivityburst'],
    intent_sharing: ['intent_sharing','intentsharing']
  };

  const headerIndex = {};
  headers.forEach((h, i) => { headerIndex[normHeader(h)] = i; });

  Object.entries(aliases).forEach(([key, list]) => {
    for (const candidate of list) {
      const idx = headerIndex[normHeader(candidate)];
      if (idx !== undefined) {
        indices[key] = idx;
        break;
      }
    }
  });

  return indices;
}

// ---------------------------
// Utilities
// ---------------------------
function toNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function toIsoDate(v) {
  if (!v) return '';
  const d = new Date(v);
  return isNaN(d.getTime()) ? '' : d.toISOString();
}

function daysSince(v) {
  if (!v) return 999;
  const d = new Date(v);
  if (isNaN(d.getTime())) return 999;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}
