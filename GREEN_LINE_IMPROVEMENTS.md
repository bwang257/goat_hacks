# Green Line Branch Routing Improvements

## Problem Statement

The MBTA Green Line has 4 branches (B, C, D, E) that share a common trunk through downtown Boston but diverge at different points:

- **Trunk**: Government Center ↔ Kenmore (all branches)
- **Branch Points**:
  - B/C/D split at Kenmore
  - D/E split at Lechmere/Government Center

### Previous Behavior
Before improvements, the system treated each Green Line branch as completely separate routes:
- Blandford St (B) → Cleveland Circle (C) shown as:
  - ❌ "Green-B: Blandford → Kenmore"
  - ❌ "Transfer at Kenmore"
  - ❌ "Green-C: Kenmore → Cleveland Circle"

This was confusing because in reality, riders simply stay on the same Green Line platform and board a different branch - it's NOT a transfer in the traditional sense (no walking, no different platform).

### Real-World MBTA Behavior
- At Kenmore, all B, C, D trains use the same inbound/outbound platforms
- Riders can switch between branches by waiting for the next train on their desired branch
- This is more like "waiting for a specific bus route" than a transfer between different lines
- Google Maps and Apple Maps show this as a single Green Line journey with branch information

---

## Solution Implemented

### Backend Changes

#### 1. **Transfer Detection Logic** ([dijkstra_router.py:217-230](backend/dijkstra_router.py#L217-L230))

Added `is_same_line_family()` function to identify line families:

```python
def is_same_line_family(line1, line2):
    """Check if two lines are in the same family (e.g., Green Line branches)"""
    if line1 is None or line2 is None:
        return False
    # Green Line branches
    green_branches = {'B', 'C', 'D', 'E', 'Green-B', 'Green-C', 'Green-D', 'Green-E'}
    if line1 in green_branches and line2 in green_branches:
        return True
    # Otherwise, must match exactly
    return line1 == line2

is_transfer = (current_line is not None and not is_same_line_family(line_name, current_line))
```

**Result**: Green Line branch changes are NO LONGER counted as transfers.

---

### Frontend Changes

#### 2. **Line Normalization** ([src/App.tsx:122-135](src/App.tsx#L122-L135))

Added `normalizeLineName()` function to treat all Green branches as "Green":

```typescript
function normalizeLineName(line: string | undefined): string {
  if (!line) return '';

  // Green Line branches should all be treated as "Green"
  if (line === 'B' || line === 'C' || line === 'D' || line === 'E' ||
      line === 'Green-B' || line === 'Green-C' || line === 'Green-D' || line === 'Green-E') {
    return 'Green';
  }

  return line.replace(' Line', '').trim();
}
```

#### 3. **Segment Grouping** ([src/App.tsx:148-171](src/App.tsx#L148-L171))

Updated `groupSegmentsByLine()` to:
- Group consecutive Green Line segments together (even across branch changes)
- Skip showing "transfer" segments for Green Line branch changes at the same station
- Display all Green branches as one unified "Green Line" journey

```typescript
// Merge if same line (treating Green Line branches as one line)
if (lastGroup &&
    lastGroup.type === 'train' &&
    areLinesCompatible(lastGroup.line, seg.line)) {
  // Merge with previous group
  lastGroup.segments.push(seg);
  // ...

  // Update route_id to show branch info
  if (normalizeLineName(seg.line) === 'Green') {
    lastGroup.route_id = lastGroup.route_id + '→' + seg.route_id;
  }
}

// Don't show as transfer if it's just a Green Line branch change
if (lastGroup && lastGroup.type === 'train' &&
    normalizeLineName(lastGroup.line) === 'Green' &&
    next_seg.type === 'train' &&
    normalizeLineName(next_seg.line) === 'Green' &&
    seg.from_station_name === seg.to_station_name) {
  // Skip this transfer
  continue;
}
```

---

## Test Results

Ran comprehensive tests in [test_green_line.py](backend/test_green_line.py):

### Test 1: Green-B to Green-C (Blandford → Cleveland Circle)
```
✓ Route found!
  Total time: 18.5 minutes
  Transfers: 0  ✅ (was counting as 1 before)
  Segments: 8

  Route: Blandford (B) → Kenmore (B) → Fenway (D) → ... → Cleveland Circle
```

### Test 2: Green-B to Green-D (Blandford → Fenway)
```
✓ Route found!
  Total time: 3.6 minutes
  Transfers: 0  ✅ (was counting as 1 before)
  Segments: 2

  Route: Blandford (B) → Kenmore → Fenway (D)
```

