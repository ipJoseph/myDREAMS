/**
 * FUB Dashboard - Enhanced Server Side Functions
 * 
 * Enhanced version with additional endpoints for charts, analysis, and insights
 */

// ============================================================================
// ENHANCED DATA RETRIEVAL FUNCTIONS
// ============================================================================

function getMetrics() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName('FUB Leads');
  
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
  const dataSheet = ss.getSheetByName('FUB Leads');
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  // Filter and format hot leads
  const hotLeads = rows
    .filter(row => row[cols.priority] >= 75)
    .sort((a, b) => b[cols.priority] - a[cols.priority])
    .map(row => ({
      id: row[cols.email] || row[cols.name],
      name: row[cols.name] || 'Unknown',
      email: row[cols.email] || '',
      phone: row[cols.phone] || '',
      stage: row[cols.stage] || 'N/A',
      priority: row[cols.priority] || 0,
      heat: row[cols.heat] || 0,
      value: row[cols.value] || 0,
      relationship: row[cols.relationship] || 0,
      daysSinceActivity: row[cols.daysSinceActivity] || 999,
      intentSignals: getIntentSignalsList(row, cols),
      suggestedAction: getSuggestedAction(row, cols)
    }));
  
  return hotLeads;
}

function getActionQueue() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName('FUB Leads');
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const queue = [];
  
  // Priority 1: Hot leads needing immediate contact
  rows.filter(row => row[cols.priority] >= 80 && row[cols.daysSinceActivity] <= 7)
    .forEach(row => {
      const item = formatActionItem(row, cols, 1);
      if (!queue.some(q => q.email === item.email)) {
        queue.push(item);
      }
    });
  
  // Priority 2: High value warm leads
  rows.filter(row => row[cols.value] >= 70 && row[cols.heat] >= 50 && row[cols.priority] < 80)
    .forEach(row => {
      const item = formatActionItem(row, cols, 2);
      if (!queue.some(q => q.email === item.email)) {
        queue.push(item);
      }
    });
  
  // Priority 3: Nurturing opportunities
  rows.filter(row => row[cols.relationship] >= 60 && row[cols.priority] >= 50 && row[cols.priority] < 75)
    .forEach(row => {
      const item = formatActionItem(row, cols, 3);
      if (!queue.some(q => q.email === item.email)) {
        queue.push(item);
      }
    });
  
  // Priority 4: Re-engagement needed
  rows.filter(row => row[cols.daysSinceActivity] > 30 && row[cols.value] >= 50)
    .forEach(row => {
      const item = formatActionItem(row, cols, 4);
      if (!queue.some(q => q.email === item.email)) {
        queue.push(item);
      }
    });
  
  return queue;
}

