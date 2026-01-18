"""
Tests to verify that alternative routes have correct arrival times.
Ensures that arrival times are always after departure times.
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dijkstra_router import DijkstraRouter, Route
from route_planner import RouteSegment


@pytest.fixture
def mock_mbta_client():
    """Create a mock MBTA client that returns predictable departure times."""
    client = AsyncMock()
    
    # Mock get_next_departures to return departures with increasing times
    async def mock_get_next_departures(stop_id, route_id=None, limit=3, use_predictions=True):
        base_time = datetime.now(timezone.utc)
        departures = []
        for i in range(limit):
            dep_time = base_time + timedelta(minutes=5 + i * 5)  # 5, 10, 15 minutes from now
            arr_time = dep_time + timedelta(minutes=3)  # 3 minute travel time
            
            departures.append({
                "type": "prediction",
                "departure_time": dep_time,
                "arrival_time": arr_time,  # This is for the from_station, not to_station
                "status": "On time",
                "trip_id": f"trip_{stop_id}_{i}",
                "vehicle_id": f"vehicle_{i}",
                "stop_id": stop_id,
                "route_id": route_id
            })
        return departures
    
    # Mock get_predictions to return arrival time at destination stop
    async def mock_get_predictions(stop_id, trip_id=None, limit=1):
        if trip_id and "trip_" in trip_id:
            # Extract the stop and index from trip_id
            base_time = datetime.now(timezone.utc)
            # For destination stop, arrival is 3 minutes after departure
            arr_time = base_time + timedelta(minutes=8)  # 5 min wait + 3 min travel
            
            return [{
                "id": f"pred_{stop_id}",
                "attributes": {
                    "arrival_time": arr_time.isoformat(),
                    "departure_time": arr_time.isoformat(),
                    "status": "On time"
                },
                "relationships": {
                    "trip": {"data": {"id": trip_id}},
                    "stop": {"data": {"id": stop_id}}
                }
            }]
        return []
    
    client.get_next_departures = mock_get_next_departures
    client.get_predictions = mock_get_predictions
    return client


@pytest.fixture
def mock_transit_graph():
    """Create a minimal transit graph for testing."""
    graph_data = {
        "nodes": {
            "place-start": {"latitude": 42.3655, "longitude": -71.0612},
            "place-middle": {"latitude": 42.3600, "longitude": -71.0580},
            "place-end": {"latitude": 42.3522, "longitude": -71.0552},
        },
        "edges": [
            {
                "from": "place-start",
                "to": "place-middle",
                "type": "train",
                "route_id": "Red",
                "line": "Red",
                "time_seconds": 180,  # 3 minutes
                "distance_meters": 1000
            },
            {
                "from": "place-middle",
                "to": "place-end",
                "type": "train",
                "route_id": "Red",
                "line": "Red",
                "time_seconds": 180,  # 3 minutes
                "distance_meters": 1000
            }
        ]
    }
    
    return graph_data


@pytest.mark.asyncio
async def test_alternative_route_arrival_after_departure(mock_mbta_client, mock_transit_graph):
    """Test that alternative routes have arrival times after departure times."""
    graph_data = mock_transit_graph
    
    # Create router with mock graph
    router = DijkstraRouter(graph_data)
    router.get_station_name = lambda x: graph_data["nodes"].get(x, {}).get("name", x) if x in graph_data["nodes"] else x
    
    # Create a primary route
    now = datetime.now(timezone.utc)
    primary_route = Route(
        segments=[
            RouteSegment(
                from_station="place-start",
                to_station="place-end",
                type="train",
                line="Red",
                route_id="Red",
                time_seconds=360,
                distance_meters=2000,
                departure_time=now + timedelta(minutes=5),
                arrival_time=now + timedelta(minutes=11),  # 5 min wait + 6 min travel
                status="Scheduled"
            )
        ],
        total_time_seconds=660,  # 11 minutes total
        total_distance_meters=2000,
        num_transfers=0,
        departure_time=now + timedelta(minutes=5),
        arrival_time=now + timedelta(minutes=11)
    )
    
    # Get alternative routes
    alternatives = await router.suggest_alternatives(
        primary_route=primary_route,
        start_station_id="place-start",
        end_station_id="place-end",
        mbta_client=mock_mbta_client,
        request_time=now,
        max_alternatives=2,
        debug=False
    )
    
    # Verify all alternatives have valid times
    for alt_route in alternatives:
        assert alt_route.departure_time is not None, "Alternative route must have departure time"
        assert alt_route.arrival_time is not None, "Alternative route must have arrival time"
        assert alt_route.arrival_time > alt_route.departure_time, \
            f"Arrival time ({alt_route.arrival_time}) must be after departure time ({alt_route.departure_time})"
        
        # Verify each segment has valid times
        for segment in alt_route.segments:
            if segment.type == "train":
                assert segment.departure_time is not None, "Segment must have departure time"
                assert segment.arrival_time is not None, "Segment must have arrival time"
                assert segment.arrival_time > segment.departure_time, \
                    f"Segment arrival ({segment.arrival_time}) must be after departure ({segment.departure_time})"
                assert segment.time_seconds > 0, "Segment travel time must be positive"
        
        # Verify total time is calculated correctly
        if alt_route.arrival_time and now:
            calculated_total = (alt_route.arrival_time - now).total_seconds()
            assert abs(calculated_total - alt_route.total_time_seconds) < 60, \
                f"Total time should match: calculated {calculated_total}s, got {alt_route.total_time_seconds}s"
    
    print(f"✓ PASS: All {len(alternatives)} alternative routes have valid arrival times")


@pytest.mark.asyncio
async def test_alternative_route_later_than_primary(mock_mbta_client, mock_transit_graph):
    """Test that alternative routes have later arrival times than the primary route."""
    graph_data = mock_transit_graph
    
    router = DijkstraRouter(graph_data)
    router.get_station_name = lambda x: graph_data["nodes"].get(x, {}).get("name", x) if x in graph_data["nodes"] else x
    
    now = datetime.now(timezone.utc)
    primary_route = Route(
        segments=[
            RouteSegment(
                from_station="place-start",
                to_station="place-end",
                type="train",
                line="Red",
                route_id="Red",
                time_seconds=360,
                distance_meters=2000,
                departure_time=now + timedelta(minutes=5),
                arrival_time=now + timedelta(minutes=11),
                status="Scheduled"
            )
        ],
        total_time_seconds=660,
        total_distance_meters=2000,
        num_transfers=0,
        departure_time=now + timedelta(minutes=5),
        arrival_time=now + timedelta(minutes=11)
    )
    
    alternatives = await router.suggest_alternatives(
        primary_route=primary_route,
        start_station_id="place-start",
        end_station_id="place-end",
        mbta_client=mock_mbta_client,
        request_time=now,
        max_alternatives=2,
        debug=False
    )
    
    # Verify alternatives arrive later than primary
    for alt_route in alternatives:
        if primary_route.arrival_time and alt_route.arrival_time:
            assert alt_route.arrival_time > primary_route.arrival_time, \
                f"Alternative arrival ({alt_route.arrival_time}) should be after primary ({primary_route.arrival_time})"
    
    print(f"✓ PASS: All alternatives arrive later than primary route")


@pytest.mark.asyncio
async def test_route_with_multiple_segments(mock_mbta_client, mock_transit_graph):
    """Test that routes with multiple segments (transfers) have correct times."""
    graph_data = mock_transit_graph
    
    router = DijkstraRouter(graph_data)
    router.get_station_name = lambda x: graph_data["nodes"].get(x, {}).get("name", x) if x in graph_data["nodes"] else x
    
    now = datetime.now(timezone.utc)
    
    # Create a route that goes through middle station
    route = await router.find_route(
        start_station_id="place-start",
        end_station_id="place-end",
        departure_time=now,
        mbta_client=mock_mbta_client,
        request_time=now,
        debug=False
    )
    
    if route:
        assert route.departure_time is not None
        assert route.arrival_time is not None
        assert route.arrival_time > route.departure_time
        
        # Verify segments are in chronological order
        prev_arrival = route.departure_time
        for segment in route.segments:
            if segment.type == "train":
                assert segment.departure_time >= prev_arrival, \
                    f"Segment departure ({segment.departure_time}) should be after previous arrival ({prev_arrival})"
                assert segment.arrival_time > segment.departure_time
                prev_arrival = segment.arrival_time
        
        print(f"✓ PASS: Multi-segment route has correct chronological order")
    else:
        pytest.skip("Could not find route (may need real graph data)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
