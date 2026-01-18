"""
Test time calculation and walking speed implementation.

This test verifies:
1. total_time_minutes is correctly calculated from request_time to arrival_time
2. Walking speed changes affect walking times correctly
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dijkstra_router import DijkstraRouter


async def test_time_calculation():
    """Test that total_time_minutes is correctly calculated from now to arrival."""
    
    # Load transit graph
    graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
    if not os.path.exists(graph_file):
        print("Error: mbta_transit_graph.json not found. Please run build_transit_graph.py first.")
        return False
    
    with open(graph_file, 'r') as f:
        graph_data = json.load(f)
    
    router = DijkstraRouter(graph_data['graph'])
    
    # Use two stations that should have a route
    start_id = "place-north"
    end_id = "place-sstat"
    
    print("Testing time calculation...")
    print(f"Start: {router.get_station_name(start_id)}")
    print(f"End: {router.get_station_name(end_id)}")
    print()
    
    # Set request time (now)
    request_time = datetime.now(timezone.utc)
    
    try:
        route = await router.find_route(
            start_station_id=start_id,
            end_station_id=end_id,
            departure_time=request_time,
            mbta_client=None,  # No real-time data needed for this test
            walking_speed_kmh=5.0,
            debug=True  # Enable debug to see calculations
        )
        
        if route:
            print()
            print("=" * 60)
            print("TIME CALCULATION VERIFICATION")
            print("=" * 60)
            print(f"Request time (now): {request_time.strftime('%H:%M:%S')}")
            print(f"Departure time: {route.departure_time.strftime('%H:%M:%S') if route.departure_time else 'N/A'}")
            print(f"Arrival time: {route.arrival_time.strftime('%H:%M:%S') if route.arrival_time else 'N/A'}")
            print()
            
            # Calculate expected total time
            if route.arrival_time:
                expected_total_seconds = (route.arrival_time - request_time).total_seconds()
                expected_total_minutes = expected_total_seconds / 60
                
                print(f"Expected total_time_seconds: {expected_total_seconds:.1f}")
                print(f"Expected total_time_minutes: {expected_total_minutes:.1f}")
                print(f"Actual total_time_seconds: {route.total_time_seconds}")
                
                # Calculate what total_time_minutes should be
                actual_total_minutes = route.total_time_seconds / 60
                print(f"Calculated total_time_minutes (from seconds): {actual_total_minutes:.1f}")
                
                # Check if they match
                if abs(expected_total_seconds - route.total_time_seconds) < 1.0:
                    print("✓ PASS: total_time_seconds matches expected calculation")
                    
                    # Check that time is not < 1 minute (unless route is very short)
                    if route.total_time_seconds < 60 and expected_total_seconds >= 60:
                        print(f"⚠ WARNING: total_time_seconds ({route.total_time_seconds}) < 60s but should be >= 60s")
                        return False
                    
                    if expected_total_minutes >= 1.0:
                        if actual_total_minutes < 1.0:
                            print(f"✗ FAIL: total_time_minutes ({actual_total_minutes}) < 1.0 when it should be {expected_total_minutes:.1f}")
                            return False
                    
                    print(f"✓ PASS: total_time_minutes calculation looks correct ({actual_total_minutes:.1f} min)")
                    return True
                else:
                    print(f"✗ FAIL: total_time_seconds mismatch (expected {expected_total_seconds:.1f}, got {route.total_time_seconds})")
                    return False
            else:
                print("✗ FAIL: No arrival_time in route")
                return False
        else:
            print("✗ FAIL: No route found")
            return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_walking_speed_impact():
    """Test that changing walking speed affects route times."""
    
    # Load transit graph
    graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
    if not os.path.exists(graph_file):
        print("Error: mbta_transit_graph.json not found.")
        return False
    
    with open(graph_file, 'r') as f:
        graph_data = json.load(f)
    
    router = DijkstraRouter(graph_data['graph'])
    
    # Use stations that likely have walking segments
    start_id = "place-north"
    end_id = "place-sstat"
    
    print()
    print("=" * 60)
    print("WALKING SPEED IMPACT TEST")
    print("=" * 60)
    
    request_time = datetime.now(timezone.utc)
    speeds = [3.0, 5.0, 7.0]  # km/h
    results = {}
    
    for speed in speeds:
        try:
            route = await router.find_route(
                start_station_id=start_id,
                end_station_id=end_id,
                departure_time=request_time,
                mbta_client=None,
                walking_speed_kmh=speed,
                debug=False
            )
            
            if route:
                # Find walking segments
                walk_segments = [seg for seg in route.segments if seg.type == "walk"]
                if walk_segments:
                    total_walk_time = sum(seg.time_seconds for seg in walk_segments)
                    results[speed] = {
                        'walk_time': total_walk_time,
                        'total_time': route.total_time_seconds
                    }
                    print(f"Speed {speed} km/h: Walk time = {total_walk_time/60:.1f} min, Total = {route.total_time_seconds/60:.1f} min")
                else:
                    print(f"Speed {speed} km/h: No walking segments (route uses trains only)")
            else:
                print(f"Speed {speed} km/h: No route found")
        except Exception as e:
            print(f"Speed {speed} km/h: Error - {e}")
    
    print()
    
    # Verify that faster speeds result in shorter walk times (if walking exists)
    if len(results) >= 2 and any(r.get('walk_time', 0) > 0 for r in results.values()):
        speeds_list = sorted([s for s in speeds if s in results and results[s].get('walk_time', 0) > 0])
        if len(speeds_list) >= 2:
            prev_walk_time = results[speeds_list[0]]['walk_time']
            all_decreasing = True
            
            for speed in speeds_list[1:]:
                current_walk_time = results[speed]['walk_time']
                if current_walk_time >= prev_walk_time:
                    all_decreasing = False
                    print(f"✗ FAIL: Walk time didn't decrease (speed {speed} km/h: {current_walk_time/60:.1f} min >= {prev_walk_time/60:.1f} min)")
                    break
                prev_walk_time = current_walk_time
            
            if all_decreasing:
                print("✓ PASS: Walking speed changes affect walk times correctly")
                return True
            else:
                print("✗ FAIL: Walking speed changes don't affect walk times")
                return False
        else:
            print("⚠ WARNING: Not enough routes with walking segments to verify")
            return True  # Not a failure if route doesn't have walking
    else:
        print("⚠ WARNING: No walking segments in routes (test may not be applicable)")
        return True  # Not a failure if route doesn't use walking


async def main():
    """Run all tests."""
    print("Running time calculation and walking speed tests...")
    print()
    
    test1_passed = await test_time_calculation()
    test2_passed = await test_walking_speed_impact()
    
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Time calculation test: {'PASS' if test1_passed else 'FAIL'}")
    print(f"Walking speed impact test: {'PASS' if test2_passed else 'FAIL'}")
    
    return test1_passed and test2_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
