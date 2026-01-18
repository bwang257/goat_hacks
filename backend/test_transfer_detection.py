"""
Debug script to understand transfer detection and rating
"""
import httpx
import json

def test_simple_transfer():
    """Test a simple Red to Green transfer"""

    response = httpx.post(
        'http://127.0.0.1:8000/api/route',
        json={
            'station_id_1': 'place-pktrm',  # Start AT Park Street
            'station_id_2': 'place-kencl',  # Go to Kenmore (Green)
            'prefer_fewer_transfers': True,
            'use_realtime': True
        },
        timeout=20.0
    )

    data = response.json()

    print('Route: Park Street → Kenmore (should be just Green Line)')
    print('='*70)
    for i, seg in enumerate(data['segments'], 1):
        print(f'{i}. {seg["from_station_name"]} → {seg["to_station_name"]}')
        print(f'   Line: {seg.get("line")}')
        print(f'   Transfer rating: {seg.get("transfer_rating")}')
        print(f'   Buffer: {seg.get("buffer_seconds")}')
        print()

    print()

    # Now test starting from Harvard (Red) to Kenmore (Green)
    response = httpx.post(
        'http://127.0.0.1:8000/api/route',
        json={
            'station_id_1': 'place-harsq',  # Harvard (Red)
            'station_id_2': 'place-kencl',  # Kenmore (Green)
            'prefer_fewer_transfers': True,
            'use_realtime': True
        },
        timeout=20.0
    )

    data = response.json()

    print('Route: Harvard (Red) → Kenmore (Green)')
    print('='*70)
    prev_line = None
    for i, seg in enumerate(data['segments'], 1):
        curr_line = seg.get("line")
        is_transfer = prev_line and curr_line and prev_line != curr_line

        print(f'{i}. {seg["from_station_name"]} → {seg["to_station_name"]}')
        print(f'   Line: {curr_line}')
        print(f'   Is transfer: {is_transfer}')
        if is_transfer:
            print(f'   Previous line: {prev_line}')
        print(f'   Transfer rating: {seg.get("transfer_rating")}')
        print(f'   Slack time: {seg.get("slack_time_seconds")}')
        print(f'   Buffer: {seg.get("buffer_seconds")}')
        print()

        prev_line = curr_line

if __name__ == "__main__":
    test_simple_transfer()
