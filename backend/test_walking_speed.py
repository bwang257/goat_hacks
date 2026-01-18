"""
Test walking speed calculations in route planning.

This test verifies that walking times are correctly recalculated
based on user's walking speed preference.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dijkstra_router import DijkstraRouter
import json


async def test_walking_speed():
    """Test that walking times change with different speeds."""
    
    # Load transit graph
    graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
    if not os.path.exists(graph_file):
        print("Error: mbta_transit_graph.json not found. Please run build_transit_graph.py first.")
        return False
    
    with open(graph_file, 'r') as f:
        graph_data = json.load(f)
    
    router = DijkstraRouter(graph_data['graph'])
    
    # Test with two stations that are walkable
    # Use stations that are known to have walking paths in the graph
    # For this test, we'll use two nearby stations
    # You may need to adjust these station IDs based on your actual graph
    start_id = "place-north"
    end_id = "place-sstat"
    
    print("Testing walking speed calculations...")
    print(f"Start: {router.get_station_name(start_id)}")
    print(f"End: {router.get_station_name(end_id)}")
    print()
    
    # Test different walking speeds
    speeds = [3.0, 5.0, 7.0]  # km/h
    results = {}
    
    for speed in speeds:
        try:
            route = await router.find_route(
                start_station_id=start_id,
                end_station_id=end_id,
                departure_time=datetime.now(timezone.utc),
                mbta_client=None,  # No real-time data needed for this test
                walking_speed_kmh=speed,
                debug=False
            )
            
            if route:
                # Find walking segments
                walk_segments = [seg for seg in route.segments if seg.type == "walk"]
                if walk_segments:
                    total_walk_time = sum(seg.time_seconds for seg in walk_segments)
                    results[speed] = total_walk_time
                    print(f"Speed: {speed} km/h -> Walking time: {total_walk_time/60:.1f} min")
                else:
                    print(f"Speed: {speed} km/h -> No walking segments in route")
            else:
                print(f"Speed: {speed} km/h -> No route found")
        except Exception as e:
            print(f"Speed: {speed} km/h -> Error: {e}")
    
    print()
    
    # Verify that faster speeds result in shorter times
    if len(results) >= 2:
        speeds_list = sorted(results.keys())
        prev_time = results[speeds_list[0]]
        all_decreasing = True
        
        for speed in speeds_list[1:]:
            current_time = results[speed]
            if current_time >= prev_time:
                all_decreasing = False
                print(f"ERROR: Time increased from {prev_time/60:.1f} min to {current_time/60:.1f} min")
                break
            prev_time = current_time
        
        if all_decreasing:
            print("✓ PASS: Faster speeds result in shorter walking times")
            return True
        else:
            print("✗ FAIL: Walking times do not decrease with faster speeds")
            return False
    else:
        print("WARNING: Not enough results to verify speed impact")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_walking_speed())
    sys.exit(0 if success else 1)
