"""
Simple test script for transfer_analyzer (without pytest)
"""

from transfer_analyzer import (
    TransferRating,
    calculate_transfer_time,
    rate_transfer,
    get_transfer_details
)

def test_calculate_transfer_time():
    print("Testing calculate_transfer_time()...")

    # Test Park Street Red→Green
    buffer = calculate_transfer_time("place-pktrm", "Red Line", "Green Line")
    assert buffer == 210, f"Expected 210s, got {buffer}s"
    print(f"✓ Park Street Red→Green: {buffer}s (180 base + 30 line adjustment)")

    # Test Downtown Crossing Orange→Red
    buffer = calculate_transfer_time("place-dwnxg", "Orange Line", "Red Line")
    assert buffer == 150, f"Expected 150s, got {buffer}s"
    print(f"✓ Downtown Crossing Orange→Red: {buffer}s")

    # Test South Station Red→Commuter Rail
    buffer = calculate_transfer_time("place-sstat", "Red Line", "Commuter Rail")
    assert buffer == 240, f"Expected 240s, got {buffer}s"
    print(f"✓ South Station Red→Commuter Rail: {buffer}s (180 + 60 adjustment)")

    # Test unknown station
    buffer = calculate_transfer_time("place-unknown")
    assert buffer == 60, f"Expected 60s (default), got {buffer}s"
    print(f"✓ Unknown station: {buffer}s (default)")

    print("All transfer time tests passed!\n")

def test_rate_transfer():
    print("Testing rate_transfer()...")

    # Test LIKELY (> 5 min)
    rating = rate_transfer(360)
    assert rating == TransferRating.LIKELY, f"Expected LIKELY, got {rating}"
    print(f"✓ 6 minutes slack: {rating.value}")

    # Test RISKY (2-5 min)
    rating = rate_transfer(240)
    assert rating == TransferRating.RISKY, f"Expected RISKY, got {rating}"
    print(f"✓ 4 minutes slack: {rating.value}")

    # Test UNLIKELY (< 2 min)
    rating = rate_transfer(60)
    assert rating == TransferRating.UNLIKELY, f"Expected UNLIKELY, got {rating}"
    print(f"✓ 1 minute slack: {rating.value}")

    # Test negative slack
    rating = rate_transfer(-30)
    assert rating == TransferRating.UNLIKELY, f"Expected UNLIKELY, got {rating}"
    print(f"✓ Negative slack: {rating.value}")

    print("All rating tests passed!\n")

def test_get_transfer_details():
    print("Testing get_transfer_details()...")

    # Test comfortable transfer at Park Street
    details = get_transfer_details(
        station_id="place-pktrm",
        from_line="Red Line",
        to_line="Green Line",
        arrival_time_seconds=1000,
        departure_time_seconds=1650,  # 10 min 50 sec later
        walking_time_seconds=90
    )

    print(f"Park Street Red→Green transfer (10:50 min available):")
    print(f"  Buffer: {details['buffer_seconds']}s")
    print(f"  Walking: {details['walking_time_seconds']}s")
    print(f"  Total required: {details['total_required_seconds']}s")
    print(f"  Available: {details['available_seconds']}s")
    print(f"  Slack: {details['slack_time_seconds']}s")
    print(f"  Rating: {details['rating']}")

    assert details['buffer_seconds'] == 210
    assert details['slack_time_seconds'] == 350  # 650 - 300
    assert details['rating'] == "likely"
    print("✓ Comfortable transfer test passed!\n")

    # Test tight transfer
    details = get_transfer_details(
        station_id="place-dwnxg",
        from_line="Orange Line",
        to_line="Red Line",
        arrival_time_seconds=1000,
        departure_time_seconds=1300,  # 5 minutes later
        walking_time_seconds=60
    )

    print(f"Downtown Crossing Orange→Red transfer (5 min available):")
    print(f"  Buffer: {details['buffer_seconds']}s")
    print(f"  Walking: {details['walking_time_seconds']}s")
    print(f"  Total required: {details['total_required_seconds']}s")
    print(f"  Available: {details['available_seconds']}s")
    print(f"  Slack: {details['slack_time_seconds']}s")
    print(f"  Rating: {details['rating']}")

    assert details['buffer_seconds'] == 150
    assert details['slack_time_seconds'] == 90  # 300 - 210
    assert details['rating'] == "unlikely"
    print("✓ Tight transfer test passed!\n")

if __name__ == "__main__":
    print("="*60)
    print("TRANSFER ANALYZER TESTS")
    print("="*60 + "\n")

    try:
        test_calculate_transfer_time()
        test_rate_transfer()
        test_get_transfer_details()

        print("="*60)
        print("ALL TESTS PASSED! ✓")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
