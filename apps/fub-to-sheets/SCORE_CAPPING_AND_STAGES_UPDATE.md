# Score Capping & Stage Multipliers Update

## 🎯 What Changed

### 1. **Removed Hard Score Caps**

**Before:**
- All scores capped at 100 (heat, value, relationship, priority)
- Leads scoring 150+ all showed as "100"
- No differentiation between truly exceptional leads

**After:**
- Heat score: Optional cap (disabled by default)
- Value score: No cap
- Relationship score: No cap  
- Priority score: No cap

**Why this is better:**
- Preserves differentiation between high performers
- A lead with 150 heat is clearly hotter than one with 100
- Sorting/ranking works properly now

### 2. **Stage Multipliers Now Match Your FUB Stages**

**Your Actual FUB Stages:**
- Lead
- Nurture
- Hot Prospect
- Active Client
- Closed
- Past Client
- Agents/Vendors/Lendors
- Unresponsive
- Trash
- Blank

**New Multipliers (all configurable in .env):**

```
Hot Prospect          → 1.4  (Highest priority)
Active Client         → 1.3  (Working with you actively)
Lead                  → 1.1  (Fresh opportunity)
Nurture               → 1.0  (Baseline)
Past Client           → 0.9  (Good for referrals)
Unresponsive          → 0.5  (Low engagement)
Closed                → 0.3  (Deal done, low priority)
Agents/Vendors/Lendors → 0.0  (Not leads)
Trash                 → 0.0  (Filter out)
Blank/Empty           → 1.0  (Default)
```

---

## 📊 What You'll See Now

### **Heat Scores:**
- Can exceed 100 (disabled cap by default)
- Truly hot leads might score 120-180
- You can enable capping in .env if you prefer

### **Priority Scores:**
- Can exceed 100
- Top leads might score 110-150
- Better differentiation in "Top Priority 20" sheet

### **Stage Impact:**
- "Hot Prospect" leads get 1.4× boost
- "Active Client" leads get 1.3× boost
- "Unresponsive" leads get 0.5× (cut in half)
- "Trash" and "Agents/Vendors/Lendors" get 0× (filtered to bottom)

---

## ⚙️ Configuration Options

### **Enable Score Capping (Optional):**

Add to your `.env` file:
```bash
# Enable 100-point cap on heat score
HEAT_SCORE_CAP_ENABLED=true
HEAT_SCORE_CAP_VALUE=100
```

### **Customize Stage Multipliers:**

Add/modify in your `.env` file:
```bash
# Adjust any stage multiplier
STAGE_MULTIPLIER_HOT_PROSPECT=1.5  # Make even higher priority
STAGE_MULTIPLIER_PAST_CLIENT=0.7   # Lower priority
STAGE_MULTIPLIER_UNRESPONSIVE=0.3  # Even lower
```

---

## 📈 Real-World Example

**Lead: Sarah Johnson**
- Stage: "Hot Prospect"
- Heat Score: 95
- Value Score: 75
- Relationship Score: 80

**OLD Calculation:**
```
Priority = (95×0.5 + 75×0.2 + 80×0.3) × 1.0 (wrong stage)
         = (47.5 + 15 + 24) × 1.0
         = 86.5
```

**NEW Calculation:**
```
Priority = (95×0.5 + 75×0.2 + 80×0.3) × 1.4 (Hot Prospect)
         = (47.5 + 15 + 24) × 1.4
         = 121.1
```

Sarah now properly ranks at the top because she's in "Hot Prospect" stage!

---

## 🧪 Testing Recommendations

1. **Run the script once** and check the results
2. **Look at Top Priority 20** - do they make sense?
3. **Check "Hot Prospect" leads** - they should rank higher now
4. **Check "Trash" and "Agents/Vendors/Lendors"** - they should be at the bottom (score × 0.0)
5. **Look for leads with heat > 100** - these are your hottest leads!

---

## 🔧 Tuning Guidance

### **If priority scores seem too high:**
- Enable heat score capping: `HEAT_SCORE_CAP_ENABLED=true`
- Lower stage multipliers slightly

### **If "Hot Prospect" not ranking high enough:**
- Increase multiplier: `STAGE_MULTIPLIER_HOT_PROSPECT=1.5`

### **If "Past Client" cluttering your lists:**
- Lower multiplier: `STAGE_MULTIPLIER_PAST_CLIENT=0.5`

### **If "Unresponsive" should be excluded entirely:**
- Set to zero: `STAGE_MULTIPLIER_UNRESPONSIVE=0.0`

---

## 📝 Summary

✅ Score caps removed - better differentiation
✅ Stage multipliers match your FUB stages
✅ All settings configurable in .env
✅ Hot Prospects get proper priority boost
✅ Trash/Agents filtered to bottom

Your scoring system now properly reflects your actual sales pipeline stages!
