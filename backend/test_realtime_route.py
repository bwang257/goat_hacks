"""
Test script to verify transfer ratings with real-time MBTA data
"""
import httpx
import json
from datetime import datetime

def test_route(station_1, station_2, route_name):
    """Test a route and display transfer ratings"""

    response = httpx.post(
        'http://127.0.0.1:8000/api/route',
        json={
            'station_id_1': station_1,
            'station_id_2': station_2,
            'prefer_fewer_transfers': True,
            'use_realtime': True
        },
        timeout=20.0
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return

    data = response.json()

    print('='*70)
    print(f'Route: {route_name}')
    print('='*70)
    print(f'Total time: {data["total_time_minutes"]} minutes')
    print(f'Total transfers: {data["num_transfers"]}')
    print(f'Has risky transfers: {data.get("has_risky_transfers", False)}')
    print(f'Alternatives: {len(data.get("alternatives", []))}')
    print()

    prev_line = None
    transfer_count = 0

    for i, seg in enumerate(data['segments'], 1):
        curr_line = seg.get('line')
        is_line_change = prev_line and curr_line and prev_line != curr_line

        print(f'{i}. {seg["from_station_name"]} → {seg["to_station_name"]}')
        print(f'   Type: {seg["type"]} | Line: {curr_line}')

        if seg.get('departure_time'):
            dt = datetime.fromisoformat(seg['departure_time'].replace('Z', '+00:00'))
            print(f'   Departs: {dt.strftime("%I:%M %p")}')

        if is_line_change:
            transfer_count += 1
            print(f'   🔄 TRANSFER #{transfer_count}: {prev_line} → {curr_line}')

        if seg.get('transfer_rating'):
            rating = seg['transfer_rating'].upper()
            emoji = '✅' if rating == 'LIKELY' else '⚠️' if rating == 'RISKY' else '🚫'
            print(f'   {emoji} TRANSFER RATING: {rating}')
            print(f'      Slack Time: {seg.get("slack_time_seconds", 0)/60:.1f} min')
            print(f'      Buffer: {seg.get("buffer_seconds", 0)/60:.1f} min')
        elif is_line_change:
            print(f'   ⚠️  No transfer rating (expected for line change)')

        print()
        prev_line = curr_line

    print(f'Line changes detected: {transfer_count}')
    print(f'API reported transfers: {data["num_transfers"]}')
    print()

if __name__ == "__main__":
    print("Testing MBTA Transfer Ratings with Real-Time Data")
    print()

    # Test 1: Harvard to Copley (Red → Green at Park Street)
    test_route('place-harsq', 'place-coecl', 'Harvard (Red) → Copley (Green)')

    # Test 2: Alewife to Downtown Crossing (Red, no transfer)
    test_route('place-alfcl', 'place-dwnxg', 'Alewife → Downtown Crossing (Red Line only)')

    # Test 3: Downtown Crossing to Back Bay (Orange → Commuter Rail)
    test_route('place-dwnxg', 'place-bbsta', 'Downtown Crossing (Orange) → Back Bay')
