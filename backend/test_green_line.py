#!/usr/bin/env python3
"""
Test script for Green Line routing improvements.
Tests that Green Line branch transfers are handled correctly.
"""

import asyncio
import json
from datetime import datetime
from dijkstra_router import DijkstraRouter
from mbta_client import MBTAClient
import os

async def test_green_line_routing():
    """Test various Green Line routing scenarios"""

    print("="*80)
    print("GREEN LINE ROUTING TEST")
    print("="*80)
    print()

    # Load graph
    with open('./data/mbta_transit_graph.json', 'r') as f:
        data = json.load(f)

    router = DijkstraRouter(data['graph'])
    api_key = os.getenv('MBTA_API_KEY')
    mbta_client = MBTAClient(api_key) if api_key else None

    if not mbta_client:
        print("⚠️  Warning: No MBTA_API_KEY set - using static times only")
        print()

    # Test scenarios
    scenarios = [
        {
            "name": "Green-B to Green-C (branch transfer at Kenmore)",
            "from": "place-bland",  # Blandford Street (B)
            "to": "place-clmnl",    # Cleveland Circle (C)
            "description": "Should show as one Green Line journey, not a transfer"
        },
        {
            "name": "Green-B to Green-D (branch transfer at Kenmore)",
            "from": "place-bland",  # Blandford Street (B)
            "to": "place-fenwy",    # Fenway (D)
            "description": "Should show as one Green Line journey"
        },
        {
            "name": "Green-C to Green-E (via trunk)",
            "from": "place-cool",   # Coolidge Corner (C)
            "to": "place-hsmnl",    # Heath Street (E)
            "description": "Should use shared trunk, shown as one Green Line journey"
        },
        {
            "name": "Green Line to Red Line",
            "from": "place-kencl",  # Kenmore (Green)
            "to": "place-harsq",    # Harvard (Red)
            "description": "Should show as a real transfer (different line families)"
        }
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\nTest {i}: {scenario['name']}")
        print(f"From: {router.get_station_name(scenario['from'])}")
        print(f"To: {router.get_station_name(scenario['to'])}")
        print(f"Expected: {scenario['description']}")
        print("-" * 80)

        try:
            # Find route
            route = await router.find_route(
                start_station_id=scenario['from'],
                end_station_id=scenario['to'],
                departure_time=datetime.now(),
                mbta_client=mbta_client,
                debug=False
            )

            if route:
                print(f"✓ Route found!")
                print(f"  Total time: {route.total_time_seconds/60:.1f} minutes")
                print(f"  Transfers: {route.num_transfers}")
                print(f"  Segments: {len(route.segments)}")
                print()

                # Analyze segments
                print("  Route breakdown:")
                for j, seg in enumerate(route.segments, 1):
                    from_name = router.get_station_name(seg.from_station)
                    to_name = router.get_station_name(seg.to_station)

                    if seg.type == 'train':
                        print(f"    {j}. TRAIN: {from_name} → {to_name}")
                        print(f"       Line: {seg.line} (route: {seg.route_id})")
                        if seg.transfer_rating:
                            print(f"       Transfer Rating: {seg.transfer_rating.upper()}")
                    elif seg.type == 'walk':
                        print(f"    {j}. WALK: {from_name} → {to_name}")
                        print(f"       Time: {seg.time_seconds/60:.1f} min")
                    elif seg.type == 'transfer':
                        print(f"    {j}. TRANSFER at {from_name}")
                        if seg.transfer_rating:
                            print(f"       Rating: {seg.transfer_rating.upper()}")

                # Check if Green Line branches were treated correctly
                green_segments = [s for s in route.segments if s.type == 'train' and
                                 (s.line in ['B', 'C', 'D', 'E'] or 'Green' in (s.line or ''))]

                if len(green_segments) > 1:
                    # Check if transfer was counted between Green Line branches
                    green_transfer_count = 0
                    for j in range(len(route.segments) - 1):
                        curr = route.segments[j]
                        next_seg = route.segments[j + 1]
                        if (curr.type == 'train' and next_seg.type == 'train' and
                            curr.line in ['B', 'C', 'D', 'E'] and
                            next_seg.line in ['B', 'C', 'D', 'E'] and
                            curr.line != next_seg.line):
                            green_transfer_count += 1

                    if green_transfer_count == 0:
                        print(f"\n  ✅ CORRECT: Green Line branch change NOT counted as transfer")
                    else:
                        print(f"\n  ❌ ERROR: Green Line branch change WAS counted as transfer!")

                print()
            else:
                print(f"✗ No route found")
                print()

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_green_line_routing())
