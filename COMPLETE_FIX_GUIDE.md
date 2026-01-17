# Complete Fix Guide - Walking Over-Preference & Straight Lines

## Root Causes Identified

### Issue 1: Walking Always Preferred ❌
**Problem**: Ruggles → Back Bay suggests walking via multiple Green Line stations instead of direct Orange Line.

**Root Cause**: ALL train edges have `time_seconds: 0` in the graph!
- Dijkstra sees: Walk (300 seconds) vs Train (0 seconds)
- Obviously prefers 0-second train
- But then realizes there's no actual route because all train edges are 0
- Falls back to walking paths which DO have times

**Fix**: Add comprehensive edge weights:
- Train travel time + Expected wait time (headway/2)
- This makes trains competitive but not artificially fast

### Issue 2: Straight-Line Walking Paths ❌
**Problem**: Walking routes display as straight lines instead of following streets.

**Root Cause**: `build_transit_graph.py` calls OSRM but doesn't save the geometry.
- OSRM returns actual street routing
- But geometry is discarded
- Only time/distance saved

**Fix**: Save geometry from OSRM in walking edges

---

## Solution: Complete Rebuild

You need to rebuild the graph with:
1. ✅ Walking edges with OSRM geometry (for street-following paths)
2. ✅ Train edges with travel time + wait time (so trains are competitive)

---

## Step-by-Step Fix

### Step 1: Backup Current Graph
```bash
cd backend/data
cp mbta_transit_graph.json mbta_transit_graph_backup.json
```

### Step 2: Rebuild Graph with Geometry
```bash
cd backend
export MBTA_API_KEY='your_api_key'
python3 build_transit_graph.py
```

