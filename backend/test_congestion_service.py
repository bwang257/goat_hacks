"""
Unit tests for congestion_service module
"""

import pytest
from datetime import datetime, timezone
from congestion_service import (
    CongestionLevel,
    StationCongestion,
    calculate_station_congestion,
    get_route_congestion,
    get_rush_hour_multiplier,
    should_avoid_station,
    RUSH_HOUR_STATIONS
)


class TestGetRushHourMultiplier:
    """Test rush hour multiplier calculations"""

    def test_weekday_morning_peak(self):
        """8 AM weekday should be peak"""
        multiplier = get_rush_hour_multiplier(8, is_weekday=True)
        assert multiplier == 1.0

    def test_weekday_evening_peak(self):
        """5-6 PM weekday should be peak"""
        assert get_rush_hour_multiplier(17, is_weekday=True) == 1.0
        assert get_rush_hour_multiplier(18, is_weekday=True) == 1.0

    def test_weekday_midday(self):
        """Midday should be moderate"""
        multiplier = get_rush_hour_multiplier(14, is_weekday=True)
        assert multiplier == 0.5

    def test_weekday_off_peak(self):
        """Late night should be low"""
        multiplier = get_rush_hour_multiplier(23, is_weekday=True)
        assert multiplier == 0.3

    def test_weekend_no_rush_hour(self):
        """Weekend 8 AM should not be rush hour"""
        multiplier = get_rush_hour_multiplier(8, is_weekday=False)
        assert multiplier == 1.0  # Normal, no rush hour boost


class TestCalculateStationCongestion:
    """Test station congestion calculations"""

    def test_major_hub_rush_hour(self):
        """Major hubs should have high congestion during rush hour"""
        # Monday 8 AM EST (13:00 UTC)
        rush_time = datetime(2026, 1, 19, 13, 0, tzinfo=timezone.utc)

        # South Station is a major hub
        congestion = calculate_station_congestion("place-sstat", rush_time)
        assert congestion.level == CongestionLevel.VERY_HIGH
        assert congestion.reason == "rush_hour"
        assert congestion.multiplier == 1.4

    def test_major_hub_off_peak(self):
        """Major hubs should have low congestion off-peak"""
        # Monday 2 PM EST (19:00 UTC)
        offpeak_time = datetime(2026, 1, 19, 19, 0, tzinfo=timezone.utc)

        congestion = calculate_station_congestion("place-sstat", offpeak_time)
        assert congestion.level == CongestionLevel.LOW
        assert congestion.multiplier == 1.0

    def test_minor_station_rush_hour(self):
        """Non-hub stations should have low congestion even during rush hour"""
        rush_time = datetime(2026, 1, 19, 13, 0, tzinfo=timezone.utc)

        # Davis is not in RUSH_HOUR_STATIONS
        congestion = calculate_station_congestion("place-davis", rush_time)
        assert congestion.level == CongestionLevel.LOW

    def test_event_affected_station(self):
        """Event-affected stations should show event congestion"""
        check_time = datetime(2026, 1, 19, 13, 0, tzinfo=timezone.utc)

        congestion = calculate_station_congestion(
            "place-kencl",  # Kenmore
            check_time,
            event_affected_stations=["place-kencl"],
            event_multiplier=1.3
        )
        assert congestion.level == CongestionLevel.HIGH
        assert congestion.reason == "event"
        assert congestion.multiplier == 1.3


class TestGetRouteCongestion:
    """Test route-wide congestion calculations"""

    def test_multiple_stations(self):
        """Should return congestion for multiple stations"""
        rush_time = datetime(2026, 1, 19, 13, 0, tzinfo=timezone.utc)
        stations = ["place-hrsq", "place-pktrm", "place-dwnxg", "place-sstat"]

        congestion_map = get_route_congestion(stations, rush_time)

        # Should have entries for congested stations
        assert len(congestion_map) > 0

        # South Station should be very high
        assert "place-sstat" in congestion_map
        assert congestion_map["place-sstat"].level == CongestionLevel.VERY_HIGH

    def test_excludes_low_congestion(self):
        """Should not include low congestion stations"""
        offpeak_time = datetime(2026, 1, 19, 19, 0, tzinfo=timezone.utc)
        stations = ["place-hrsq", "place-pktrm", "place-sstat"]

        congestion_map = get_route_congestion(stations, offpeak_time)

        # Off-peak should have no high congestion
        assert len(congestion_map) == 0


class TestShouldAvoidStation:
    """Test station avoidance logic"""

    def test_avoid_very_high_congestion(self):
        """Should avoid very high congestion stations"""
        rush_time = datetime(2026, 1, 19, 13, 0, tzinfo=timezone.utc)

        should_avoid = should_avoid_station(
            "place-sstat",
            rush_time,
            avoid_threshold=CongestionLevel.HIGH
        )
        assert should_avoid is True

    def test_dont_avoid_low_congestion(self):
        """Should not avoid low congestion stations"""
        offpeak_time = datetime(2026, 1, 19, 19, 0, tzinfo=timezone.utc)

        should_avoid = should_avoid_station(
            "place-sstat",
            offpeak_time,
            avoid_threshold=CongestionLevel.HIGH
        )
        assert should_avoid is False


class TestRushHourStations:
    """Test rush hour station configuration"""

    def test_major_hubs_configured(self):
        """Major transfer hubs should be configured"""
        assert "place-sstat" in RUSH_HOUR_STATIONS  # South Station
        assert "place-north" in RUSH_HOUR_STATIONS  # North Station
        assert "place-pktrm" in RUSH_HOUR_STATIONS  # Park Street
        assert "place-dwnxg" in RUSH_HOUR_STATIONS  # Downtown Crossing

    def test_multipliers_reasonable(self):
        """All multipliers should be reasonable (1.1 - 1.5)"""
        for station_id, multiplier in RUSH_HOUR_STATIONS.items():
            assert 1.1 <= multiplier <= 1.5, f"{station_id} has unreasonable multiplier: {multiplier}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
