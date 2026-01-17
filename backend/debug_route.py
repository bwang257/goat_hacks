"""
Debug routing to see why nearby stations don't suggest walking
"""
import asyncio
import json
from route_planner import TransitGraph
from mbta_client import MBTAClient
import os

async def debug_route(start_name: str, end_name: str):
    """Debug a specific route to see what's happening"""

    # Load data
    with open("data/mbta_stations.json") as f:
        stations_data = json.load(f)

    stations = stations_data["stations"]

    # Find stations
    start = next((s for s in stations if start_name.lower() in s["name"].lower()), None)
    end = next((s for s in stations if end_name.lower() in s["name"].lower()), None)

    if not start or not end:
        print(f"Could not find stations: {start_name}, {end_name}")
        return

    print("=" * 70)
    print(f"DEBUGGING ROUTE: {start['name']} -> {end['name']}")
    print("=" * 70)
    print()
    print(f"Start: {start['name']}")
    print(f"  ID: {start['id']}")
    print(f"  Lines: {start['lines']}")
    print(f"  Location: ({start['latitude']:.5f}, {start['longitude']:.5f})")
    print()
    print(f"End: {end['name']}")
    print(f"  ID: {end['id']}")
    print(f"  Lines: {end['lines']}")
    print(f"  Location: ({end['latitude']:.5f}, {end['longitude']:.5f})")
    print()

    # Calculate direct distance
    import math
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad)*math.cos(lat2_rad)*math.sin(delta_lon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    distance = haversine(start['latitude'], start['longitude'], end['latitude'], end['longitude'])
    walk_time_estimate = distance / 1.4 / 60  # 1.4 m/s walking speed, convert to minutes

    print(f"Direct Distance: {distance:.0f}m ({walk_time_estimate:.1f} min walk)")
    print()

    # Load graph
    graph = TransitGraph("data/mbta_transit_graph.json")

    # Check for walking edge
    print("-" * 70)
    print("CHECKING FOR WALKING EDGE:")
    print("-" * 70)

    walking_edge = None
    for edge in graph.adjacency.get(start['id'], []):
        if edge.get("type") == "walk" and edge["to"] == end['id']:
            walking_edge = edge
            break

    if walking_edge:
        walk_time = walking_edge.get("time_seconds", 0) / 60
        walk_dist = walking_edge.get("distance_meters", 0)
        print(f"✓ Walking edge EXISTS in graph!")
        print(f"  Time: {walk_time:.1f} minutes")
        print(f"  Distance: {walk_dist:.0f}m")
        print()
    else:
        print(f"✗ NO walking edge in graph")
        print(f"  This means the graph builder didn't add this connection")
        print(f"  Stations may be too far apart (> threshold)")
        print()

    # Try to find a route
    print("-" * 70)
    print("FINDING ROUTE (with debug=True):")
    print("-" * 70)

    api_key = os.environ.get("MBTA_API_KEY")
    if not api_key:
        print("No MBTA_API_KEY found - using static routing only")
        route = graph.find_shortest_path(
            start['id'],
            end['id'],
            prefer_fewer_transfers=True,
            debug=True
        )
    else:
        print("Using time-aware routing with MBTA API...")
        mbta_client = MBTAClient(api_key)
        route = await graph.find_time_aware_path(
            start['id'],
            end['id'],
            mbta_client=mbta_client,
            prefer_fewer_transfers=True,
            debug=True
        )

    print()
    print("-" * 70)
    print("RESULT:")
    print("-" * 70)

    if route:
        print(f"✓ Route found!")
        print(f"  Total time: {route.total_time_seconds/60:.1f} minutes")
        print(f"  Transfers: {route.num_transfers}")
        print(f"  Segments: {len(route.segments)}")
        print()
        print("Route details:")
        for i, seg in enumerate(route.segments, 1):
            seg_time = seg.time_seconds / 60
            print(f"  {i}. {seg.type.upper()}: {graph.get_station_name(seg.from_station)} -> {graph.get_station_name(seg.to_station)}")
            print(f"     Time: {seg_time:.1f} min, Line: {seg.line or 'N/A'}")

        print()
        if walking_edge and route.segments[0].type != "walk":
            print("⚠ WARNING: Walking edge exists but route doesn't use it!")
            print(f"   Walk time: {walking_edge['time_seconds']/60:.1f} min")
            print(f"   Route time: {route.total_time_seconds/60:.1f} min")
            print(f"   The algorithm SHOULD have chosen walking!")
    else:
        print(f"✗ No route found")

    print()

async def main():
    import sys

    if len(sys.argv) != 3:
        print("Usage: python debug_route.py <start_station> <end_station>")
        print()
        print("Examples:")
        print("  python debug_route.py copley 'back bay'")
        print("  python debug_route.py boylston chinatown")
        print("  python debug_route.py harvard central")
        return

    await debug_route(sys.argv[1], sys.argv[2])

if __name__ == "__main__":
    asyncio.run(main())
