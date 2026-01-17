"""
Builds the transit graph from stations and route data.
"""

import json
import os
from typing import Dict, List
from .graph import TransitGraph
from ..models import Station


# Average time between stations on each route (seconds) - placeholder until API
ROUTE_SEGMENT_TIMES: Dict[str, float] = {
    'Red': 120,      # ~2 minutes between stations
    'Orange': 120,
    'Blue': 90,      # Shorter segments
    'Green-B': 150,  # Surface stops
    'Green-C': 150,
    'Green-D': 150,
    'Green-E': 150,
    'Silver': 180,
}

# Route station order (actual MBTA sequence)
ROUTE_ORDER: Dict[str, List[str]] = {
    'Red': [
        'place-alsgr', 'place-davis', 'place-portr', 'place-harsq',
        'place-cntsq', 'place-knncl', 'place-chmnl', 'place-pktrm',
        'place-dwnxg', 'place-sstat', 'place-brdwy', 'place-asmnl',
        'place-jfk', 'place-qnctr', 'place-brntn',
    ],
    'Orange': [
        'place-oakg', 'place-mlmnl', 'place-welln', 'place-sull',
        'place-north', 'place-haecl', 'place-state', 'place-dwnxg',
        'place-chncl', 'place-tumnl', 'place-bbsta', 'place-masta',
        'place-rcmnl', 'place-forhl',
    ],
    'Blue': [
        'place-wondl', 'place-astao', 'place-aport', 'place-mvbcl',
        'place-aqucl', 'place-state', 'place-bomnl',
    ],
    'Green-B': [
        'place-north', 'place-haecl', 'place-pktrm', 'place-boyls',
        'place-coecl', 'place-hymnl', 'place-kencl', 'place-bcnwa',
    ],
    'Green-C': [
        'place-north', 'place-haecl', 'place-pktrm', 'place-boyls',
        'place-coecl', 'place-hymnl', 'place-kencl', 'place-lake',
    ],
    'Green-D': [
        'place-north', 'place-haecl', 'place-pktrm', 'place-boyls',
        'place-coecl', 'place-hymnl', 'place-kencl', 'place-chhil', 'place-rsmnl',
    ],
    'Green-E': [
        'place-lech', 'place-north', 'place-haecl', 'place-pktrm',
        'place-boyls', 'place-alfcl', 'place-nuniv',
    ],
}


def build_transit_graph(stations: List[Station], walk_speed_mps: float = 1.4) -> TransitGraph:
    """
    Build transit graph from station data.
    
    Args:
        stations: List of station objects
        walk_speed_mps: Walking speed in meters per second (default 1.4 = normal pace)
    
    Returns:
        TransitGraph instance with all routes and transfers
    """
    graph = TransitGraph()
    
    # Add all stations as nodes
    station_map = {s.id: s for s in stations}
    for station in stations:
        graph.add_station(station.id, {
            'id': station.id,
            'name': station.name,
            'lat': station.lat,
            'lon': station.lon,
            'routes': station.routes,
        })
    
    # Add route edges (stations connected by routes)
    for route, station_order in ROUTE_ORDER.items():
        avg_time = ROUTE_SEGMENT_TIMES.get(route, 120)
        
        for i in range(len(station_order) - 1):
            from_id = station_order[i]
            to_id = station_order[i + 1]
            
            # Only add edge if both stations exist
            if from_id not in station_map or to_id not in station_map:
                continue
            
            from_station = station_map[from_id]
            to_station = station_map[to_id]
            
            # Calculate distance (Haversine formula approximation)
            lat_diff = abs(to_station.lat - from_station.lat)
            lon_diff = abs(to_station.lon - from_station.lon)
            # Rough approximation: 1 degree ≈ 111km
            distance_m = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111000
            
            graph.add_route_edge(from_id, to_id, route, avg_time, distance_m)
            # Also add reverse direction (transit is bidirectional)
            graph.add_route_edge(to_id, from_id, route, avg_time, distance_m)
    
    # Load transfer distances from JSON
    transfers_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "transfers.json"
    )
    
    try:
        with open(transfers_path) as f:
            transfers_data = json.load(f)
        
        # Add transfer edges (walking between platforms at same station)
        for station_id, transfers in transfers_data.items():
            if station_id not in station_map:
                continue
            
            for transfer_key, walk_distance_m in transfers.items():
                # Parse transfer key: "Red-to-Orange" -> route1="Red", route2="Orange"
                if '-to-' in transfer_key:
                    route1, route2 = transfer_key.split('-to-')
                    
                    # Find stations at this transfer point with these routes
                    current_station = station_map[station_id]
                    if route1 in current_station.routes and route2 in current_station.routes:
                        # Self-loop for same-station transfer
                        graph.add_transfer_edge(
                            station_id, station_id, walk_distance_m, walk_speed_mps
                        )
        
        # Add cross-station transfers (stations that are close but different IDs)
        # Park Street: Red and Green are same platform complex
        # Downtown Crossing: Red and Orange are connected
        # State: Orange and Blue are connected
        # These are already in transfers.json as same-station transfers
        
    except Exception as e:
        print(f"Warning: Could not load transfer data: {e}")
    
    return graph
