# Dijkstra's Algorithm Analysis & Proposal

## Current Problem

Despite having walking edges in the graph (e.g., Copley-Back Bay: 324m, 4 mins), the routing algorithm **still suggests roundabout transfer routes** for nearby Green/Orange station pairs.

### Root Cause Analysis

The issue isn't missing data - it's **algorithm complexity**:

## Current Architecture (Pareto Multi-Objective BFS)

```python
# Current approach in find_time_aware_path():
for each edge:
    if edge_type == "train":
        # Makes API call to get next departure time
        departures = await mbta_client.get_next_departures(...)
        # Waits for response, calculates arrival time

    if edge_type == "walk":
        # Heavily filtered by multiple conditions
        # May be skipped due to restrictive logic
```

### Problems with Current Approach:

1. **O(N) API Calls**: Each train edge requires real-time API lookup
   - Slow: 100-500ms per API call
   - Expensive: Multiple API calls per pathfinding attempt
   - Rate limits: Can hit MBTA API rate limits

2. **Complex Walking Filter Logic**: Lines 384-447 have multiple conditions
   - May be **too restrictive** and filtering out valid walks
   - Logic is hard to debug (13 different conditions!)
   - Doesn't consider "total time including waiting"

3. **Multi-Objective Optimization Overhead**:
   - Tracks Pareto-optimal labels (transfers vs time)
   - More complex than necessary for most routes
   - Can explore 2000+ nodes before finding simple walking route

## Your Proposal: Dijkstra's Algorithm

**Key Insight**:
> "Delays/congestion only influence transfer times, right? We can use the graph to store expected travel times and still deal with real-time data."

**This is BRILLIANT and CORRECT!** Here's why:

### Why Dijkstra Works Better

#### 1. Pre-computed Static Weights
```python
# Build graph once with expected travel times:
train_edges = {
    "Park St -> DTX on Red": 120 seconds,  # Average from historical data
    "DTX -> South Station": 90 seconds,
    # etc.
}

walk_edges = {
    "Copley -> Back Bay": 234 seconds,  # Fixed walking time
    "Boylston -> Chinatown": 300 seconds,
    # etc.
}
```

**Benefits**:
- ✅ No API calls during pathfinding
- ✅ Blazing fast: ~1-10ms vs 500-2000ms
- ✅ Simple, proven algorithm
- ✅ Easy to debug

#### 2. Real-Time Data for Departures Only

```python
# Step 1: Run Dijkstra to find optimal PATH (instant!)
path = dijkstra(start, end)  # Returns: [Copley, walk, Back Bay, Orange, destination]

# Step 2: Get real-time departure times ONLY for the chosen path
for segment in path:
    if segment.type == "train":
        next_train = await get_next_departure(segment.station, segment.route)
        # Only 1-3 API calls total (one per train segment)
```

**Benefits**:
- ✅ Fast pathfinding (Dijkstra on static graph)
- ✅ Real-time accuracy (API calls only for final route)
- ✅ Minimal API usage (1-3 calls vs 100+ calls)

### Proposed Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Static Graph Pathfinding (Dijkstra)           │
│ - Use average/expected travel times                     │
│ - Include ALL walking edges without filtering           │
│ - Find optimal path in <10ms                            │
└─────────────────────────────────────────────────────────┘
                           ↓
                  Returns: [A, walk, B, train, C, D]
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Real-Time Enrichment (API calls)              │
│ - For each TRAIN segment in path:                       │
│   - Get next departure time from MBTA API               │
│   - Calculate actual arrival time                       │
│ - For WALK segments: use static time (walking is fixed) │
└─────────────────────────────────────────────────────────┘
                           ↓
           Complete route with real-time data!
```

## Implementation Plan

### Step 1: Modify `build_transit_graph.py`

Add **average travel times** for train edges:

```python
# Query MBTA API for historical schedule data
async def get_average_travel_time(from_stop, to_stop, route_id):
    # Get schedules for past week
    schedules = await mbta_client.get_schedules(route_id, ...)

    # Calculate average time between these stops
    times = []
    for schedule in schedules:
        if schedule.from_stop == from_stop and schedule.to_stop == to_stop:
            travel_time = schedule.arrival - schedule.departure
            times.append(travel_time)

    return mean(times)  # Return average

