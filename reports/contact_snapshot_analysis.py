#!/usr/bin/env python3
"""
Contact Snapshots: Historical Analysis Report
==============================================
Analyzes 92,861 snapshots across 898 contacts (Jan 1 - Mar 13, 2026)
Generates charts and insights for the myDREAMS CRM pipeline.
"""
import sqlite3
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'dreams.db')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'snapshot_analysis')
os.makedirs(OUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)

# Style
plt.rcParams.update({
    'figure.facecolor': '#0f1117',
    'axes.facecolor': '#1a1d27',
    'axes.edgecolor': '#333',
    'axes.labelcolor': '#ccc',
    'text.color': '#ccc',
    'xtick.color': '#999',
    'ytick.color': '#999',
    'grid.color': '#2a2d37',
    'grid.alpha': 0.6,
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
})
COLORS = {
    'Lead': '#4dabf7',
    'Nurture': '#69db7c',
    'Active Client': '#ffd43b',
    'Hot Prospect': '#ff6b6b',
    'Under Contract': '#da77f2',
    'Closed': '#20c997',
    'Trash': '#868e96',
    'Unresponsive': '#495057',
    'Agents/Vendors/Lendors': '#748ffc',
}
ACCENT = '#7c5cfc'
GOLD = '#ffd43b'
RED = '#ff6b6b'
GREEN = '#69db7c'
BLUE = '#4dabf7'

# ============================================================
# CHART 1: Pipeline Funnel (current snapshot)
# ============================================================
print("Generating Chart 1: Pipeline Funnel...")
df_funnel = pd.read_sql("""
    SELECT stage, COUNT(DISTINCT contact_id) as contacts
    FROM contact_snapshots
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM contact_snapshots)
    GROUP BY stage
    ORDER BY contacts DESC
""", conn)

fig, ax = plt.subplots(figsize=(12, 6))
bars = ax.barh(df_funnel['stage'], df_funnel['contacts'],
               color=[COLORS.get(s, '#666') for s in df_funnel['stage']],
               edgecolor='none', height=0.7)
for bar, val in zip(bars, df_funnel['contacts']):
    ax.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2,
            f'{val}', va='center', fontsize=12, fontweight='bold', color='#ddd')
ax.set_xlabel('Number of Contacts')
ax.set_title('Current Pipeline Distribution (Mar 13, 2026)')
ax.invert_yaxis()
ax.grid(axis='x', linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '01_pipeline_funnel.png'), dpi=150)
plt.close()

# ============================================================
# CHART 2: Stage Composition Over Time
# ============================================================
print("Generating Chart 2: Stage composition over time...")
df_time = pd.read_sql("""
    SELECT DATE(snapshot_at) as snap_date, stage, COUNT(DISTINCT contact_id) as contacts
    FROM contact_snapshots
    WHERE stage IN ('Lead', 'Nurture', 'Active Client', 'Hot Prospect')
    GROUP BY DATE(snapshot_at), stage
""", conn)
df_time['snap_date'] = pd.to_datetime(df_time['snap_date'])
pivot = df_time.pivot_table(index='snap_date', columns='stage', values='contacts', fill_value=0)

fig, ax = plt.subplots(figsize=(14, 6))
for col in ['Lead', 'Nurture', 'Active Client', 'Hot Prospect']:
    if col in pivot.columns:
        ax.plot(pivot.index, pivot[col], label=col, color=COLORS[col], linewidth=2)
ax.set_xlabel('Date')
ax.set_ylabel('Contacts')
ax.set_title('Active Pipeline Stages Over Time')
ax.legend(loc='upper left', framealpha=0.8)
ax.grid(True, linestyle='--')
fig.autofmt_xdate()
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '02_stages_over_time.png'), dpi=150)
plt.close()

# ============================================================
# CHART 3: Scoring Profile by Stage (Radar-like grouped bar)
# ============================================================
print("Generating Chart 3: Scoring profiles by stage...")
df_scores = pd.read_sql("""
    SELECT stage,
           AVG(heat_score) as heat,
           AVG(value_score) as value,
           AVG(relationship_score) as relationship,
           AVG(priority_score) as priority
    FROM contact_snapshots
    WHERE stage IN ('Lead', 'Nurture', 'Active Client', 'Hot Prospect', 'Under Contract', 'Closed')
    GROUP BY stage
""", conn)

