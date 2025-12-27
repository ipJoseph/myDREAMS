/**
 * FUB Dashboard - Enhanced Server Side Functions
 * Updated to work with Joseph's actual sheet structure
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const CONFIG = {
  SHEET_NAME: 'Contacts',  // Your main data sheet
  THRESHOLDS: {
    HOT_PRIORITY: 75,
    HIGH_VALUE: 25,        // Adjusted - value scores are typically lower
    HIGH_INTENT: 2,        // Adjusted - only 4 intent flags total, so 2+ is significant
    EXCELLENT_SCORE: 90,
    GOOD_SCORE: 70,
    MEDIUM_SCORE: 50,
    EXCELLENT_HEAT: 120,   // Heat can exceed 100
    GOOD_HEAT: 80,
    MEDIUM_HEAT: 40
  }
};

// ============================================================================
// DATA RETRIEVAL FUNCTIONS
// ============================================================================

function getMetrics() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return {
      totalLeads: 0,
      hotLeads: 0,
      highValue: 0,
      activeThisWeek: 0,
      avgPriority: 0,
      highIntent: 0,
      hotPercent: 0
    };
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const metrics = calculateMetrics(rows, cols);
  
  // Add percentage
  if (metrics.totalLeads > 0) {
    metrics.hotPercent = ((metrics.hotLeads / metrics.totalLeads) * 100).toFixed(1);
  }
  
  return metrics;
}

function getHotLeads() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  // Filter and format hot leads
  const hotLeads = rows
    .filter(row => (row[cols.priority_score] || 0) >= CONFIG.THRESHOLDS.HOT_PRIORITY)
    .sort((a, b) => (b[cols.priority_score] || 0) - (a[cols.priority_score] || 0))
    .map(row => ({
      id: row[cols.primaryEmail] || row[cols.id],
      name: `${row[cols.firstName] || ''} ${row[cols.lastName] || ''}`.trim() || 'Unknown',
      email: row[cols.primaryEmail] || '',
      phone: row[cols.primaryPhone] || '',
      stage: row[cols.stage] || 'N/A',
      priority: row[cols.priority_score] || 0,
      heat: row[cols.heat_score] || 0,
      value: row[cols.value_score] || 0,
      relationship: row[cols.relationship_score] || 0,
      daysSinceActivity: getDaysSince(row[cols.lastActivity]),
      intentSignals: getIntentSignalsList(row, cols),
      suggestedAction: getSuggestedAction(row, cols)
    }));
  
  return hotLeads;
}

function getActionQueue() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const queue = [];
  const seen = new Set();
  
  // Priority 1: Hot leads needing immediate contact
  rows.filter(row => {
    const priority = row[cols.priority_score] || 0;
    const days = getDaysSince(row[cols.lastActivity]);
    return priority >= 80 && days <= 7;
  }).forEach(row => {
    const email = row[cols.primaryEmail];
    if (!seen.has(email)) {
      seen.add(email);
      queue.push(formatActionItem(row, cols, 1));
    }
  });
  
  // Priority 2: High value warm leads
  rows.filter(row => {
    const value = row[cols.value_score] || 0;
    const heat = row[cols.heat_score] || 0;
    const priority = row[cols.priority_score] || 0;
    return value >= 70 && heat >= 50 && priority < 80;
  }).forEach(row => {
    const email = row[cols.primaryEmail];
    if (!seen.has(email)) {
      seen.add(email);
      queue.push(formatActionItem(row, cols, 2));
    }
  });
  
  // Priority 3: Nurturing opportunities
  rows.filter(row => {
    const relationship = row[cols.relationship_score] || 0;
    const priority = row[cols.priority_score] || 0;
    return relationship >= 60 && priority >= 50 && priority < 75;
  }).forEach(row => {
    const email = row[cols.primaryEmail];
    if (!seen.has(email)) {
      seen.add(email);
      queue.push(formatActionItem(row, cols, 3));
    }
  });
  
  // Priority 4: Re-engagement needed
  rows.filter(row => {
    const days = getDaysSince(row[cols.lastActivity]);
    const value = row[cols.value_score] || 0;
    return days > 30 && value >= 50;
  }).forEach(row => {
    const email = row[cols.primaryEmail];
    if (!seen.has(email)) {
      seen.add(email);
      queue.push(formatActionItem(row, cols, 4));
    }
  });
  
  return queue;
}

function getScoreAnalysis() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return {
      priorityDist: { excellent: 0, good: 0, medium: 0, low: 0 },
      heatDist: { excellent: 0, good: 0, medium: 0, low: 0 },
      valueDist: { excellent: 0, good: 0, medium: 0, low: 0 },
      relationshipDist: { excellent: 0, good: 0, medium: 0, low: 0 },
      insights: []
    };
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const metrics = calculateMetrics(rows, cols);
  
  // Generate insights
  const insights = [
    {
      category: 'High Heat, Low Value',
      count: rows.filter(r => (r[cols.heat_score] || 0) >= 70 && (r[cols.value_score] || 0) < 40).length,
      description: 'Engaged but potentially price shopping or early stage'
    },
    {
      category: 'High Value, Low Heat',
      count: rows.filter(r => (r[cols.value_score] || 0) >= 70 && (r[cols.heat_score] || 0) < 40).length,
      description: 'Hidden gems - quality prospects needing nurturing'
    },
    {
      category: 'Perfect Prospects',
      count: rows.filter(r => 
        (r[cols.heat_score] || 0) >= 70 && 
        (r[cols.value_score] || 0) >= 70 && 
        (r[cols.relationship_score] || 0) >= 70
      ).length,
      description: 'All scores high - ready to close'
    },
    {
      category: 'Quality Over Quantity',
      count: rows.filter(r => countIntentSignals(r, cols) >= 3 && (r[cols.heat_score] || 0) < 50).length,
      description: 'Strong intent signals despite lower activity'
    }
  ];
  
  return {
    priorityDist: metrics.distribution.priority,
    heatDist: metrics.distribution.heat,
    valueDist: metrics.distribution.value,
    relationshipDist: metrics.distribution.relationship,
    insights: insights
  };
}

function getTrends() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return { activityPattern: {} };
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const activityPattern = {
    'Active (< 7d)': rows.filter(r => getDaysSince(r[cols.lastActivity]) <= 7).length,
    'Warm (7-30d)': rows.filter(r => {
      const days = getDaysSince(r[cols.lastActivity]);
      return days > 7 && days <= 30;
    }).length,
    'Cold (30-90d)': rows.filter(r => {
      const days = getDaysSince(r[cols.lastActivity]);
      return days > 30 && days <= 90;
    }).length,
    'Stale (> 90d)': rows.filter(r => getDaysSince(r[cols.lastActivity]) > 90).length
  };
  
  return { activityPattern: activityPattern };
}

function getInsights() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const insights = [];
  
  // High value cold leads
  const highValueCold = rows.filter(r => 
    (r[cols.value_score] || 0) >= 70 && 
    (r[cols.heat_score] || 0) < 40
  ).length;
  
  if (highValueCold > 0) {
    insights.push({
      type: 'opportunity',
      title: `${highValueCold} High-Value Cold Leads`,
      description: 'These are quality prospects who have gone quiet. A strategic re-engagement campaign could unlock significant opportunities.',
      action: 'Create a personalized re-engagement email sequence focusing on their specific interests.'
    });
  }
  
  // High engagement, low progression
  const highEngagementStuck = rows.filter(r => 
    (r[cols.heat_score] || 0) >= 70 && 
    (r[cols.relationship_score] || 0) < 40
  ).length;
  
  if (highEngagementStuck > 0) {
    insights.push({
      type: 'warning',
      title: `${highEngagementStuck} Leads Stuck in Pipeline`,
      description: 'These leads are highly engaged but relationship scores are low, suggesting they may need more trust-building.',
      action: 'Schedule personal calls or video meetings to strengthen the relationship and move forward.'
    });
  }
  
  // Intent vs Activity mismatch
  const intentNoActivity = rows.filter(r => 
    countIntentSignals(r, cols) >= 2 && 
    getDaysSince(r[cols.lastActivity]) > 14
  ).length;
  
  if (intentNoActivity > 0) {
    insights.push({
      type: 'opportunity',
      title: `${intentNoActivity} High-Intent Quiet Leads`,
      description: 'Leads showing strong buying signals but haven\'t been contacted recently. These are prime for immediate outreach.',
      action: 'Prioritize these for contact today - they\'re showing buying signals and need attention.'
    });
  }
  
  // Stale high value leads
  const staleValuable = rows.filter(r => 
    getDaysSince(r[cols.lastActivity]) > 30 && 
    (r[cols.value_score] || 0) >= 60
  ).length;
  
  if (staleValuable > 5) {
    insights.push({
      type: 'warning',
      title: `${staleValuable} Valuable Leads Going Stale`,
      description: 'A significant number of high-value prospects haven\'t been contacted in over 30 days. You risk losing these opportunities.',
      action: 'Implement an automated re-engagement sequence or assign these for immediate follow-up.'
    });
  }
  
  // Perfect prospects
  const perfect = rows.filter(r => 
    (r[cols.heat_score] || 0) >= 70 && 
    (r[cols.value_score] || 0) >= 70 && 
    (r[cols.relationship_score] || 0) >= 70
  ).length;
  
  if (perfect > 0) {
    insights.push({
      type: 'opportunity',
      title: `${perfect} Perfect Prospects Ready to Close`,
      description: 'These leads score high across all dimensions. They\'re hot, valuable, and have strong relationships with you.',
      action: 'Focus on closing these first - schedule property showings or listing appointments immediately.'
    });
  }
  
  return insights;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function formatActionItem(row, cols, priority) {
  return {
    id: row[cols.primaryEmail] || row[cols.id],
    name: `${row[cols.firstName] || ''} ${row[cols.lastName] || ''}`.trim() || 'Unknown',
    email: row[cols.primaryEmail] || '',
    phone: row[cols.primaryPhone] || '',
    stage: row[cols.stage] || '',
    priority: priority,
    priorityScore: (row[cols.priority_score] || 0).toFixed(1),
    heat: row[cols.heat_score] || 0,
    value: row[cols.value_score] || 0,
    relationship: row[cols.relationship_score] || 0,
    daysSinceActivity: getDaysSince(row[cols.lastActivity]),
    intentSignals: getIntentSignalsList(row, cols),
    suggestedAction: getSuggestedAction(row, cols)
  };
}

function getIntentSignalsList(row, cols) {
  const signals = [];
  
  if (cols.intent_repeat_views !== undefined && row[cols.intent_repeat_views]) {
    signals.push('🔍 Repeat Property Views');
  }
  if (cols.intent_high_favorites !== undefined && row[cols.intent_high_favorites]) {
    signals.push('💎 High Favorites');
  }
  if (cols.intent_activity_burst !== undefined && row[cols.intent_activity_burst]) {
    signals.push('⚡ Activity Burst');
  }
  if (cols.intent_sharing !== undefined && row[cols.intent_sharing]) {
    signals.push('📤 Active Sharing');
  }
  
  return signals;
}

function getSuggestedAction(row, cols) {
  const priority = row[cols.priority_score] || 0;
  const heat = row[cols.heat_score] || 0;
  const value = row[cols.value_score] || 0;
  const days = getDaysSince(row[cols.lastActivity]);
  const intentCount = countIntentSignals(row, cols);
  
  if (priority >= 90) {
    return '🔥 Immediate Contact - Top Priority';
  } else if (intentCount >= 2) {
    return '🎯 Schedule Showing - High Intent';
  } else if (value >= 80 && heat >= 70) {
    return '💎 Present Listing - Ready to Close';
  } else if (days > 30 && value >= 60) {
    return '📧 Re-engagement Email';
  } else if (heat >= 70 && value < 50) {
    return '📊 Send Market Analysis';
  } else if (priority >= 75) {
    return '📱 Follow Up Call';
  } else {
    return '🌱 Nurture with Content';
  }
}

function countIntentSignals(row, cols) {
  let count = 0;
  
  if (cols.intent_repeat_views !== undefined && row[cols.intent_repeat_views]) count++;
  if (cols.intent_high_favorites !== undefined && row[cols.intent_high_favorites]) count++;
  if (cols.intent_activity_burst !== undefined && row[cols.intent_activity_burst]) count++;
  if (cols.intent_sharing !== undefined && row[cols.intent_sharing]) count++;
  
  return count;
}

function getDaysSince(dateValue) {
  if (!dateValue) return 999;
  
  try {
    const lastDate = new Date(dateValue);
    const now = new Date();
    const diffTime = Math.abs(now - lastDate);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  } catch (e) {
    return 999;
  }
}

function calculateMetrics(rows, cols) {
  const metrics = {
    totalLeads: rows.length,
    hotLeads: 0,
    highValue: 0,
    activeThisWeek: 0,
    highIntent: 0,
    needsNurturing: 0,
    highValueCold: 0,
    staleLeads: 0,
    avgPriority: 0,
    distribution: {
      heat: { excellent: 0, good: 0, medium: 0, low: 0 },
      value: { excellent: 0, good: 0, medium: 0, low: 0 },
      relationship: { excellent: 0, good: 0, medium: 0, low: 0 },
      priority: { excellent: 0, good: 0, medium: 0, low: 0 }
    }
  };
  
  let totalPriority = 0;
  
  rows.forEach(row => {
    const priority = row[cols.priority_score] || 0;
    const heat = row[cols.heat_score] || 0;
    const value = row[cols.value_score] || 0;
    const relationship = row[cols.relationship_score] || 0;
    const days = getDaysSince(row[cols.lastActivity]);
    const intentCount = countIntentSignals(row, cols);
    
    totalPriority += priority;
    
    // Counts
    if (priority >= CONFIG.THRESHOLDS.HOT_PRIORITY) metrics.hotLeads++;
    if (value >= CONFIG.THRESHOLDS.HIGH_VALUE) metrics.highValue++;
    if (days <= 7) metrics.activeThisWeek++;
    if (intentCount >= 3) metrics.highIntent++;
    if (priority >= 50 && priority < 75 && relationship >= 60) metrics.needsNurturing++;
    if (value >= 70 && heat < 40) metrics.highValueCold++;
    if (days > 30 && value >= 50) metrics.staleLeads++;
    
    // Distribution for heat (can exceed 100)
    const scores = {
      heat: heat,
      value: value,
      relationship: relationship,
      priority: priority
    };
    
    // Heat score uses different thresholds (can exceed 100)
    if (heat >= CONFIG.THRESHOLDS.EXCELLENT_HEAT) {
      metrics.distribution.heat.excellent++;
    } else if (heat >= CONFIG.THRESHOLDS.GOOD_HEAT) {
      metrics.distribution.heat.good++;
    } else if (heat >= CONFIG.THRESHOLDS.MEDIUM_HEAT) {
      metrics.distribution.heat.medium++;
    } else {
      metrics.distribution.heat.low++;
    }
    
    // Other scores use standard 0-100 scale
    ['value', 'relationship', 'priority'].forEach(metric => {
      const score = scores[metric];
      
      if (score >= CONFIG.THRESHOLDS.EXCELLENT_SCORE) {
        metrics.distribution[metric].excellent++;
      } else if (score >= CONFIG.THRESHOLDS.GOOD_SCORE) {
        metrics.distribution[metric].good++;
      } else if (score >= CONFIG.THRESHOLDS.MEDIUM_SCORE) {
        metrics.distribution[metric].medium++;
      } else {
        metrics.distribution[metric].low++;
      }
    });
  });
  
  metrics.avgPriority = rows.length > 0 ? (totalPriority / rows.length).toFixed(1) : 0;
  
  return metrics;
}

function getColumnIndices(headers) {
  const indices = {};
  
  // Map exact column names from your Python script
  const mapping = {
    'id': 'id',
    'firstName': 'firstName',
    'lastName': 'lastName',
    'stage': 'stage',
    'primaryEmail': 'primaryEmail',
    'primaryPhone': 'primaryPhone',
    'lastActivity': 'lastActivity',
    'priority_score': 'priority_score',
    'heat_score': 'heat_score',
    'value_score': 'value_score',
    'relationship_score': 'relationship_score',
    'intent_repeat_views': 'intent_repeat_views',
    'intent_high_favorites': 'intent_high_favorites',
    'intent_activity_burst': 'intent_activity_burst',
    'intent_sharing': 'intent_sharing'
  };
  
  headers.forEach((header, index) => {
    const normalized = header.trim();
    
    Object.entries(mapping).forEach(([key, value]) => {
      if (normalized === value) {
        indices[key] = index;
      }
    });
  });
  
  return indices;
}

// ============================================================================
// WEB APP DEPLOYMENT
// ============================================================================

function doGet() {
  return HtmlService.createHtmlOutputFromFile('fub_dashboard_enhanced')
    .setTitle('FUB Lead Intelligence Dashboard')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
