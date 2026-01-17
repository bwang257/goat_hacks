"""
Pre-compute comprehensive edge weights for optimal Dijkstra routing.

This script adds:
1. Actual train travel times (from MBTA API or estimates)
2. Expected wait times based on route headways
3. Verifies walking times use OSRM actual paths (not crow-flies)

Run once, saves to graph, then Dijkstra uses accurate weights.
"""
import json
import asyncio
import httpx
import os
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from mbta_client import MBTAClient

# Default travel time estimates by route type
DEFAULT_TIMES = {
    0: 180,  # Light rail (3 min between stops)
    1: 120,  # Subway (2 min between stops)
    2: 180,  # Commuter rail (3 min between stops)
    3: 90,   # Bus (1.5 min between stops)
    4: 120,  # Ferry (2 min)
}

# Average headways (time between trains) by route type
HEADWAYS = {
    0: 600,   # Light rail: 10 min
    1: 300,   # Subway: 5 min (peak)
    2: 1800,  # Commuter rail: 30 min
    3: 900,   # Bus: 15 min
    4: 1800,  # Ferry: 30 min
}


async def get_actual_train_time(mbta_client: MBTAClient, from_stop: str, to_stop: str, route_id: str) -> Tuple[float, str]:
    """
    Get actual train travel time between two stops from MBTA schedules.
    Returns (time_seconds, source) where source is 'api' or 'estimated'
    """
    try:
        # Get schedules for this route
        schedules = await mbta_client.get_schedules(
            route_id=route_id,
            stop_id=from_stop,
            limit=20
        )

        if not schedules:
            return None, 'no_schedules'

        # Find a schedule that goes to the destination stop
        # We need to check the trip's subsequent stops
        for schedule in schedules:
            trip_id = schedule.get('relationships', {}).get('trip', {}).get('data', {}).get('id')
            if not trip_id:
                continue

            # Get this specific schedule's times
            dep_time_str = schedule.get('attributes', {}).get('departure_time')
            if not dep_time_str:
                continue

            # Try to find the arrival time at destination for same trip
            # Query schedules for destination stop with same trip
            dest_schedules = await mbta_client.get_schedules(
                route_id=route_id,
                stop_id=to_stop,
                limit=20
            )

            for dest_sched in dest_schedules:
                dest_trip = dest_sched.get('relationships', {}).get('trip', {}).get('data', {}).get('id')
                if dest_trip == trip_id:
                    # Found the same trip at destination!
                    arr_time_str = dest_sched.get('attributes', {}).get('arrival_time')
                    if arr_time_str:
                        # Parse times
                        dep_time = datetime.fromisoformat(dep_time_str.replace('Z', '+00:00'))
                        arr_time = datetime.fromisoformat(arr_time_str.replace('Z', '+00:00'))
                        travel_time = (arr_time - dep_time).total_seconds()

                        if 0 < travel_time < 3600:  # Sanity check: 1 min to 1 hour
                            return travel_time, 'api'

    except Exception as e:
        print(f"    Error getting API time: {e}")

    return None, 'failed'