stages = df_scores['stage'].tolist()
metrics = ['heat', 'value', 'relationship', 'priority']
x = np.arange(len(stages))
width = 0.2
metric_colors = [RED, GOLD, GREEN, ACCENT]

fig, ax = plt.subplots(figsize=(14, 6))
for i, (metric, color) in enumerate(zip(metrics, metric_colors)):
    offset = (i - 1.5) * width
    bars = ax.bar(x + offset, df_scores[metric], width, label=metric.title(),
                  color=color, edgecolor='none', alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(stages, rotation=20, ha='right')
ax.set_ylabel('Average Score')
ax.set_title('Scoring Profiles by Pipeline Stage')
ax.legend(loc='upper right', framealpha=0.8)
ax.grid(axis='y', linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '03_scoring_by_stage.png'), dpi=150)
plt.close()

# ============================================================
# CHART 4: Call Activity vs Stage Progression
# ============================================================
print("Generating Chart 4: Call activity vs stage...")
df_calls = pd.read_sql("""
    SELECT
        CASE
            WHEN calls_outbound + calls_inbound > 5 THEN '5+'
            WHEN calls_outbound + calls_inbound BETWEEN 3 AND 5 THEN '3-5'
            WHEN calls_outbound + calls_inbound BETWEEN 1 AND 2 THEN '1-2'
            ELSE '0'
        END as call_bucket,
        stage,
        COUNT(DISTINCT contact_id) as contacts
    FROM contact_snapshots
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM contact_snapshots)
      AND stage IN ('Lead', 'Nurture', 'Active Client', 'Closed')
    GROUP BY call_bucket, stage
""", conn)

pivot_calls = df_calls.pivot_table(index='call_bucket', columns='stage', values='contacts', fill_value=0)
# Reorder
bucket_order = ['0', '1-2', '3-5', '5+']
pivot_calls = pivot_calls.reindex(bucket_order)
stage_order = ['Lead', 'Nurture', 'Active Client', 'Closed']
pivot_calls = pivot_calls[[s for s in stage_order if s in pivot_calls.columns]]

fig, ax = plt.subplots(figsize=(12, 6))
pivot_calls.plot(kind='bar', ax=ax, color=[COLORS[s] for s in pivot_calls.columns],
                 edgecolor='none', width=0.7)
ax.set_xlabel('Total Calls (Inbound + Outbound)')
ax.set_ylabel('Number of Contacts')
ax.set_title('Call Volume and Pipeline Stage')
ax.legend(title='Stage', framealpha=0.8)
ax.grid(axis='y', linestyle='--')
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '04_calls_vs_stage.png'), dpi=150)
plt.close()

# ============================================================
# CHART 5: Heat Score Decay - "Hot to Cold" Contacts
# ============================================================
print("Generating Chart 5: Heat decay trajectories...")

# Get time series for contacts that peaked above 70 and have enough data points
hot_contacts = pd.read_sql("""
    SELECT contact_id, first_name, last_name
    FROM contact_snapshots
    GROUP BY contact_id
    HAVING MAX(heat_score) >= 70 AND COUNT(*) > 20
    ORDER BY MAX(heat_score) DESC
    LIMIT 8
""", conn)

fig, ax = plt.subplots(figsize=(14, 7))
for _, row in hot_contacts.iterrows():
    cid = row['contact_id']
    name = f"{row['first_name']} {row['last_name'][:1]}."
    ts = pd.read_sql(f"""
        SELECT DATE(snapshot_at) as dt, heat_score
        FROM contact_snapshots
        WHERE contact_id = '{cid}'
        ORDER BY snapshot_at
    """, conn)
    ts['dt'] = pd.to_datetime(ts['dt'])
    # Deduplicate by date, take last value
    ts = ts.groupby('dt').last().reset_index()
    ax.plot(ts['dt'], ts['heat_score'], label=name, linewidth=2, alpha=0.85)

ax.axhline(y=50, color=GOLD, linestyle='--', alpha=0.5, label='Engagement Threshold (50)')
ax.set_xlabel('Date')
ax.set_ylabel('Heat Score')
ax.set_title('Heat Score Trajectories: High-Engagement Contacts')
ax.legend(loc='upper right', fontsize=9, framealpha=0.8)
ax.grid(True, linestyle='--')
ax.set_ylim(0, 105)
fig.autofmt_xdate()
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '05_heat_decay.png'), dpi=150)
plt.close()

