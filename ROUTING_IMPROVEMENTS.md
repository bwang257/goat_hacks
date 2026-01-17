# Route Finding Improvements Plan

## Current Issues

### 1. **Strange/Roundabout Routes**
The routing algorithm doesn't properly prioritize direct routes over complex multi-transfer routes.

### 2. **Key Problems:**

#### A. No Geographic Heuristic (A* Improvement Needed)
- Currently uses Dijkstra-style search without geographic awareness
- Should add haversine distance heuristic to prioritize paths moving toward destination
- This will explore direct paths before roundabout ones

#### B. Walking Logic Issues
**Current code (route_planner.py:277-280):**
```python
if serves_trains and edge_type == "walk":
    walk_time = edge.get("time_seconds", 0)
    if walk_time > 300:  # Only blocks >5 min walks
        continue
```

**Problems:**
- Allows short walks even when unnecessary
- Should check: "Am I already on the right line to my destination?"
- Should NEVER suggest walking between adjacent stations on the same line

#### C. Weak Transfer Penalties
- Transfer penalties only affect sort order, not actual pruning
- Should heavily penalize transfers when direct routes exist

#### D. Multi-Route Planner Too Naive
- Uses first transfer station found, not optimal one
- Doesn't calculate actual walking distances between platforms
- No consideration of transfer station quality (Downtown Crossing vs far stations)

## Proposed Solutions

### Solution 1: Add A* Heuristic (HIGH PRIORITY)
Add geographic distance heuristic to guide search toward destination.

**Implementation:**
```python
def haversine_distance(lat1, lon1, lat2, lon2):
    # Calculate distance in meters
    R = 6371000
    # ... standard haversine formula

# In pathfinding loop:
priority = current_time + heuristic_to_destination(next_station, end_station)
```

**Benefits:**
- Explores geographically closer stations first
- Prevents exploring routes going away from destination
- Dramatically reduces strange roundabout routing

### Solution 2: Improve Walking Prevention Logic

**Rules to add:**
1. **Never walk between adjacent stations on the same line**
   - Check if destination is reachable by staying on current train
   - Block walking edges if answer is yes

2. **Prefer trains over walking for medium distances (>500m)**
   - Even if walk is 5 min, prefer train if available

3. **Only allow walking for:**
   - Station-to-station transfers between different lines
   - Last-mile connections when no train option exists
   - Short distances (<300m) when it saves significant time

### Solution 3: Smarter Transfer Selection

**For multi-route planner:**
1. Find ALL transfer stations between routes
2. Score each by:
   - Geographic optimality (how far out of the way)
   - Transfer time (walking distance between platforms)
   - Service frequency (more trains = better)
3. Try transfers in order of best score

### Solution 4: Add Route Validation

**Before returning route, validate:**
- No walking between consecutive stations on same line
- Transfers only at genuine transfer stations
- No backtracking (going past destination then returning)
- Total time is reasonable vs direct distance

## Implementation Priority

1. **CRITICAL**: Add A* heuristic (80% of the problem)
2. **HIGH**: Improve walking prevention logic
3. **MEDIUM**: Smarter transfer station selection
4. **LOW**: Route validation (catches edge cases)

## Example Scenarios to Test

### Test 1: Adjacent Stations on Same Line
- From: Harvard (Red) → To: Central (Red)
- Expected: Take Red Line (1 stop)
- Bad Result: Walk (if it suggests this, it's broken)

### Test 2: Transfer Required
- From: Harvard (Red) → To: State (Orange)
- Expected: Red to Park/DTX → Transfer → Orange to State
- Bad Result: Any route with >1 transfer, or walking long distances

### Test 3: Short Distance but Different Lines
- From: Government Center (Green/Blue) → To: State (Orange/Blue)
- Expected: Blue Line (1 stop)
- Bad Result: Walking or roundabout Green→Red→Orange path

### Test 4: Geographic Trap
- From: Airport (Blue) → To: Wonderland (Blue)
- Expected: Blue Line (direct)
- Bad Result: Transfer to another line then back to Blue

## Code Files to Modify

1. **backend/route_planner.py**
   - Add haversine heuristic function
   - Modify priority calculation in `find_time_aware_path`
   - Improve walking prevention logic (lines 272-280)
   - Add geographic validation

2. **backend/multi_route_planner.py**
   - Improve `_find_transfer_station` to return ranked list
   - Add transfer station scoring
   - Consider walking distances between platforms

3. **Testing**
   - Create test cases for common routes
   - Log actual routes being suggested
   - Compare against common sense
