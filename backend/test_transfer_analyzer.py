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
            departure_time_seconds=1600,  # 10 minutes later
            walking_time_seconds=90
        )

        assert details["buffer_seconds"] == 210  # 180 + 30 line adjustment
        assert details["walking_time_seconds"] == 90
        assert details["total_required_seconds"] == 300  # 210 + 90
        assert details["available_seconds"] == 600  # 1600 - 1000
        assert details["slack_time_seconds"] == 300  # 600 - 300
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