# ============================================================
# CHART 6: Website Activity vs Conversion
# ============================================================
print("Generating Chart 6: Website activity vs conversion...")
df_web = pd.read_sql("""
    SELECT contact_id, stage,
           MAX(website_visits) as visits,
           MAX(properties_viewed) as viewed,
           MAX(properties_favorited) as favorited,
           MAX(heat_score) as peak_heat,
           MAX(avg_price_viewed) as avg_price
    FROM contact_snapshots
    WHERE stage IN ('Lead', 'Nurture', 'Active Client', 'Closed')
      AND (website_visits > 0 OR properties_viewed > 0)
    GROUP BY contact_id
""", conn)

fig, ax = plt.subplots(figsize=(14, 8))
for stage in ['Lead', 'Nurture', 'Active Client', 'Closed']:
    subset = df_web[df_web['stage'] == stage]
    scatter = ax.scatter(subset['visits'], subset['viewed'],
                        s=subset['favorited'].clip(1) * 15 + 20,
                        c=COLORS[stage], alpha=0.6, label=stage, edgecolors='white', linewidth=0.3)
ax.set_xlabel('Website Visits')
ax.set_ylabel('Properties Viewed')
ax.set_title('Digital Engagement Map: Visits vs Views (bubble size = favorites)')
ax.legend(framealpha=0.8)
ax.grid(True, linestyle='--')
ax.set_xlim(-2, 120)
ax.set_ylim(-5, 250)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '06_engagement_map.png'), dpi=150)
plt.close()

# ============================================================
# CHART 7: The "Silent Buyers" - High Activity, Zero Calls
# ============================================================
print("Generating Chart 7: Silent buyers...")
df_silent = pd.read_sql("""
    SELECT contact_id, first_name, last_name, stage,
           MAX(heat_score) as peak_heat,
           MAX(website_visits) as visits,
           MAX(properties_viewed) as viewed,
           MAX(properties_favorited) as favorited,
           MAX(avg_price_viewed) as avg_price
    FROM contact_snapshots
    WHERE (calls_outbound + calls_inbound) = 0
      AND properties_viewed > 10
    GROUP BY contact_id
    ORDER BY peak_heat DESC
    LIMIT 15
""", conn)

fig, ax = plt.subplots(figsize=(14, 7))
names = [f"{r['first_name']} {r['last_name'][:1]}." for _, r in df_silent.iterrows()]
x = np.arange(len(names))
w = 0.35
ax.bar(x - w/2, df_silent['viewed'], w, label='Properties Viewed', color=BLUE, edgecolor='none')
ax.bar(x + w/2, df_silent['visits'], w, label='Website Visits', color=GREEN, edgecolor='none')
# Overlay favorites as markers
ax2 = ax.twinx()
ax2.scatter(x, df_silent['favorited'], color=RED, s=80, zorder=5, label='Favorites', marker='D')
ax2.set_ylabel('Favorites', color=RED)
ax2.tick_params(axis='y', labelcolor=RED)

ax.set_xticks(x)
ax.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax.set_ylabel('Count')
ax.set_title('"Silent Buyers": High Digital Activity, Zero Phone Contact')
ax.legend(loc='upper left', framealpha=0.8)
ax2.legend(loc='upper right', framealpha=0.8)
ax.grid(axis='y', linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '07_silent_buyers.png'), dpi=150)
plt.close()

# ============================================================
# CHART 8: Price Tier Segmentation
# ============================================================
print("Generating Chart 8: Price tier analysis...")
df_price = pd.read_sql("""
    SELECT contact_id, stage,
           MAX(avg_price_viewed) as avg_price,
           MAX(heat_score) as peak_heat,
           MAX(properties_viewed) as viewed,
           MAX(calls_outbound + calls_inbound) as total_calls
    FROM contact_snapshots
    WHERE avg_price_viewed > 0
      AND stage IN ('Lead', 'Nurture', 'Active Client', 'Closed')
    GROUP BY contact_id
""", conn)

def price_tier(p):
    if p < 100000: return 'Under $100K'
    elif p < 250000: return '$100K-$250K'
    elif p < 500000: return '$250K-$500K'
    elif p < 1000000: return '$500K-$1M'
    else: return '$1M+'