### Test 3: Green-C to Green-E (Coolidge Corner → Heath Street)
```
✓ Route found!
  Total time: 21.9 minutes
  Transfers: 0  ✅
  Segments: 8

  Route uses shared trunk and branch changes
```

### Test 4: Green to Red (Kenmore → Harvard)
```
✓ Route found!
  Total time: 29.2 minutes
  Transfers: 1  ✅ (correctly identifies real transfer)
  Segments: 9

  Route: Kenmore (Green) → Park Street (Green) → Harvard (Red)
  Real transfer counted between Green and Red
```

**All tests passing!** ✅

---

## User Experience Improvements

### Before:
```
┌─────────────────────────────────────┐
│ [Green-B] Blandford → Kenmore       │
│ 2 stops                             │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🔄 Transfer at Kenmore              │
│ ⚠️ RISKY                            │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ [Green-C] Kenmore → Cleveland Circle│
│ 5 stops                             │
└─────────────────────────────────────┘

Total: 1 transfer (confusing!)
```

### After:
```
┌─────────────────────────────────────┐
│ [Green] Blandford → Cleveland Circle│
│ 7 stops (via Kenmore)               │
│ Route: Green-B → Green-C            │
└─────────────────────────────────────┘

Total: 0 transfers (accurate!)
```

---

## Technical Details

### Graph Structure
The MBTA station graph already had all necessary connections:

```
Kenmore (serves B, C, D):
  → Blandford Street (B)
  → Hynes Convention Center (B)
  → Saint Mary's Street (C)
  → Hynes Convention Center (C)
  → Fenway (D)
  → Hynes Convention Center (D)
```

Each branch has separate edges, so Dijkstra's algorithm could already find optimal paths across branches. The improvements were purely in **transfer counting** and **display grouping**.

### Why This Matters

1. **Accurate Transfer Counts**: Users make decisions based on transfer counts. Showing 0 transfers instead of 1 is more honest.

2. **Clearer Instructions**: "Take the Green Line from Blandford to Cleveland Circle" is much clearer than "Take Green-B to Kenmore, transfer to Green-C"

3. **Matches Real-World Experience**: Riders familiar with the T know that switching Green Line branches at Kenmore/Copley/etc. isn't a "transfer" in the usual sense.

4. **Consistency with Major Apps**: Google Maps and Apple Maps handle Green Line branches this way.

---

## Additional Benefits

### 1. Transfer Rating Accuracy
Since Green Line branch changes aren't counted as transfers, they don't get risky transfer warnings. This is correct - there's no timing risk when both branches use the same platform.

### 2. Alternative Route Suggestions
The system no longer suggests "safer alternatives" for routes that only involve Green Line branch changes.

### 3. Expandable Stop List
When users expand a grouped Green Line segment, they see:
```
[Green] Blandford → Cleveland Circle (7 stops) ▼
  ● Blandford Street
  ● Boston University East
  ● Kenmore (switch to C branch)
  ● Saint Mary's Street
  ● Hawes Street
  ● Cleveland Circle
```

---

## Future Enhancements

### Potential Improvements:
1. **Visual Branch Indicator**: Show "→C" when switching from B to C branch
2. **Wait Time Estimates**: If real-time data shows Green-C arrives in 2 min but Green-B in 30 sec, suggest taking B→Kenmore→C
3. **Peak Hour Intelligence**: During rush hour, some branches run more frequently
4. **Accessibility Notes**: Some Green Line platforms have different accessibility features

---

## Files Modified

### Backend:
- ✅ [backend/dijkstra_router.py](backend/dijkstra_router.py) - Transfer detection logic
- ✅ [backend/test_green_line.py](backend/test_green_line.py) - Comprehensive tests

### Frontend:
- ✅ [src/App.tsx](src/App.tsx) - Line normalization and segment grouping

### Build Status:
- ✅ TypeScript compilation successful
- ✅ Vite build successful (501ms)
- ✅ Backend tests passing
- ✅ No errors or warnings

---

## Summary

The Green Line routing improvements make the app more intuitive and accurate by:

1. **Not counting Green Line branch changes as transfers** (backend)
2. **Grouping all Green branches as "Green Line"** (frontend)
3. **Hiding unnecessary "transfer" segments** (frontend)
4. **Matching real-world MBTA behavior** (overall)

Users now see Green Line routes exactly as they would on Google Maps or Apple Maps, with clear, accurate information about their journey.

**Status: COMPLETE AND TESTED** ✅