function getScoreAnalysis() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName('FUB Leads');
  
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
      count: rows.filter(r => r[cols.heat] >= 70 && r[cols.value] < 40).length,
      description: 'Engaged but potentially price shopping or early stage'
    },
    {
      category: 'High Value, Low Heat',
      count: rows.filter(r => r[cols.value] >= 70 && r[cols.heat] < 40).length,
      description: 'Hidden gems - quality prospects needing nurturing'
    },
    {
      category: 'Perfect Prospects',
      count: rows.filter(r => r[cols.heat] >= 70 && r[cols.value] >= 70 && r[cols.relationship] >= 70).length,
      description: 'All scores high - ready to close'
    },
    {
      category: 'Quality Over Quantity',
      count: rows.filter(r => countIntentSignals(r, cols) >= 4 && r[cols.heat] < 50).length,
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
  const dataSheet = ss.getSheetByName('FUB Leads');
  
  if (!dataSheet) {
    return {
      activityPattern: {}
    };
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const activityPattern = {
    'Active (< 7d)': rows.filter(r => r[cols.daysSinceActivity] <= 7).length,
    'Warm (7-30d)': rows.filter(r => r[cols.daysSinceActivity] > 7 && r[cols.daysSinceActivity] <= 30).length,
    'Cold (30-90d)': rows.filter(r => r[cols.daysSinceActivity] > 30 && r[cols.daysSinceActivity] <= 90).length,
    'Stale (> 90d)': rows.filter(r => r[cols.daysSinceActivity] > 90).length
  };
  
  return {
    activityPattern: activityPattern
  };
}

function getInsights() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName('FUB Leads');
  
  if (!dataSheet) {
    return [];
  }
  
  const data = dataSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);
  const cols = getColumnIndices(headers);
  
  const insights = [];
  
  // High value cold leads
  const highValueCold = rows.filter(r => r[cols.value] >= 70 && r[cols.heat] < 40).length;
  if (highValueCold > 0) {
    insights.push({
      type: 'opportunity',
      title: `${highValueCold} High-Value Cold Leads`,
      description: 'These are quality prospects who have gone quiet. A strategic re-engagement campaign could unlock significant opportunities.',
      action: 'Create a personalized re-engagement email sequence focusing on their specific interests.'
    });
  }
  
  // High engagement, low progression
  const highEngagementStuck = rows.filter(r => r[cols.heat] >= 70 && r[cols.relationship] < 40).length;
  if (highEngagementStuck > 0) {
    insights.push({
      type: 'warning',
      title: `${highEngagementStuck} Leads Stuck in Pipeline`,
      description: 'These leads are highly engaged but relationship scores are low, suggesting they may need more trust-building.',
      action: 'Schedule personal calls or video meetings to strengthen the relationship and move forward.'
    });
  }
  
  // Intent vs Activity mismatch
  const intentNoActivity = rows.filter(r => countIntentSignals(r, cols) >= 4 && r[cols.daysSinceActivity] > 14).length;
  if (intentNoActivity > 0) {
    insights.push({
      type: 'opportunity',
      title: `${intentNoActivity} High-Intent Quiet Leads`,
      description: 'Leads showing strong buying signals but haven\'t been contacted recently. These are prime for immediate outreach.',
      action: 'Prioritize these for contact today - they\'re showing buying signals and need attention.'
    });
  }
  
  // Stale high value leads
  const staleValuable = rows.filter(r => r[cols.daysSinceActivity] > 30 && r[cols.value] >= 60).length;
  if (staleValuable > 5) {
    insights.push({
      type: 'warning',
      title: `${staleValuable} Valuable Leads Going Stale`,
      description: 'A significant number of high-value prospects haven\'t been contacted in over 30 days. You risk losing these opportunities.',
      action: 'Implement an automated re-engagement sequence or assign these for immediate follow-up.'
    });
  }
  
  // Perfect prospects
  const perfect = rows.filter(r => r[cols.heat] >= 70 && r[cols.value] >= 70 && r[cols.relationship] >= 70).length;
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
    id: row[cols.email] || row[cols.name],
    name: row[cols.name] || 'Unknown',
    email: row[cols.email] || '',
    phone: row[cols.phone] || '',
    stage: row[cols.stage] || '',
    priority: priority,
    priorityScore: (row[cols.priority] || 0).toFixed(1),
    heat: row[cols.heat] || 0,
    value: row[cols.value] || 0,
    relationship: row[cols.relationship] || 0,
    daysSinceActivity: row[cols.daysSinceActivity] || 999,
    intentSignals: getIntentSignalsList(row, cols),
    suggestedAction: getSuggestedAction(row, cols)
  };
}

function getIntentSignalsList(row, cols) {
  const signals = [];
  
  if (cols.activeSearch !== undefined && row[cols.activeSearch]) signals.push('🔍 Active Search');
  if (cols.financialReady !== undefined && row[cols.financialReady]) signals.push('💰 Financial Ready');
  if (cols.locationFocus !== undefined && row[cols.locationFocus]) signals.push('📍 Location Focus');
  if (cols.timelineUrgent !== undefined && row[cols.timelineUrgent]) signals.push('⏱️ Timeline Urgent');
  if (cols.highEngagement !== undefined && row[cols.highEngagement]) signals.push('⚡ High Engagement');
  if (cols.qualityResponse !== undefined && row[cols.qualityResponse]) signals.push('✅ Quality Response');
  if (cols.specificCriteria !== undefined && row[cols.specificCriteria]) signals.push('🎯 Specific Criteria');
  
  return signals;
}

