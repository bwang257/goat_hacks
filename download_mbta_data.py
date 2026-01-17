import httpx
import json
from typing import Dict, Set
import asyncio
import os

async def fetch_mbta_data(api_key: str) -> Dict:
    """
    Fetch all MBTA station data and save to file.
    Run this script once to download all data.
    Excludes: Mattapan Trolley
    """
    
    base_url = "https://api-v3.mbta.com"
    headers = {"x-api-key": api_key} if api_key else {}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        
        # 1. Fetch all routes (subway, light rail, commuter rail)
        print("Fetching routes...")
        routes_url = f"{base_url}/routes?filter[type]=0,1,2"
        routes_response = await client.get(routes_url, headers=headers)
        routes_response.raise_for_status()
        routes_data = routes_response.json()
        
        routes = {}
        route_ids = []
        
        # Mattapan Trolley route ID to exclude
        EXCLUDED_ROUTES = ["Mattapan"]
        
        for route in routes_data["data"]:
            route_id = route["id"]
            
            # Skip Mattapan Trolley
            if route_id in EXCLUDED_ROUTES:
                print(f"  Excluding: {route['attributes']['long_name']}")
                continue
            
            route_ids.append(route_id)
            
            attrs = route["attributes"]
            route_type = attrs["type"]
            
            # Determine display name based on route type
            if route_type in [0, 1]:  # Light Rail or Heavy Rail (subway)
                display_name = attrs.get("short_name") or attrs["long_name"]
            else:  # Commuter Rail
                display_name = attrs["long_name"]
            
            routes[route_id] = {
                "id": route_id,
                "name": attrs["long_name"],
                "short_name": attrs.get("short_name", ""),
                "display_name": display_name,
                "type": route_type,
                "color": attrs.get("color", ""),
                "text_color": attrs.get("text_color", ""),
                "sort_order": attrs.get("sort_order", 999)
            }
        
        print(f"Found {len(routes)} routes (excluded Mattapan Trolley)")
        
        # 2. Fetch all stops/stations - use location_type filter
        print("Fetching stations (parent stops only)...")
        
        # Get parent stations (location_type=1)
        stations_url = f"{base_url}/stops?filter[location_type]=1"
        stations_response = await client.get(stations_url, headers=headers)
        stations_response.raise_for_status()
        stations_data = stations_response.json()
        
        stations = {}
        
        for stop in stations_data["data"]:
            attrs = stop["attributes"]
            
            if attrs.get("latitude") and attrs.get("longitude"):
                stations[stop["id"]] = {
                    "id": stop["id"],
                    "name": attrs["name"],
                    "latitude": attrs["latitude"],
                    "longitude": attrs["longitude"],
                    "wheelchair_boarding": attrs.get("wheelchair_boarding", 0),
                    "municipality": attrs.get("municipality", ""),
                    "address": attrs.get("address"),
                    "platform_name": attrs.get("platform_name"),
                    "route_ids": [],
                    "lines": [],
                    "child_stops": [],
                    "connections": []
                }
        
        print(f"Found {len(stations)} parent stations")
        
        # Also get all child stops to map to parents
        print("Fetching child stops...")
        child_stops_url = f"{base_url}/stops?filter[location_type]=0"
        child_stops_response = await client.get(child_stops_url, headers=headers)
        child_stops_response.raise_for_status()
        child_stops_data = child_stops_response.json()
        
        stop_to_parent = {}
        
        for stop in child_stops_data["data"]:
            parent_rel = stop["relationships"].get("parent_station", {}).get("data")
            if parent_rel:
                parent_id = parent_rel["id"]
                stop_id = stop["id"]
                stop_to_parent[stop_id] = parent_id
                
                # Add child stop to parent's child_stops list
                if parent_id in stations:
                    if stop_id not in stations[parent_id]["child_stops"]:
                        stations[parent_id]["child_stops"].append(stop_id)
        
        print(f"Mapped {len(stop_to_parent)} child stops to parents")
        
        # 3. Map routes to stations (excluding Mattapan)
        print("Mapping routes to stations...")
        for idx, route_id in enumerate(route_ids):
            print(f"  Processing route {idx+1}/{len(route_ids)}: {routes[route_id]['display_name']}")
            route_stops_url = f"{base_url}/stops?filter[route]={route_id}"
            
            try:
                route_stops_response = await client.get(route_stops_url, headers=headers)
                route_stops_response.raise_for_status()
                route_stops_data = route_stops_response.json()
                
                for stop in route_stops_data["data"]:
                    stop_id = stop["id"]
                    
                    # Find parent station
                    if stop_id in stations:
                        parent_id = stop_id
                    elif stop_id in stop_to_parent:
                        parent_id = stop_to_parent[stop_id]
                    else:
                        continue
                    
                    # Add route to parent station
                    if parent_id in stations:
                        if route_id not in stations[parent_id]["route_ids"]:
                            stations[parent_id]["route_ids"].append(route_id)
                            stations[parent_id]["lines"].append(routes[route_id]["display_name"])
            
            except httpx.HTTPStatusError as e:
                print(f"    Warning: Could not fetch stops for route {route_id}: {e}")
                continue
        
        # 4. Remove stations that only serve excluded routes (Mattapan stations)
        print("Filtering out Mattapan-only stations...")
        stations_before = len(stations)
        stations = {
            station_id: station_data 
            for station_id, station_data in stations.items() 
            if len(station_data["route_ids"]) > 0  # Only keep stations that serve at least one route
        }
        stations_removed = stations_before - len(stations)
        if stations_removed > 0:
            print(f"  Removed {stations_removed} Mattapan-only stations")
        
        # 5. Build connections graph using trip data (handles branches correctly)
        print("Building station connections from trip data...")
        print("  (This ensures accurate branching for commuter rail routes)")
        
        for idx, route_id in enumerate(route_ids):
            print(f"  Processing connections for route {idx+1}/{len(route_ids)}: {routes[route_id]['display_name']}")
            
            try:
                # Use schedules/trips to get actual stop sequences
                # This properly handles branches (e.g., Providence/Stoughton splits at Canton Junction)
                schedules_url = f"{base_url}/schedules"
                params = {
                    "filter[route]": route_id,
                    "page[limit]": "100",  # Get multiple trips to see all branches
                    "include": "trip,stop"
                }
                
                schedules_response = await client.get(schedules_url, params=params, headers=headers)
                schedules_response.raise_for_status()
                schedules_data = schedules_response.json()
                
                # Group schedules by trip to get stop sequences
                trips_to_stops = {}  # trip_id -> list of (stop_id, sequence)
                
                for schedule in schedules_data.get("data", []):
                    trip_rel = schedule.get("relationships", {}).get("trip", {}).get("data")
                    stop_rel = schedule.get("relationships", {}).get("stop", {}).get("data")
                    
                    if not trip_rel or not stop_rel:
                        continue
                    
                    trip_id = trip_rel.get("id")
                    stop_id = stop_rel.get("id")
                    
                    if not trip_id or not stop_id:
                        continue
                    
                    # Get stop sequence from schedule attributes
                    attrs = schedule.get("attributes", {})
                    stop_sequence = attrs.get("stop_sequence")
                    
                    if stop_sequence is None:
                        continue
                    
                    # Map child stop to parent station
                    parent_id = stop_to_parent.get(stop_id, stop_id)
                    if parent_id not in stations:
                        continue
                    
                    if trip_id not in trips_to_stops:
                        trips_to_stops[trip_id] = []
                    
                    trips_to_stops[trip_id].append((parent_id, stop_sequence))
                
                # Build connections from trip stop sequences
                connections_added = set()  # Track to avoid duplicates
                
                for trip_id, stop_sequence_list in trips_to_stops.items():
                    # Sort by stop_sequence to get correct order
                    stop_sequence_list.sort(key=lambda x: x[1])
                    
                    # Connect adjacent stops in this trip
                    for i in range(len(stop_sequence_list) - 1):
                        station_a = stop_sequence_list[i][0]
                        station_b = stop_sequence_list[i + 1][0]
                        
                        # Skip if same station (shouldn't happen, but be safe)
                        if station_a == station_b:
                            continue
                        
                        # Create connection key to avoid duplicates
                        conn_key_a = (station_a, station_b, route_id)
                        conn_key_b = (station_b, station_a, route_id)
                        
                        if conn_key_a not in connections_added:
                            connection_a = {
                                "station_id": station_b,
                                "route_id": route_id,
                                "line": routes[route_id]["display_name"]
                            }
                            
                            if connection_a not in stations[station_a]["connections"]:
                                stations[station_a]["connections"].append(connection_a)
                            connections_added.add(conn_key_a)
                        
                        if conn_key_b not in connections_added:
                            connection_b = {
                                "station_id": station_a,
                                "route_id": route_id,
                                "line": routes[route_id]["display_name"]
                            }
                            
                            if connection_b not in stations[station_b]["connections"]:
                                stations[station_b]["connections"].append(connection_b)
                            connections_added.add(conn_key_b)
                
                if len(connections_added) == 0:
                    # Fallback: if no trip data, use simple stop ordering
                    print(f"    No trip data found, using fallback method")
                    route_stops_url = f"{base_url}/stops?filter[route]={route_id}"
                    route_stops_response = await client.get(route_stops_url, headers=headers)
                    route_stops_response.raise_for_status()
                    route_stops_data = route_stops_response.json()
                    
                    ordered_stations = []
                    for stop in route_stops_data["data"]:
                        parent_id = stop_to_parent.get(stop["id"], stop["id"])
                        if parent_id in stations and parent_id not in ordered_stations:
                            ordered_stations.append(parent_id)
                    
                    for i in range(len(ordered_stations) - 1):
                        station_a = ordered_stations[i]
                        station_b = ordered_stations[i + 1]
                        
                        connection_a = {
                            "station_id": station_b,
                            "route_id": route_id,
                            "line": routes[route_id]["display_name"]
                        }
                        connection_b = {
                            "station_id": station_a,
                            "route_id": route_id,
                            "line": routes[route_id]["display_name"]
                        }
                        
                        if connection_a not in stations[station_a]["connections"]:
                            stations[station_a]["connections"].append(connection_a)
                        if connection_b not in stations[station_b]["connections"]:
                            stations[station_b]["connections"].append(connection_b)
            
            except httpx.HTTPStatusError as e:
                print(f"    Warning: Could not build connections for route {route_id}: {e}")
                continue
            except Exception as e:
                print(f"    Error building connections for route {route_id}: {e}")
                continue
        
        # Convert to list and add helpful metadata
        stations_list = list(stations.values())
        
        # Sort by name for easier reading
        stations_list.sort(key=lambda s: s["name"])
        
        # Verify branching routes (e.g., Providence/Stoughton)
        print("\nVerifying route branches...")
        for route_id, route_info in routes.items():
            if route_info["type"] == 2:  # Commuter Rail
                route_stations = [s for s in stations_list if route_id in s["route_ids"]]
                branch_stations = []  # Stations that connect to multiple next stations
                
                for station in route_stations:
                    route_connections = [c for c in station["connections"] if c["route_id"] == route_id]
                    if len(route_connections) > 2:  # More than bidirectional = branch point
                        branch_stations.append(station["name"])
                
                if branch_stations:
                    print(f"  {route_info['display_name']}: Branch points at {', '.join(branch_stations)}")
        
        print(f"\nData Summary:")
        print(f"  Total Routes: {len(routes)} (Mattapan excluded)")
        print(f"  Total Stations: {len(stations_list)}")
        
        # Count by line
        line_counts = {}
        for station in stations_list:
            for line in station["lines"]:
                line_counts[line] = line_counts.get(line, 0) + 1
        
        print(f"\nStations by line:")
        for line, count in sorted(line_counts.items()):
            print(f"  • {line}: {count} stations")
        
        return {
            "metadata": {
                "downloaded_at": None,
                "source": "MBTA API v3",
                "api_url": "https://api-v3.mbta.com",
                "total_stations": len(stations_list),
                "total_routes": len(routes),
                "excluded_routes": EXCLUDED_ROUTES,
                "note": "Mattapan Trolley excluded from this dataset"
            },
            "routes": routes,
            "stations": stations_list
        }

