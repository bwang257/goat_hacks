"""
Unit tests for transfer_analyzer module
"""

import pytest
from transfer_analyzer import (
    TransferRating,
    calculate_transfer_time,
    rate_transfer,
    get_transfer_details,
    STATION_BUFFERS
)


class TestCalculateTransferTime:
    """Test calculate_transfer_time function"""

    def test_park_street_red_to_green(self):
        """Park Street Red→Green should have high buffer (180s base + 30s line adjustment)"""
        buffer = calculate_transfer_time("place-pktrm", "Red Line", "Green Line")
        assert buffer == 210  # 180 (station) + 30 (line adjustment)

    def test_downtown_crossing_orange_to_red(self):
        """Downtown Crossing Orange→Red should have medium buffer"""
        buffer = calculate_transfer_time("place-dwnxg", "Orange Line", "Red Line")
        assert buffer == 150  # No line adjustment for this pair

    def test_south_station_red_to_commuter_rail(self):
        """South Station Red→Commuter Rail should have high buffer"""
        buffer = calculate_transfer_time("place-sstat", "Red Line", "Commuter Rail")
        assert buffer == 240  # 180 (station) + 60 (commuter rail adjustment)

    def test_government_center_green_to_blue(self):
        """Government Center Green→Blue should have buffer with line adjustment"""
        buffer = calculate_transfer_time("place-gover", "Green Line", "Blue Line")
        assert buffer == 140  # 120 (station) + 20 (line adjustment)

    def test_unknown_station_uses_default(self):
        """Unknown station should use default buffer"""
        buffer = calculate_transfer_time("place-unknown")
        assert buffer == 60  # default

    def test_no_line_information(self):
        """Transfer without line information should use base station buffer"""
        buffer = calculate_transfer_time("place-pktrm")
        assert buffer == 180  # just the station buffer, no line adjustment

    def test_unknown_line_pair(self):
        """Unknown line pair should not add adjustment"""
        buffer = calculate_transfer_time("place-pktrm", "Red Line", "Blue Line")
        assert buffer == 180  # no adjustment for this pair


class TestRateTransfer:
    """Test rate_transfer function"""

    def test_likely_transfer_6_minutes(self):
        """6 minutes slack time should be LIKELY"""
        rating = rate_transfer(360)
        assert rating == TransferRating.LIKELY

    def test_likely_transfer_exactly_5_minutes(self):
        """Exactly 5 minutes slack time should be LIKELY (> 300 seconds)"""
        rating = rate_transfer(301)
        assert rating == TransferRating.LIKELY

    def test_risky_transfer_4_minutes(self):
        """4 minutes slack time should be RISKY"""
        rating = rate_transfer(240)
        assert rating == TransferRating.RISKY

    def test_risky_transfer_exactly_2_minutes(self):
        """Exactly 2 minutes slack time should be RISKY (> 120 seconds)"""
        rating = rate_transfer(121)
        assert rating == TransferRating.RISKY

    def test_unlikely_transfer_1_minute(self):
        """1 minute slack time should be UNLIKELY"""
        rating = rate_transfer(60)
        assert rating == TransferRating.UNLIKELY

    def test_unlikely_transfer_negative(self):
        """Negative slack time should be UNLIKELY"""
        rating = rate_transfer(-30)
        assert rating == TransferRating.UNLIKELY

    def test_unlikely_transfer_zero(self):
        """Zero slack time should be UNLIKELY"""
        rating = rate_transfer(0)
        assert rating == TransferRating.UNLIKELY


class TestGetTransferDetails:
    """Test get_transfer_details function"""

    def test_comfortable_transfer(self):
        """Test transfer with plenty of time"""
        details = get_transfer_details(
            station_id="place-pktrm",
            from_line="Red Line",
            to_line="Green Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1610,  # Just over 10 minutes later
            walking_time_seconds=90
        )

        assert details["buffer_seconds"] == 210  # 180 + 30 line adjustment
        assert details["walking_time_seconds"] == 90
        assert details["total_required_seconds"] == 300  # 210 + 90
        assert details["available_seconds"] == 610  # 1610 - 1000
        assert details["slack_time_seconds"] == 310  # 610 - 300 (> 300 = likely)
        assert details["rating"] == "likely"

    def test_tight_transfer(self):
        """Test transfer with tight timing"""
        details = get_transfer_details(
            station_id="place-dwnxg",
            from_line="Orange Line",
            to_line="Red Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1300,  # 5 minutes later
            walking_time_seconds=60
        )

        assert details["buffer_seconds"] == 150
        assert details["walking_time_seconds"] == 60
        assert details["total_required_seconds"] == 210
        assert details["available_seconds"] == 300
        assert details["slack_time_seconds"] == 90  # 90 seconds slack = UNLIKELY
        assert details["rating"] == "unlikely"

    def test_risky_transfer(self):
        """Test transfer with risky timing"""
        details = get_transfer_details(
            station_id="place-gover",
            from_line="Green Line",
            to_line="Blue Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1400,  # 6:40 minutes later
            walking_time_seconds=80
        )

        assert details["buffer_seconds"] == 140  # 120 + 20
        assert details["walking_time_seconds"] == 80
        assert details["total_required_seconds"] == 220
        assert details["available_seconds"] == 400
        assert details["slack_time_seconds"] == 180  # 3 minutes = RISKY
        assert details["rating"] == "risky"

    def test_no_walking_time(self):
        """Test transfer with no walking time (same platform)"""
        details = get_transfer_details(
            station_id="place-jfk",
            from_line="Red Line",
            to_line="Red Line",  # Branch transfer
            arrival_time_seconds=1000,
            departure_time_seconds=1300,
            walking_time_seconds=0
        )

        assert details["walking_time_seconds"] == 0
        assert details["total_required_seconds"] == 120  # just buffer
        assert details["slack_time_seconds"] == 180  # 300 - 120 = RISKY
        assert details["rating"] == "risky"