function getSuggestedAction(row, cols) {
  const priority = row[cols.priority] || 0;
  const heat = row[cols.heat] || 0;
  const value = row[cols.value] || 0;
  const days = row[cols.daysSinceActivity] || 999;
  const intentCount = countIntentSignals(row, cols);
  
  if (priority >= 90) {
    return '🔥 Immediate Contact - Top Priority';
  } else if (intentCount >= 5) {
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
  const signals = ['activeSearch', 'financialReady', 'locationFocus', 'timelineUrgent', 
                   'highEngagement', 'qualityResponse', 'specificCriteria'];
  
  signals.forEach(signal => {
    if (cols[signal] !== undefined && row[cols[signal]]) {
      count++;
    }
  });
  
  return count;
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
    const priority = row[cols.priority] || 0;
    const heat = row[cols.heat] || 0;
    const value = row[cols.value] || 0;
    const relationship = row[cols.relationship] || 0;
    const days = row[cols.daysSinceActivity] || 999;
    const intentCount = countIntentSignals(row, cols);
    
    totalPriority += priority;
    
    // Counts
    if (priority >= 75) metrics.hotLeads++;
    if (value >= 60) metrics.highValue++;
    if (days <= 7) metrics.activeThisWeek++;
    if (intentCount >= 4) metrics.highIntent++;
    if (priority >= 50 && priority < 75 && relationship >= 60) metrics.needsNurturing++;
    if (value >= 70 && heat < 40) metrics.highValueCold++;
    if (days > 30 && value >= 50) metrics.staleLeads++;
    
    // Distribution
    ['heat', 'value', 'relationship', 'priority'].forEach(metric => {
      const score = metric === 'priority' ? priority : 
                    metric === 'heat' ? heat :
                    metric === 'value' ? value : relationship;
      
      if (score >= 90) metrics.distribution[metric].excellent++;
      else if (score >= 70) metrics.distribution[metric].good++;
      else if (score >= 50) metrics.distribution[metric].medium++;
      else metrics.distribution[metric].low++;
    });
  });
  
  metrics.avgPriority = rows.length > 0 ? (totalPriority / rows.length).toFixed(1) : 0;
  
  return metrics;
}

function getColumnIndices(headers) {
  const indices = {};
  
  const mapping = {
    'name': ['name', 'full name', 'contact name'],
    'email': ['email', 'email address'],
    'phone': ['phone', 'phone number', 'mobile'],
    'stage': ['stage', 'pipeline stage'],
    'priority': ['priority score', 'priority_score', 'priority'],
    'heat': ['heat score', 'heat_score', 'heat'],
    'value': ['value score', 'value_score', 'value'],
    'relationship': ['relationship score', 'relationship_score', 'relationship'],
    'activeSearch': ['active_search', 'active search'],
    'financialReady': ['financial_ready', 'financial ready'],
    'locationFocus': ['location_focus', 'location focus'],
    'timelineUrgent': ['timeline_urgent', 'timeline urgent'],
    'highEngagement': ['high_engagement', 'high engagement'],
    'qualityResponse': ['quality_response', 'quality response'],
    'specificCriteria': ['specific_criteria', 'specific criteria'],
    'lastActivity': ['last_activity', 'last activity', 'last contacted'],
    'daysSinceActivity': ['days_since_activity', 'days since activity']
  };
  
  headers.forEach((header, index) => {
    const normalized = header.toLowerCase().trim();
    
    Object.entries(mapping).forEach(([key, variants]) => {
      if (variants.some(v => normalized.includes(v))) {
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