df_price['tier'] = df_price['avg_price'].apply(price_tier)
tier_order = ['Under $100K', '$100K-$250K', '$250K-$500K', '$500K-$1M', '$1M+']
tier_counts = df_price.groupby(['tier', 'stage']).size().unstack(fill_value=0)
tier_counts = tier_counts.reindex(tier_order)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Left: count by tier
tier_total = df_price['tier'].value_counts().reindex(tier_order)
bars = ax1.bar(tier_order, tier_total, color=[ACCENT, BLUE, GREEN, GOLD, RED], edgecolor='none')
for bar, val in zip(bars, tier_total):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             str(val), ha='center', fontsize=11, fontweight='bold', color='#ddd')
ax1.set_title('Contacts by Price Tier')
ax1.set_ylabel('Contacts')
ax1.tick_params(axis='x', rotation=20)
ax1.grid(axis='y', linestyle='--')

# Right: avg heat by tier
heat_by_tier = df_price.groupby('tier')['peak_heat'].mean().reindex(tier_order)
bars2 = ax2.bar(tier_order, heat_by_tier, color=[ACCENT, BLUE, GREEN, GOLD, RED], edgecolor='none')
for bar, val in zip(bars2, heat_by_tier):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             f'{val:.0f}', ha='center', fontsize=11, fontweight='bold', color='#ddd')
ax2.set_title('Avg Peak Heat Score by Price Tier')
ax2.set_ylabel('Heat Score')
ax2.tick_params(axis='x', rotation=20)
ax2.grid(axis='y', linestyle='--')

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '08_price_tiers.png'), dpi=150)
plt.close()

# ============================================================
# CHART 9: Favoriting as Conversion Signal
# ============================================================
print("Generating Chart 9: Favorites as signal...")
df_fav = pd.read_sql("""
    SELECT
        CASE
            WHEN properties_favorited >= 10 THEN '10+'
            WHEN properties_favorited BETWEEN 5 AND 9 THEN '5-9'
            WHEN properties_favorited BETWEEN 1 AND 4 THEN '1-4'
            ELSE '0'
        END as fav_bucket,
        COUNT(DISTINCT contact_id) as total,
        SUM(CASE WHEN stage IN ('Active Client', 'Closed', 'Under Contract') THEN 1 ELSE 0 END) as converted
    FROM contact_snapshots
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM contact_snapshots)
      AND stage NOT IN ('Agents/Vendors/Lendors', 'Trash')
    GROUP BY fav_bucket
""", conn)
fav_order = ['0', '1-4', '5-9', '10+']
df_fav = df_fav.set_index('fav_bucket').reindex(fav_order).reset_index()
df_fav['pct'] = (df_fav['converted'] / df_fav['total'] * 100).fillna(0)

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(df_fav['fav_bucket'], df_fav['pct'],
              color=[BLUE, GREEN, GOLD, RED], edgecolor='none', width=0.6)
for bar, row in zip(bars, df_fav.itertuples()):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f'{row.pct:.1f}%\n({row.converted}/{row.total})',
            ha='center', fontsize=11, color='#ddd')
ax.set_xlabel('Properties Favorited')
ax.set_ylabel('Conversion Rate (%)')
ax.set_title('Favoriting Behavior as Conversion Predictor')
ax.grid(axis='y', linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '09_favorites_conversion.png'), dpi=150)
plt.close()

# ============================================================
# CHART 10: Lead Source Quality
# ============================================================
print("Generating Chart 10: Lead source quality...")
df_source = pd.read_sql("""
    SELECT source,
           COUNT(DISTINCT contact_id) as total,
           AVG(heat_score) as avg_heat,
           SUM(CASE WHEN stage IN ('Active Client', 'Closed', 'Under Contract') THEN 1 ELSE 0 END) as converted
    FROM contact_snapshots
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM contact_snapshots)
      AND source IS NOT NULL AND source != ''
    GROUP BY source
    HAVING total >= 3
    ORDER BY total DESC
""", conn)
df_source['conv_rate'] = df_source['converted'] / df_source['total'] * 100

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
# Volume
ax1.barh(df_source['source'], df_source['total'], color=BLUE, edgecolor='none')
ax1.set_xlabel('Contacts')
ax1.set_title('Lead Volume by Source')
ax1.invert_yaxis()
ax1.grid(axis='x', linestyle='--')