class TestWalkingSpeedAdjustment:
    """Test walking speed affects transfer buffer calculations"""

    def test_slow_walker_gets_more_buffer(self):
        """Slow walker (3 km/h) should get more buffer time than normal"""
        normal = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 5.0)
        slow = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 3.0)
        assert slow > normal
        # With 60% walking portion: slow should be significantly more
        assert slow >= normal * 1.2

    def test_fast_walker_gets_less_buffer(self):
        """Fast walker (6 km/h) should get less buffer time"""
        normal = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 5.0)
        fast = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 6.0)
        assert fast < normal

    def test_default_speed_unchanged(self):
        """Default 5 km/h should return same as original base calculation"""
        # Base: 180 (station) + 30 (line) = 210
        # With speed factor 1.0: 40% fixed (84) + 60% walking (126) = 210
        buffer = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 5.0)
        assert buffer == 210

    def test_minimum_buffer_floor(self):
        """Very fast walker shouldn't get unreasonably low buffer"""
        buffer = calculate_transfer_time("place-unknown", walking_speed_kmh=10.0)
        assert buffer >= 30  # Minimum floor

    def test_slow_walker_rating_changes(self):
        """Slow walker should have less slack time for same scenario"""
        # Same scenario, but slow walker needs more time
        normal_details = get_transfer_details(
            station_id="place-pktrm",
            from_line="Red Line",
            to_line="Green Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1400,  # 6:40 available
            walking_time_seconds=0,
            walking_speed_kmh=5.0
        )
        slow_details = get_transfer_details(
            station_id="place-pktrm",
            from_line="Red Line",
            to_line="Green Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1400,
            walking_time_seconds=0,
            walking_speed_kmh=3.0
        )
        # Slow walker has less slack time because buffer is higher
        assert slow_details["slack_time_seconds"] < normal_details["slack_time_seconds"]
        assert slow_details["buffer_seconds"] > normal_details["buffer_seconds"]

    def test_very_slow_walker_unlikely_transfer(self):
        """Very slow walker (2 km/h) should see transfer become unlikely"""
        # With normal speed this might be risky, but slow speed makes it unlikely
        slow_details = get_transfer_details(
            station_id="place-pktrm",
            from_line="Red Line",
            to_line="Green Line",
            arrival_time_seconds=1000,
            departure_time_seconds=1350,  # 5:50 available
            walking_time_seconds=0,
            walking_speed_kmh=2.0  # Very slow
        )
        # With 2 km/h, buffer should be much higher
        # Base 210 * (0.4 fixed + 0.6 * 2.5 factor) = 84 + 315 = 399
        assert slow_details["buffer_seconds"] > 350
        assert slow_details["rating"] == "unlikely"

    def test_zero_walking_speed_uses_default_factor(self):
        """Zero walking speed should use factor of 1.0 (no division by zero)"""
        buffer = calculate_transfer_time("place-pktrm", "Red Line", "Green Line", 0)
        # Should fall back to factor 1.0
        assert buffer == 210


class TestStationBuffers:
    """Test that all major transfer stations have configured buffers"""

    def test_major_stations_have_buffers(self):
        """Verify major transfer hubs have explicit buffers"""
        major_stations = [
            "place-pktrm",    # Park Street
            "place-dwnxg",    # Downtown Crossing
            "place-sstat",    # South Station
            "place-north",    # North Station
            "place-gover",    # Government Center
        ]

        for station in major_stations:
            assert station in STATION_BUFFERS
            assert STATION_BUFFERS[station] >= 120  # Major stations need at least 2 min

    def test_all_buffers_are_positive(self):
        """Verify all configured buffers are positive"""
        for station_id, buffer in STATION_BUFFERS.items():
            assert buffer > 0, f"{station_id} has non-positive buffer: {buffer}"

    def test_buffers_are_reasonable(self):
        """Verify buffers are within reasonable range (1-10 minutes)"""
        for station_id, buffer in STATION_BUFFERS.items():
            assert 30 <= buffer <= 600, f"{station_id} buffer out of range: {buffer}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
