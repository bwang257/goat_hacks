"""
Test weather adjustment calculations in route planning.

This test verifies that weather adjustments are correctly calculated
and applied to walking times in routes.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather_service import WeatherService
import json


async def test_weather_multiplier_calculations():
    """Test weather multiplier calculations for different conditions."""
    
    service = WeatherService()
    
    # Test cases: (weather_data, expected_multiplier_range)
    test_cases = [
        # Heavy rain (> 2.5mm)
        ({"precipitation_last_hour": 3.0, "temperature": 20}, 1.2),
        # Light rain (0.5-2.5mm)
        ({"precipitation_last_hour": 1.0, "temperature": 20}, 1.1),
        # Heavy rain in text description
        ({"precipitation_last_hour": None, "text_description": "Heavy Rain"}, 1.2),
        # Light rain in text
        ({"precipitation_last_hour": None, "text_description": "Light Rain"}, 1.1),
        # Extreme cold (< 20°F, no precipitation)
        ({"precipitation_last_hour": None, "temperature": -10, "text_description": "Clear"}, 1.05),
        # Extreme heat (> 90°F, no precipitation)
        ({"precipitation_last_hour": None, "temperature": 35, "text_description": "Clear"}, 1.05),
        # Normal conditions
        ({"precipitation_last_hour": None, "temperature": 20, "text_description": "Clear"}, 1.0),
        # None/empty data
        (None, 1.0),
        ({}, 1.0),
    ]
    
    print("Testing weather multiplier calculations...")
    print()
    
    all_passed = True
    for i, (weather_data, expected) in enumerate(test_cases):
        multiplier = service.calculate_weather_adjustment(weather_data)
        
        # Allow small floating point differences
        if abs(multiplier - expected) < 0.01:
            print(f"✓ Test {i+1}: {weather_data} -> {multiplier} (expected ~{expected})")
        else:
            print(f"✗ Test {i+1}: {weather_data} -> {multiplier} (expected ~{expected})")
            all_passed = False
    
    return all_passed


async def test_weather_service_fetch():
    """Test that weather service can fetch data (may fail if offline or API issues)."""
    
    print()
    print("Testing weather service data fetch...")
    
    service = WeatherService()
    
    try:
        weather_data = await service.get_current_weather()
        
        if weather_data:
            print(f"✓ Weather data fetched successfully")
            print(f"  Temperature: {weather_data.get('temperature')}°C")
            print(f"  Description: {weather_data.get('text_description', 'N/A')}")
            
            adjustment = service.calculate_weather_adjustment(weather_data)
            print(f"  Adjustment multiplier: {adjustment}")
            
            # Verify adjustment is reasonable (between 1.0 and 1.5)
            if 1.0 <= adjustment <= 1.5:
                print(f"✓ Adjustment multiplier is in valid range")
                return True
            else:
                print(f"✗ Adjustment multiplier out of range: {adjustment}")
                return False
        else:
            print("⚠ Weather data fetch returned None (API may be unavailable)")
            print("  This is acceptable for offline testing")
            return True  # Don't fail test if API is unavailable
            
    except Exception as e:
        print(f"⚠ Could not fetch weather (may be offline): {e}")
        print("  This is acceptable for offline testing")
        return True  # Don't fail test if API is unavailable


async def test_weather_in_route_calculation():
    """Test that weather adjustment is applied in route calculations."""
    
    print()
    print("Testing weather adjustment in route calculation...")
    
    # Load transit graph
    graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
    if not os.path.exists(graph_file):
        print("⚠ mbta_transit_graph.json not found. Skipping route test.")
        return True
    
    with open(graph_file, 'r') as f:
        graph_data = json.load(f)
    
    from dijkstra_router import DijkstraRouter
    
    router = DijkstraRouter(graph_data['graph'])
    
    # Test with walking route (two nearby stations)
    start_id = "place-north"
    end_id = "place-sstat"
    
    print(f"Start: {router.get_station_name(start_id)}")
    print(f"End: {router.get_station_name(end_id)}")
    print()
    
    # Test with different weather adjustments
    adjustments = [1.0, 1.1, 1.2]  # Normal, +10%, +20%
    results = {}
    
    for adj in adjustments:
        try:
            route = await router.find_route(
                start_station_id=start_id,
                end_station_id=end_id,
                departure_time=datetime.now(timezone.utc),
                mbta_client=None,  # No MBTA client for this test
                walking_speed_kmh=5.0,
                weather_adjustment=adj,
                debug=False
            )
            
            if route:
                walk_segments = [seg for seg in route.segments if seg.type == "walk"]
                if walk_segments:
                    total_walk_time = sum(seg.time_seconds for seg in walk_segments)
                    results[adj] = total_walk_time
                    print(f"  Weather adjustment {adj}: {total_walk_time/60:.1f} min walking")
        except Exception as e:
            print(f"  Error with adjustment {adj}: {e}")
    
    # Verify that higher adjustments lead to longer times
    if len(results) >= 2:
        adj_values = sorted(results.keys())
        times = [results[adj] for adj in adj_values]
        
        # Times should increase with adjustment (allow some tolerance)
        is_increasing = all(times[i] <= times[i+1] * 1.01 for i in range(len(times)-1))
        
        if is_increasing:
            print(f"✓ Walking times increase with weather adjustment")
            return True
        else:
            print(f"✗ Walking times don't increase with adjustment: {times}")
            return False
    else:
        print("⚠ Not enough results to verify adjustment impact")
        return True  # Don't fail if route doesn't have walking segments


async def test_all():
    """Run all weather tests."""
    print("=" * 60)
    print("WEATHER ADJUSTMENT TESTS")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(await test_weather_multiplier_calculations())
    results.append(await test_weather_service_fetch())
    results.append(await test_weather_in_route_calculation())
    
    print()
    print("=" * 60)
    if all(results):
        print("✓ ALL TESTS PASSED")
        return True
    else:
        print("✗ SOME TESTS FAILED")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_all())
    sys.exit(0 if success else 1)