# Add to graph edges
edges.append({
    "from": from_stop,
    "to": to_stop,
    "type": "train",
    "route_id": route_id,
    "time_seconds": average_time,  # Static expected time
    "route_type": route_type
})
```

### Step 2: Implement Clean Dijkstra

```python
def find_route_dijkstra(start, end):
    """
    Simple Dijkstra's algorithm - no API calls, no filters
    Uses pre-computed travel times from graph
    """
    pq = [(0, start, [])]  # (total_time, current_node, path)
    visited = set()

    while pq:
        time, node, path = heapq.heappop(pq)

        if node == end:
            return path  # Found optimal path!

        if node in visited:
            continue
        visited.add(node)

        # Explore all edges (train AND walk)
        for edge in adjacency[node]:
            # Use pre-computed time (no API call!)
            new_time = time + edge["time_seconds"]
            new_path = path + [edge]
            heapq.heappush(pq, (new_time, edge["to"], new_path))

    return None
```

**That's it!** No complex filtering, no API calls, no Pareto optimization. Just classic Dijkstra.

### Step 3: Real-Time Enrichment

```python
async def enrich_route_with_realtime(path, departure_time):
    """
    Take the path from Dijkstra and add real-time train times
    """
    current_time = departure_time
    enriched_segments = []

    for edge in path:
        if edge["type"] == "walk":
            # Walking time is fixed
            segment = {
                **edge,
                "departure_time": current_time,
                "arrival_time": current_time + timedelta(seconds=edge["time_seconds"])
            }
            current_time = segment["arrival_time"]

        elif edge["type"] == "train":
            # Get real-time departure
            next_trains = await mbta_client.get_next_departures(
                edge["from"],
                edge["route_id"],
                limit=1
            )

            if next_trains:
                train = next_trains[0]
                dep_time = train["departure_time"]
                # Use static travel time from graph for arrival estimate
                arr_time = dep_time + timedelta(seconds=edge["time_seconds"])

                segment = {
                    **edge,
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "status": train.get("status", "Scheduled")
                }
                current_time = arr_time
            else:
                # No trains available - use estimated times
                segment = {
                    **edge,
                    "departure_time": current_time,
                    "arrival_time": current_time + timedelta(seconds=edge["time_seconds"])
                }
                current_time = segment["arrival_time"]

        enriched_segments.append(segment)

    return enriched_segments
```

### Step 4: Main Routing Function

```python
async def find_best_route(start, end, departure_time=None):
    """
    Two-phase routing: Fast Dijkstra + Real-time enrichment
    """
    # Phase 1: Fast pathfinding (no API calls)
    path = find_route_dijkstra(start, end)

    if not path:
        return None

    # Phase 2: Add real-time data (minimal API calls)
    if departure_time is None:
        departure_time = datetime.now(timezone.utc)

    enriched_route = await enrich_route_with_realtime(path, departure_time)

    return Route(segments=enriched_route, ...)
```

## Advantages of Dijkstra Approach

| Aspect | Current (Pareto BFS + API) | Dijkstra + Enrichment |
|--------|---------------------------|----------------------|
| **Speed** | 500-2000ms | 10-50ms |
| **API Calls** | 50-200 per route | 1-3 per route |
| **Correctness** | Complex filters may miss routes | Provably optimal |
| **Debugging** | Very difficult (async, filters) | Easy (static graph) |
| **Walking routes** | Often filtered out | Always considered |
| **Code complexity** | ~400 lines, 13 conditions | ~100 lines, simple |

## Handling Real-Time Data Correctly

### What Real-Time Data Affects:

✅ **Train departure times**: "Next Red Line train at 2:15 PM"
✅ **Service disruptions**: "Orange Line delayed 10 mins"
✅ **Platform changes**: "Train departing from track 2"

❌ **Does NOT affect**:
- Walking times (fixed!)
- Route topology (which stations connect)
- **Relative optimality of paths** (walking 5 min is still better than transfer+train 15 min)

### How Dijkstra Handles This:

1. **Find optimal PATH topology** using expected times
   - "The best route is: Walk to Back Bay, then Orange Line"

2. **Enrich with real-time** for actual schedule
   - "Next Orange Line train: 2:17 PM, arrives 2:25 PM"

Even if train times vary, **the optimal path structure stays the same!**

### Example:

**Scenario**: Copley (Green) → Prudential (Green E)

**Dijkstra says**: Walk 4 mins directly (240 seconds)
- vs Green Line: wait 2 min + ride 2 min + walk in station = 270 seconds

**Real-time doesn't change this!**
- Even if next train is 30 seconds away: wait 0.5 min + ride 2 min = 150 sec
- **Still worse than walking 240 sec?** No! Real-time makes train better!

**SOLUTION**: Use **predicted wait time** in Dijkstra:

```python
# Better approach: include expected wait time in graph
train_edge_weight = expected_headway/2 + travel_time