**This now:**
- ✅ Uses OSRM for walking times AND geometry
- ✅ Saves geometry in walking edges
- ⚠️ Still creates train edges with time_seconds: 0 (we'll fix next)

### Step 3: Add Comprehensive Edge Weights
```bash
export MBTA_API_KEY='your_api_key'
python3 compute_edge_weights.py
```

**This adds:**
- Train travel times (from MBTA API or estimates)
- Expected wait times (headway/2)
- Total edge weight = travel_time + wait_time

**Output**: `data/mbta_transit_graph_weighted.json`

### Step 4: Replace Graph
```bash
cd data
mv mbta_transit_graph.json mbta_transit_graph_old.json
mv mbta_transit_graph_weighted.json mbta_transit_graph.json
```

### Step 5: Restart Backend
```bash
cd ..
python3 main.py
```

**Expected output:**
```
✓ Loaded transit graph with 247 stations
✓ Dijkstra router initialized
```

### Step 6: Test
```bash
python3 debug_route.py ruggles "back bay"
```

**Expected result:**
- Orange Line: ~2 min travel + ~2.5 min wait = **4.5 min total**
- Walking: ~15-20 min
- **Should choose Orange Line** ✅

---

## What compute_edge_weights.py Does

### For Train Edges:
```python
# 1. Try to get actual travel time from MBTA API
travel_time = get_from_api(from_stop, to_stop, route)
# Typical: 90-180 seconds between stops

# 2. Add expected wait time (half the headway)
Subway headway: 5 min → wait: 2.5 min
Commuter rail headway: 30 min → wait: 15 min

# 3. Total edge weight
edge.time_seconds = travel_time + expected_wait

# Example: Red Line
#   Travel: 120 sec (2 min)
#   Wait: 150 sec (2.5 min)
#   Total: 270 sec (4.5 min)
```

### For Walk Edges:
```python
# Already have accurate OSRM times
# Just verify geometry is saved
# No wait time for walking!
```

---

## Expected Edge Weights After Fix

### Ruggles → Back Bay Example:

**Option 1: Orange Line (Direct)**
```
Edge weight = 120 sec (travel) + 150 sec (wait) = 270 sec (4.5 min)
```

**Option 2: Walk**
```
Edge weight = 1200 sec (20 min walk)
```

**Dijkstra chooses**: Orange Line (270 < 1200) ✅

### Copley → Back Bay Example:

**Option 1: Walk**
```
Edge weight = 240 sec (4 min)
```

**Option 2: Green to Transfer to Orange**
```
Walk to nearby Green: 60 sec
Wait for Green: 300 sec
Ride Green: 120 sec
Transfer walk: 120 sec
Wait for Orange: 150 sec
Ride Orange: 60 sec
Total: 810 sec (13.5 min)
```

**Dijkstra chooses**: Walk (240 < 810) ✅

---

## Why This Fixes Both Issues

### Issue 1: Walking Over-Preference ✅
**Before**:
- Train edges: 0 seconds (artificially fast)
- Walk edges: Actual time
- Result: Algorithm confused, defaults to walking

**After**:
- Train edges: travel_time + wait_time (realistic)
- Walk edges: Actual time
- Result: Algorithm correctly balances both options

### Issue 2: Straight Lines ✅
**Before**:
- OSRM called but geometry discarded
- Frontend draws straight line between stations

**After**:
- OSRM geometry saved in edge.geometry
- Frontend draws along actual streets

---

## Headway Values (Expected Wait Times)

| Route Type | Headway | Wait Time (avg) |
|------------|---------|-----------------|
| Subway (Red/Orange/Blue) | 5 min | 2.5 min |
| Light Rail (Green) | 10 min | 5 min |
| Commuter Rail | 30 min | 15 min |
| Bus | 15 min | 7.5 min |

These are used in `compute_edge_weights.py` to calculate expected wait times.

---

## Verification

### After Rebuild, Check:

1. **Walking edges have geometry**:
```bash
python3 << EOF
import json
with open('data/mbta_transit_graph.json') as f:
    graph = json.load(f)
walk = [e for e in graph['graph']['edges'] if e.get('type') == 'walk'][0]
print(f"Has geometry: {'geometry' in walk}")
print(f"Geometry points: {len(walk.get('geometry', []))}")
EOF
```

Expected: `Has geometry: True`, `Geometry points: 50+`

2. **Train edges have times**:
```bash
python3 << EOF
import json
with open('data/mbta_transit_graph.json') as f:
    graph = json.load(f)
train = [e for e in graph['graph']['edges'] if e.get('type') == 'train'][0]
print(f"Time: {train.get('time_seconds', 0)/60:.1f} min")
print(f"Travel: {train.get('travel_time_seconds', 0)/60:.1f} min")
print(f"Wait: {train.get('expected_wait_seconds', 0)/60:.1f} min")
EOF
```

Expected: All values > 0

3. **Ruggles → Back Bay chooses train**:
```bash
python3 debug_route.py ruggles "back bay"
```

Expected output:
```
✓ Path found!
  Total time: 4.5 minutes
  Segments: 1

Route details:
  1. TRAIN: Ruggles -> Back Bay
     Time: 4.5 min, Line: Orange Line
```

---

## Performance Impact

### Rebuild Time:
- `build_transit_graph.py`: ~10-15 min (OSRM calls for 242 walk edges)
- `compute_edge_weights.py`: ~5-10 min (MBTA API for 590 train edges)
- **Total: ~20-25 minutes one-time cost**

### Runtime Performance:
- **No change** - Dijkstra still runs in <10ms
- All computation done offline
- Graph loaded once on startup

---

## Alternative: Quick Fix (Estimates Only)

If you don't want to wait for API calls:

```bash
python3 compute_edge_weights.py --no-api
```

This uses:
- Estimated train times (2-3 min per stop)
- Standard headways
- No MBTA API calls

**Trade-off**: Less accurate but much faster (~30 seconds)

---

## Files Modified

1. **`backend/build_transit_graph.py`** ✅
   - Save OSRM geometry in walking edges
   - Return geometry from `calculate_walking_time()`

2. **`backend/compute_edge_weights.py`** ✅ NEW
   - Add train travel times + wait times
   - Query MBTA API or use estimates
   - Save weighted graph

3. **`backend/dijkstra_router.py`** ✅ Already done
   - Use `edge.time_seconds` for routing
   - Handle geometry display

---

## Summary

**Root Cause**: Graph had incomplete edge weights
- Train edges: 0 seconds (missing!)
- Walk edges: Accurate times + missing geometry

**Fix**: Complete rebuild with:
- Walking edges: OSRM times + geometry ✅
- Train edges: Travel time + wait time ✅

**Result**:
- Trains competitive with walking ✅
- Walking paths follow streets ✅
- Dijkstra finds optimal routes ✅

**Time Investment**: ~25 minutes rebuild (one-time)

**Performance**: No change (all offline computation)

---

## Next Steps

1. Run `build_transit_graph.py` (rebuild with geometry)
2. Run `compute_edge_weights.py` (add train weights)
3. Replace graph file
4. Restart backend
5. Test Ruggles → Back Bay (should use Orange Line)
6. Test Copley → Back Bay (should walk)

Both issues will be completely resolved! 🎉
