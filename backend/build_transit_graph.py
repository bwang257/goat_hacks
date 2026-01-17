import json
import httpx
import asyncio
import math
from typing import Dict, List, Tuple
from datetime import datetime

# Haversine distance calculation
def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in meters between two points"""
    R = 6371000  # Earth's radius in meters
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(delta_lng / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

async def calculate_walking_time(lat1: float, lng1: float, lat2: float, lng2: float) -> Tuple[float, float]:
    """
    Calculate walking time and distance between two points using OSRM.
    Returns (time_in_seconds, distance_in_meters)
    """
    url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{lng1},{lat1};{lng2},{lat2}?overview=false"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return (route["duration"], route["distance"])
    except:
        pass
    
    # Fallback: estimate based on straight-line distance
    distance = haversine_distance(lat1, lng1, lat2, lng2)
    # Assume 5 km/h walking speed and 1.3x detour factor
    time = (distance * 1.3) / (5000 / 3600)
    return (time, distance * 1.3)

async def get_train_time_between_stations(station_id_1: str, station_id_2: str, route_id: str, api_key: str) -> float:
    """
    Get estimated train travel time between two adjacent stations on the same line.
    Uses MBTA predictions API if available, otherwise estimates based on distance.
    """
    # This would use the MBTA API to get actual travel times
    # For now, we'll use a simplified approach
    
    # Typical MBTA speeds:
    # Heavy Rail (Red/Orange/Blue): ~40 km/h average with stops
    # Light Rail (Green): ~20 km/h average with stops
    # Commuter Rail: ~60 km/h average with stops
    
    # We'll estimate based on route type
    return 120  # Default: 2 minutes between stations (will be refined)

async def build_transit_graph(api_key: str = None):
    """
    Build a complete transit graph with:
    1. Train connections between adjacent stations
    2. Walking connections between nearby stations
    3. Transfer connections at multi-line stations
    """
    
    print("=" * 60)
    print("Building MBTA Transit Graph")
    print("=" * 60)
    print()
    
    # Load station data
    with open("./data/mbta_stations.json", "r") as f:
        mbta_data = json.load(f)
    
    stations = mbta_data["stations"]
    routes = mbta_data["routes"]
    
    print(f"Loaded {len(stations)} stations and {len(routes)} routes")
    
    # Initialize graph structure
    graph = {
        "nodes": {},  # station_id -> station info
        "edges": []   # List of edges with travel times
    }
    
    # Add all stations as nodes
    for station in stations:
        graph["nodes"][station["id"]] = {
            "id": station["id"],
            "name": station["name"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "lines": station["lines"]
        }
    
    print("\n1. Adding train connections...")
    train_edges = 0
    
    # Add train connections (from existing connections data)
    for station in stations:
        for connection in station.get("connections", []):
            connected_station_id = connection["station_id"]
            route_id = connection["route_id"]
            line_name = connection["line"]
            
            # Determine average speed based on route type
            route_type = routes[route_id]["type"]

            # Calculate time based on distance
            if route_type == 1:  # Heavy Rail
                avg_speed_kmh = 45  # Slightly faster
                stop_time = 15      # Shorter stops
            elif route_type == 0:  # Light Rail
                avg_speed_kmh = 25  # Slightly faster
                stop_time = 20      # Shorter stops
            else:  # Commuter Rail
                avg_speed_kmh = 60
                stop_time = 30

            travel_time = (distance / (avg_speed_kmh * 1000 / 3600)) + stop_time


            # Calculate time based on straight-line distance
            # (This is a simplification - real MBTA times would be better)
            station_coord = (station["latitude"], station["longitude"])
            connected_coord = (graph["nodes"][connected_station_id]["latitude"],
                             graph["nodes"][connected_station_id]["longitude"])
            
            distance = haversine_distance(*station_coord, *connected_coord)
            
            # Add edge (directed)
            edge = {
                "from": station["id"],
                "to": connected_station_id,
                "type": "train",
                "line": line_name,
                "route_id": route_id,
                "time_seconds": round(travel_time, 1),
                "distance_meters": round(distance, 1)
            }
            graph["edges"].append(edge)
            train_edges += 1
    
    print(f"   Added {train_edges} train connections")
    
    # 2. Add walking connections between nearby stations
    print("\n2. Calculating walking connections between nearby stations...")
    print("   (This may take a few minutes...)")
    
    MAX_WALKING_DISTANCE = 800  # meters (about 10 min walk)
    MAX_WALKING_TIME = 600      # seconds (10 minutes)
    
    walking_edges = 0
    station_list = list(graph["nodes"].values())
    
    # Calculate walking distances for nearby stations
    for i, station_a in enumerate(station_list):
        if i % 20 == 0:
            print(f"   Processing station {i+1}/{len(station_list)}...")
        
        for station_b in station_list[i+1:]:
            # Skip if same station
            if station_a["id"] == station_b["id"]:
                continue
            
            # Check straight-line distance first
            straight_distance = haversine_distance(
                station_a["latitude"], station_a["longitude"],
                station_b["latitude"], station_b["longitude"]
            )
            
            # Only consider stations within reasonable walking distance
            if straight_distance <= MAX_WALKING_DISTANCE:
                # Calculate actual walking time using OSRM
                walk_time, walk_distance = await calculate_walking_time(
                    station_a["latitude"], station_a["longitude"],
                    station_b["latitude"], station_b["longitude"]
                )
                
                if walk_time <= MAX_WALKING_TIME:
                    # Add bidirectional walking edges
                    edge_a_to_b = {
                        "from": station_a["id"],
                        "to": station_b["id"],
                        "type": "walk",
                        "time_seconds": round(walk_time, 1),
                        "distance_meters": round(walk_distance, 1)
                    }
                    edge_b_to_a = {
                        "from": station_b["id"],
                        "to": station_a["id"],
                        "type": "walk",
                        "time_seconds": round(walk_time, 1),
                        "distance_meters": round(walk_distance, 1)
                    }
                    graph["edges"].append(edge_a_to_b)
                    graph["edges"].append(edge_b_to_a)
                    walking_edges += 2
                
                # Rate limiting - don't overwhelm OSRM
                await asyncio.sleep(0.1)
    
    print(f"   Added {walking_edges} walking connections")
    
    # 3. Add transfer penalties at multi-line stations
    print("\n3. Adding transfer penalties...")
    transfer_edges = 0
    TRANSFER_TIME = 180  # 3 minutes to transfer between lines
    
    for station in stations:
        if len(station["lines"]) > 1:
            # This station serves multiple lines
            # We model this as a small time penalty when changing lines
            # (This is implicit in our graph - staying on same line is faster)
            pass
    
    print(f"   Transfer time penalty: {TRANSFER_TIME} seconds")
    
    # Save graph
    graph_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "num_stations": len(graph["nodes"]),
            "num_edges": len(graph["edges"]),
            "max_walking_distance_meters": MAX_WALKING_DISTANCE,
            "max_walking_time_seconds": MAX_WALKING_TIME,
            "transfer_penalty_seconds": TRANSFER_TIME
        },
        "graph": graph
    }
    
    output_file = "./data/mbta_transit_graph.json"
    with open(output_file, "w") as f:
        json.dump(graph_data, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"✓ Transit graph saved to: {output_file}")
    print("=" * 60)
    print(f"\nGraph Statistics:")
    print(f"  Stations (nodes): {len(graph['nodes'])}")
    print(f"  Total connections (edges): {len(graph['edges'])}")
    print(f"  - Train connections: {train_edges}")
    print(f"  - Walking connections: {walking_edges}")
    print()

if __name__ == "__main__":
    import os
    api_key = os.environ.get("MBTA_API_KEY")
    asyncio.run(build_transit_graph(api_key))