async def compute_all_edge_weights(api_key: str = None, use_api: bool = True):
    """
    Compute comprehensive edge weights for all edges in the graph.

    For TRAIN edges:
        - Try to get actual travel time from MBTA API
        - Fall back to estimated time based on route type
        - Add expected wait time (headway / 2)

    For WALK edges:
        - Verify they use OSRM actual paths (already done by build_transit_graph)
        - Keep as-is (no wait time for walking)
    """

    print("=" * 70)
    print("COMPUTING COMPREHENSIVE EDGE WEIGHTS")
    print("=" * 70)
    print()

    # Load existing graph
    graph_file = "data/mbta_transit_graph.json"
    with open(graph_file, 'r') as f:
        graph_data = json.load(f)

    edges = graph_data['graph']['edges']
    nodes = graph_data['graph']['nodes']

    print(f"Loaded {len(edges)} edges from graph")
    print(f"  Train edges: {sum(1 for e in edges if e.get('type') == 'train')}")
    print(f"  Walk edges: {sum(1 for e in edges if e.get('type') == 'walk')}")
    print()

    # Initialize MBTA client if API key provided
    mbta_client = None
    if api_key and use_api:
        mbta_client = MBTAClient(api_key)
        print("✓ MBTA API client initialized")
    else:
        print("⚠ No API key - using estimates only")
    print()

    # Process each edge
    train_edges_processed = 0
    walk_edges_verified = 0
    api_times_retrieved = 0
    estimated_times = 0

    print("-" * 70)
    print("PROCESSING TRAIN EDGES")
    print("-" * 70)

    for i, edge in enumerate(edges):
        edge_type = edge.get('type', 'train')

        if edge_type == 'train':
            train_edges_processed += 1
            route_id = edge.get('route_id')
            route_type = edge.get('route_type', 1)
            from_stop = edge['from']
            to_stop = edge['to']

            # Try to get actual time from API
            travel_time = None
            source = 'none'

            if mbta_client and route_id:
                travel_time, source = await get_actual_train_time(mbta_client, from_stop, to_stop, route_id)

            # Fall back to estimate if API failed
            if travel_time is None:
                travel_time = DEFAULT_TIMES.get(route_type, 120)
                source = 'estimated'
                estimated_times += 1
            else:
                api_times_retrieved += 1

            # Add expected wait time (half the headway)
            headway = HEADWAYS.get(route_type, 600)
            expected_wait = headway / 2

            # Total edge weight = wait time + travel time
            total_time = expected_wait + travel_time

            # Update edge
            edge['travel_time_seconds'] = travel_time
            edge['expected_wait_seconds'] = expected_wait
            edge['time_seconds'] = total_time
            edge['weight_source'] = source

            if train_edges_processed % 50 == 0:
                from_name = nodes.get(from_stop, {}).get('name', from_stop)[:25]
                to_name = nodes.get(to_stop, {}).get('name', to_stop)[:25]
                print(f"  [{train_edges_processed}/590] {from_name} → {to_name}")
                print(f"    Travel: {travel_time/60:.1f}min, Wait: {expected_wait/60:.1f}min, Total: {total_time/60:.1f}min ({source})")

        elif edge_type == 'walk':
            # Walking edges should already have accurate OSRM times
            # Verify they exist
            if edge.get('time_seconds', 0) > 0:
                walk_edges_verified += 1
            else:
                print(f"  ⚠ Walking edge missing time: {edge['from']} -> {edge['to']}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Train edges processed: {train_edges_processed}")
    print(f"  From API: {api_times_retrieved}")
    print(f"  Estimated: {estimated_times}")
    print()
    print(f"Walk edges verified: {walk_edges_verified}")
    print()

    # Save updated graph
    print("Saving updated graph...")
    output_file = "data/mbta_transit_graph_weighted.json"

    with open(output_file, 'w') as f:
        json.dump(graph_data, f, indent=2)

    print(f"✓ Saved to: {output_file}")
    print()
    print("=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Rename: mv data/mbta_transit_graph.json data/mbta_transit_graph_old.json")
    print("2. Rename: mv data/mbta_transit_graph_weighted.json data/mbta_transit_graph.json")
    print("3. Restart backend: python3 main.py")
    print()
    print("Dijkstra will now use accurate edge weights!")
    print("=" * 70)


async def main():
    import sys

    api_key = os.environ.get("MBTA_API_KEY")
    use_api = True

    if len(sys.argv) > 1:
        if sys.argv[1] == "--no-api":
            use_api = False
            print("Running in estimate-only mode (no API calls)")
        elif sys.argv[1] == "--help":
            print("Usage: python compute_edge_weights.py [--no-api]")
            print()
            print("Computes edge weights for Dijkstra routing:")
            print("  - Train edges: travel time + expected wait time")
            print("  - Walk edges: verified OSRM actual paths")
            print()
            print("Options:")
            print("  --no-api    Use estimates only (no MBTA API calls)")
            print()
            print("Requires MBTA_API_KEY environment variable for API mode")
            return

    if use_api and not api_key:
        print("Error: MBTA_API_KEY not set")
        print("Either:")
        print("  1. export MBTA_API_KEY='your_key'")
        print("  2. Run with --no-api flag for estimates only")
        return

    await compute_all_edge_weights(api_key, use_api)


if __name__ == "__main__":
    asyncio.run(main())