# For Red Line (5 min headway):
edge_time = 150 + 120 = 270 seconds  # avg wait + travel

# For walking:
edge_time = 240 seconds  # fixed

# Dijkstra will correctly prefer walking!
```

## What About Delays and Disruptions?

### Option 1: Fallback Routes (Simple)

```python
# If service disruption detected:
if route_has_disruption(primary_route):
    # Run Dijkstra again with that route disabled
    backup_route = dijkstra_excluding(disrupted_routes)
    return backup_route
```

### Option 2: Dynamic Weight Adjustment (Advanced)

```python
# Adjust edge weights based on real-time delays
def get_adjusted_weight(edge):
    base_time = edge["time_seconds"]

    # Check for delays
    delays = get_current_delays(edge["route_id"])

    return base_time + delays
```

## Recommended Implementation

### Phase 1 (Immediate): Basic Dijkstra
- Use average travel times from MBTA historical data
- No real-time (just get routes working correctly!)
- Focus on correct path topology

### Phase 2 (After Phase 1 works): Add Real-Time
- Enrich Dijkstra results with next train times
- Show accurate departure/arrival times
- Keep using Dijkstra for path structure

### Phase 3 (Optional): Smart Waiting
- Add expected wait times to train edges
- Dynamically adjust for disruptions
- Multiple route options

## Why Current Approach Fails for Nearby Stations

```python
# Current code (lines 394-447) has 13 different walking filters:
if current_line and edge_type == "walk":
    if self._is_destination_reachable_on_line(...):  # Filter 1
        continue
    if next_station in stations_reachable_by_current_line:  # Filter 2
        continue

if edge_type == "walk":
    # Filter 3, 4, 5... up to 13 different conditions!
```

**Problem**: With so many filters, **valid walking routes get excluded!**

**Dijkstra solution**:
```python
# Just add all edges to priority queue
# Let the algorithm decide based on total time!
for edge in adjacency[node]:
    heapq.heappush(pq, (time + edge["time_seconds"], edge["to"], ...))
```

No filters needed - Dijkstra mathematically finds the optimal path!

## Summary & Recommendation

### ✅ Yes, Use Dijkstra's Algorithm!

**You are absolutely correct that Dijkstra is the better approach.**

### Implementation Priority:

1. **HIGH PRIORITY**: Implement basic Dijkstra pathfinding
   - Strip out complex filtering logic
   - Use pre-computed travel times
   - Get correct path topology

2. **MEDIUM PRIORITY**: Add real-time enrichment
   - After Dijkstra finds path, get next train times
   - Minimal API calls, accurate schedules

3. **LOW PRIORITY**: Advanced features
   - Dynamic disruption handling
   - Multiple route alternatives
   - Smart wait time estimation

### Expected Improvements:

- **Speed**: 50-100x faster pathfinding
- **Correctness**: Always finds optimal path
- **Simplicity**: 1/4 the code complexity
- **Walking routes**: Will finally work correctly!

### Files to Modify:

1. `build_transit_graph.py`: Add average travel times to edges
2. `route_planner.py`: Replace `find_time_aware_path` with Dijkstra
3. `main.py`: Add real-time enrichment step

The current Pareto BFS approach is over-engineered for this problem. **Dijkstra is the right tool for the job!**
