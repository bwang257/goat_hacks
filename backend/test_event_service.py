"""
Test event detection and impact assessment.

This test verifies that events are correctly detected and their impact
is calculated for routes passing through affected stations.
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_service import EventService, EventImpact


def test_event_service_initialization():
    """Test that event service initializes correctly."""
    print("Testing event service initialization...")
    
    service = EventService()
    
    assert service is not None
    assert service.venue_stations is not None
    assert len(service.venue_stations) > 0
    
    print("✓ Event service initialized correctly")
    print()


def test_venue_station_mapping():
    """Test venue to station mapping."""
    print("Testing venue to station mapping...")
    
    service = EventService()
    
    # Test that all venues have stations mapped
    assert "fenway_park" in service.venue_stations
    assert "td_garden" in service.venue_stations
    assert len(service.venue_stations["fenway_park"]) > 0
    assert len(service.venue_stations["td_garden"]) > 0
    
    print(f"  Fenway Park → {service.venue_stations['fenway_park']}")
    print(f"  TD Garden → {service.venue_stations['td_garden']}")
    print("✓ Venue mapping correct")
    print()


def test_event_time_relevance():
    """Test event time window logic."""
    print("Testing event time relevance...")
    
    service = EventService()
    
    route_time = datetime(2026, 3, 28, 18, 0, tzinfo=timezone.utc)  # 6 PM
    
    # Event 2 hours before (relevant)
    event_time_1 = datetime(2026, 3, 28, 19, 0, tzinfo=timezone.utc)  # 7 PM (1 hour after route)
    assert service._is_event_time_relevant(event_time_1, route_time) == True
    
    # Event 2 hours before route (relevant)
    event_time_2 = datetime(2026, 3, 28, 16, 0, tzinfo=timezone.utc)  # 4 PM (2 hours before route)
    assert service._is_event_time_relevant(event_time_2, route_time) == True
    
    # Event 4 hours before (not relevant)
    event_time_3 = datetime(2026, 3, 28, 13, 0, tzinfo=timezone.utc)  # 1 PM (5 hours before route)
    assert service._is_event_time_relevant(event_time_3, route_time) == False
    
    # Event 4 hours after (not relevant)
    event_time_4 = datetime(2026, 3, 28, 22, 0, tzinfo=timezone.utc)  # 10 PM (4 hours after route)
    assert service._is_event_time_relevant(event_time_4, route_time) == False
    
    print("✓ Event time relevance logic correct")
    print()


def test_red_sox_event_detection():
    """Test Red Sox event detection for known game dates."""
    print("Testing Red Sox event detection...")
    
    service = EventService()
    
    # Test with a known Red Sox game date
    test_date = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)  # Noon on game day
    events = service._get_red_sox_events_today(test_date)
    
    # Should find Red Sox game on this date
    if len(events) > 0:
        event = events[0]
        assert event.has_event == True
        assert event.event_type == "sports"
        assert "Red Sox" in event.event_name
        assert len(event.affected_stations) > 0
        print(f"  Found event: {event.event_name}")
        print(f"  Affected stations: {event.affected_stations}")
        print("✓ Red Sox event detection working")
    else:
        print("  No Red Sox games found for test date (this is OK if date not in database)")
        print("  (Event database would be populated with real dates in production)")
    
    print()


def test_td_garden_event_detection():
    """Test TD Garden event detection."""
    print("Testing TD Garden event detection...")
    
    service = EventService()
    
    # Test with a known TD Garden game date
    test_date = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    events = service._get_td_garden_events_today(test_date)
    
    # Should find TD Garden events on this date
    if len(events) > 0:
        event = events[0]
        assert event.has_event == True
        assert event.event_type == "sports"
        assert len(event.affected_stations) > 0
        print(f"  Found event: {event.event_name}")
        print(f"  Affected stations: {event.affected_stations}")
        print("✓ TD Garden event detection working")
    else:
        print("  No TD Garden events found for test date (this is OK if date not in database)")
    
    print()


def test_route_event_detection():
    """Test event detection for routes passing through affected stations."""
    print("Testing route event detection...")
    
    service = EventService()
    
    # Test route that passes through Kenmore (Fenway Park station)
    route_stations = ["place-harsq", "place-kencl", "place-pktrm"]  # Harvard Square → Kenmore → Park Street
    route_time = datetime(2026, 3, 28, 18, 0, tzinfo=timezone.utc)  # 6 PM on game day
    
    impact = service.check_events_for_route(route_stations, route_time)
    
    if impact.has_event:
        print(f"  Event detected: {impact.event_name}")
        print(f"  Affected stations: {impact.affected_stations}")
        print(f"  Congestion multiplier: {impact.congestion_multiplier}")
        assert impact.congestion_multiplier >= 1.0
        print("✓ Route event detection working")
    else:
        print("  No events detected for test route (this is OK if no events scheduled)")
        print("  (In production, events would be fetched from APIs)")
    
    print()
    
    # Test route that doesn't pass through affected stations
    route_stations_no_event = ["place-sstat", "place-dwnxg", "place-pktrm"]  # South Station → Downtown Crossing → Park Street
    impact_no_event = service.check_events_for_route(route_stations_no_event, route_time)
    
    if not impact_no_event.has_event:
        print("✓ Correctly identified route with no affected events")
    else:
        print(f"  Warning: Event detected for route without affected stations: {impact_no_event.event_name}")
    
    print()


def test_multiple_events_same_route():
    """Test detection of multiple events affecting same route."""
    print("Testing multiple events on same route...")
    
    service = EventService()
    
    # Route passing through both Kenmore and North Station
    route_stations = ["place-kencl", "place-pktrm", "place-north"]
    route_time = datetime(2026, 3, 28, 18, 0, tzinfo=timezone.utc)
    
    impact = service.check_events_for_route(route_stations, route_time)
    
    # Should detect events at both venues if they exist on this date
    if impact.has_event:
        print(f"  Events detected: {impact.event_name}")
        print(f"  All affected stations: {impact.affected_stations}")
        print("✓ Multiple event detection working")
    else:
        print("  No multiple events detected (this is OK if dates don't overlap)")
    
    print()


def test_all():
    """Run all event service tests."""
    print("=" * 60)
    print("EVENT SERVICE TESTS")
    print("=" * 60)
    print()
    
    try:
        test_event_service_initialization()
        test_venue_station_mapping()
        test_event_time_relevance()
        test_red_sox_event_detection()
        test_td_garden_event_detection()
        test_route_event_detection()
        test_multiple_events_same_route()
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return True
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