async def main():
    """
    Main function to download and save MBTA data.
    """
    
    print("=" * 60)
    print("MBTA Data Downloader")
    print("Excludes: Mattapan Trolley")
    print("=" * 60)
    print()
    
    # Get API key
    api_key = os.environ.get("MBTA_API_KEY")
    
    if not api_key:
        print("MBTA API key required!")
        print()
        print("Get a free key at: https://api-v3.mbta.com/")
        print()
        api_key = input("Enter your MBTA API key: ").strip()
        
        if not api_key:
            print("Error: API key is required")
            return
    
    print()
    
    try:
        # Fetch data
        data = await fetch_mbta_data(api_key)
        
        # Add timestamp
        from datetime import datetime
        data["metadata"]["downloaded_at"] = datetime.now().isoformat()
        
        # Save to data folder
        os.makedirs("data", exist_ok=True)
        
        output_file = "data/mbta_stations.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        
        print()
        print("=" * 60)
        print(f"✓ Data saved to: {output_file}")
        print("=" * 60)
        print()
        print("Sample stations:")
        for station in data["stations"][:10]:
            wheelchair = "♿" if station["wheelchair_boarding"] == 1 else ""
            print(f"  • {station['name']} {wheelchair}")
            print(f"    Lines: {', '.join(station['lines'])}")
            print(f"    Location: {station['latitude']:.6f}, {station['longitude']:.6f}")
            if station.get("municipality"):
                print(f"    Municipality: {station['municipality']}")
            print(f"    Connections: {len(station['connections'])} stations")
            print()
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print()
            print("ERROR: 403 Forbidden - Invalid or missing API key")
            print()
            print("Get a free API key at: https://api-v3.mbta.com/")
        else:
            print(f"HTTP Error: {e}")
            print(f"URL: {e.request.url}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())