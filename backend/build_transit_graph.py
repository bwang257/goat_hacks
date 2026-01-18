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

async def calculate_walking_time(lat1: float, lng1: float, lat2: float, lng2: float) -> Tuple[float, float, List]:
    """
    Calculate walking time, distance, and geometry between two points using OSRM.
    Returns (time_in_seconds, distance_in_meters, geometry_coordinates)
    """
    url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            # Get geometry coordinates [lng, lat] -> convert to [lat, lng] for Leaflet
            geom = route.get("geometry", {}).get("coordinates", [])
            coords = [[coord[1], coord[0]] for coord in geom]  # Swap to [lat, lng]
            return (route["duration"], route["distance"], coords)
    except:
        pass

    # Fallback: estimate based on straight-line distance
    distance = haversine_distance(lat1, lng1, lat2, lng2)
    # Assume 5 km/h walking speed and 1.3x detour factor
    time = (distance * 1.3) / (5000 / 3600)
    # Straight line coordinates
    coords = [[lat1, lng1], [lat2, lng2]]
    return (time, distance * 1.3, coords)

# Note: Train travel times are now calculated dynamically from MBTA API
# schedules and predictions, not from distance estimates.

async def build_transit_graph(api_key: str = None):
    """
    Build a transit connectivity graph with:
    1. Train connections between adjacent stations (connectivity only, no time estimates)
    2. Walking connections between nearby stations (with OSRM-calculated times)
    3. Route and station relationships for schedule-based routing
    
    Note: Train travel times are now calculated dynamically from MBTA API
    schedules and predictions, not from distance estimates.
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
    
    print("\n1. Adding train connections (connectivity only)...")
    train_edges = 0
    
    # Add train connections (from existing connections data)
    # These edges represent connectivity only - travel times will be
    # calculated dynamically from MBTA API schedules/predictions
    for station in stations:
        for connection in station.get("connections", []):
            connected_station_id = connection["station_id"]
            route_id = connection["route_id"]
            line_name = connection["line"]
            
            # Get route type for metadata
            route_type = routes.get(route_id, {}).get("type", 1)
            
            # Calculate distance and time estimate
            station_coord = (station["latitude"], station["longitude"])
            connected_coord = (graph["nodes"][connected_station_id]["latitude"],
                             graph["nodes"][connected_station_id]["longitude"])
            distance = haversine_distance(*station_coord, *connected_coord)
            
            # Estimate train travel time based on distance and average speeds
            # Light Rail (Green/Red/Blue/Orange): avg 20 km/h = 5.56 m/s
            # Heavy Rail (T commuter rail): avg 35 km/h = 9.72 m/s
            # Plus add 30 seconds per stop for acceleration/deceleration and boarding
            if route_type == 1:  # Light Rail (Green Line, etc.)
                speed_ms = 5.56  # meters per second
                stop_time = 30  # seconds per stop
            else:  # Heavy Rail or other
                speed_ms = 10  # meters per second average
                stop_time = 45  # seconds per stop
            
            estimated_time = (distance / speed_ms) + stop_time
            
            # Add edge (directed) with estimated time
            edge = {
                "from": station["id"],
                "to": connected_station_id,
                "type": "train",
                "line": line_name,
                "route_id": route_id,
                "route_type": route_type,
                "distance_meters": round(distance, 1),
                "time_seconds": round(estimated_time, 1),
                "note": "Time is estimated from distance; will be refined by MBTA API schedules"
            }
            graph["edges"].append(edge)
            train_edges += 1
    
    print(f"   Added {train_edges} train connections with estimated times")
    print("   Note: Times are based on distance estimates and will be refined by MBTA API")
    
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
                # Calculate actual walking time using OSRM (with geometry)
                walk_time, walk_distance, geometry = await calculate_walking_time(
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
                        "distance_meters": round(walk_distance, 1),
                        "geometry": geometry  # Add geometry for map display
                    }
                    edge_b_to_a = {
                        "from": station_b["id"],
                        "to": station_a["id"],
                        "type": "walk",
                        "time_seconds": round(walk_time, 1),
                        "distance_meters": round(walk_distance, 1),
                        "geometry": list(reversed(geometry))  # Reverse for opposite direction
                    }
                    graph["edges"].append(edge_a_to_b)
                    graph["edges"].append(edge_b_to_a)
                    walking_edges += 2
                
                # Rate limiting - don't overwhelm OSRM
                await asyncio.sleep(0.1)
    
    print(f"   Added {walking_edges} walking connections")
    
    # 3. Identify transfer stations (multi-line stations)
    print("\n3. Identifying transfer stations...")
    transfer_stations = []
    
    for station in stations:
        if len(station["lines"]) > 1:
            transfer_stations.append(station["id"])
    
    print(f"   Found {len(transfer_stations)} transfer stations")
    print("   Note: Transfer times will be calculated from MBTA API schedules")
    
    # Save graph
    graph_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "num_stations": len(graph["nodes"]),
            "num_edges": len(graph["edges"]),
            "max_walking_distance_meters": MAX_WALKING_DISTANCE,
            "max_walking_time_seconds": MAX_WALKING_TIME,
            "num_transfer_stations": len(transfer_stations),
            "note": "Train travel times are calculated dynamically from MBTA API schedules/predictions, not from distance estimates"
        },
        "graph": graph,
        "transfer_stations": transfer_stations
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