# Quality
ax2.barh(df_source['source'], df_source['avg_heat'], color=RED, edgecolor='none')
ax2.set_xlabel('Avg Heat Score')
ax2.set_title('Lead Quality by Source (Avg Heat)')
ax2.invert_yaxis()
ax2.grid(axis='x', linestyle='--')

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '10_lead_source_quality.png'), dpi=150)
plt.close()

# ============================================================
# CHART 11: Communication Gap Analysis
# ============================================================
print("Generating Chart 11: Communication gaps...")
df_gap = pd.read_sql("""
    SELECT contact_id, first_name, last_name, stage,
           heat_score, properties_viewed, website_visits, properties_favorited,
           calls_outbound, calls_inbound, avg_price_viewed
    FROM contact_snapshots
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM contact_snapshots)
      AND heat_score >= 40
      AND (calls_outbound + calls_inbound) <= 2
      AND stage IN ('Lead', 'Nurture')
    ORDER BY heat_score DESC
    LIMIT 12
""", conn)

fig, ax = plt.subplots(figsize=(14, 7))
names = [f"{r['first_name']} {r['last_name'][:1]}." for _, r in df_gap.iterrows()]
x = np.arange(len(names))

ax.bar(x, df_gap['heat_score'], color=RED, alpha=0.8, label='Heat Score', edgecolor='none')
ax.bar(x, -(df_gap['calls_outbound'] + df_gap['calls_inbound']) * 10, color=GREEN,
       alpha=0.8, label='Calls (x10 scale)', edgecolor='none')
ax.axhline(y=0, color='#555', linewidth=1)
ax.set_xticks(x)
ax.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax.set_ylabel('Heat Score (up) / Call Effort (down)')
ax.set_title('Communication Gap: Hot Contacts with Minimal Outreach')
ax.legend(framealpha=0.8)
ax.grid(axis='y', linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '11_communication_gaps.png'), dpi=150)
plt.close()

# ============================================================
# CHART 12: Kevin Lewis Journey (Success Story)
# ============================================================
print("Generating Chart 12: Kevin Lewis journey...")
df_kevin = pd.read_sql("""
    SELECT DATE(snapshot_at) as dt, stage, heat_score,
           calls_outbound, calls_inbound, relationship_score
    FROM contact_snapshots
    WHERE contact_id = '5272'
    ORDER BY snapshot_at
""", conn)
df_kevin['dt'] = pd.to_datetime(df_kevin['dt'])
df_kevin = df_kevin.groupby('dt').last().reset_index()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

# Stage timeline
stage_map = {'Lead': 1, 'Nurture': 2, 'Active Client': 3, 'Under Contract': 4, 'Closed': 5}
df_kevin['stage_num'] = df_kevin['stage'].map(stage_map)
for stage, num in stage_map.items():
    mask = df_kevin['stage'] == stage
    if mask.any():
        ax1.fill_between(df_kevin['dt'], 0, 1, where=mask,
                        color=COLORS.get(stage, '#666'), alpha=0.6, label=stage)
ax1.set_yticks([])
ax1.set_title('Kevin Lewis: From Active Client to Closed (Success Path)')
ax1.legend(loc='upper left', ncol=5, fontsize=9, framealpha=0.8)

# Metrics
ax2.plot(df_kevin['dt'], df_kevin['calls_outbound'], label='Calls Out', color=BLUE, linewidth=2)
ax2.plot(df_kevin['dt'], df_kevin['calls_inbound'], label='Calls In', color=GREEN, linewidth=2)
ax2.plot(df_kevin['dt'], df_kevin['relationship_score'], label='Relationship Score',
         color=ACCENT, linewidth=2, linestyle='--')
ax2.set_ylabel('Count / Score')
ax2.set_xlabel('Date')
ax2.legend(framealpha=0.8)
ax2.grid(True, linestyle='--')
fig.autofmt_xdate()
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, '12_kevin_lewis_journey.png'), dpi=150)
plt.close()

conn.close()

print(f"\nAll charts saved to: {OUT_DIR}/")
print("Charts generated:")
for f in sorted(os.listdir(OUT_DIR)):
    if f.endswith('.png'):
        print(f"  {f}")
