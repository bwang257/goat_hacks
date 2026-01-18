from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from route_planner import TransitGraph, Route
from realtime_same_line import RealtimeSameLineRouter
from mbta_client import MBTAClient
from multi_route_planner import MultiRoutePlanner
from dijkstra_router import DijkstraRouter

from typing import List
import httpx
import math
import json
import os
from typing import List, Optional
from datetime import datetime, timezone
import polyline

app = FastAPI(title="MBTA Walking Time API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load MBTA data on startup
MBTA_DATA = {}

# Initialize at startup
REALTIME_SAME_LINE = None
MBTA_CLIENT = None
MULTI_ROUTE_PLANNER = None
DIJKSTRA_ROUTER = None

async def get_mbta_client():
    """Get or create MBTA client"""
    global MBTA_CLIENT
    if MBTA_CLIENT is not None:
        return MBTA_CLIENT
    
    mbta_key = os.environ.get("MBTA_API_KEY")
    if mbta_key:
        MBTA_CLIENT = MBTAClient(mbta_key)
        print("✓ MBTA API client initialized")
    else:
        print("⚠️  MBTA_API_KEY not set - real-time features will be limited")
    
    return MBTA_CLIENT

async def get_realtime_router():
    """Lazy load the realtime router to ensure transit graph is loaded first"""
    global REALTIME_SAME_LINE
    if REALTIME_SAME_LINE is not None:
        return REALTIME_SAME_LINE
    
    mbta_key = os.environ.get("MBTA_API_KEY")
    if mbta_key and TRANSIT_GRAPH:
        try:
            REALTIME_SAME_LINE = RealtimeSameLineRouter(mbta_key, TRANSIT_GRAPH)
            print("✓ Real-time same-line router initialized")
        except Exception as e:
            print(f"Could not initialize real-time router: {e}")
    else:
        if not mbta_key:
            print("⚠️  MBTA_API_KEY not set")
        if not TRANSIT_GRAPH:
            print("⚠️  Transit graph not loaded")
    
    return REALTIME_SAME_LINE

async def get_multi_route_planner():
    """Get or create multi-route planner"""
    global MULTI_ROUTE_PLANNER
    if MULTI_ROUTE_PLANNER is not None:
        return MULTI_ROUTE_PLANNER
    
    mbta_client = await get_mbta_client()
    if mbta_client and TRANSIT_GRAPH:
        try:
            MULTI_ROUTE_PLANNER = MultiRoutePlanner(TRANSIT_GRAPH, mbta_client)
            print("✓ Multi-route planner initialized")
        except Exception as e:
            print(f"Could not initialize multi-route planner: {e}")
    
    return MULTI_ROUTE_PLANNER

@app.on_event("startup")
async def load_realtime_same_line():
    """Initialize realtime router at startup"""
    await get_realtime_router()
    await get_mbta_client()
    await get_multi_route_planner()

class NextTrainInfo(BaseModel):
    departure_time: str
    arrival_time: str
    minutes_until_departure: float
    total_trip_minutes: float
    status: str
    vehicle_id: Optional[str]
    countdown_text: str

class StationCoordinate(BaseModel):
    station_id: str
    station_name: str
    latitude: float
    longitude: float

class SameLineRouteResponse(BaseModel):
    line_name: str
    line_color: str
    from_station_name: str
    to_station_name: str
    direction_name: str
    scheduled_time_minutes: float
    distance_meters: float
    next_trains: List[NextTrainInfo]
    is_same_line: bool
    path_coordinates: Optional[List[StationCoordinate]] = None
    geometry_coordinates: Optional[List[List[float]]] = None

@app.get("/api/realtime/same-line")
async def get_realtime_same_line_route(
    station_id_1: str,
    station_id_2: str,
    num_trains: int = 3
):
    """
    Get real-time train predictions for same-line routes.
    Returns next N trains with live departure times.
    If MBTA API key is not available, returns basic same-line info.
    """
    
    # Check if stations are on the same line using transit graph
    if not TRANSIT_GRAPH:
        raise HTTPException(
            status_code=503,
            detail="Transit graph not loaded"
        )
    
    # Check if same line
    start_node = TRANSIT_GRAPH.nodes.get(station_id_1)
    end_node = TRANSIT_GRAPH.nodes.get(station_id_2)
    
    if not start_node or not end_node:
        raise HTTPException(
            status_code=404,
            detail="One or both stations not found"
        )
    
    start_lines = set(start_node.get("lines", []))
    end_lines = set(end_node.get("lines", []))
    shared_lines = start_lines & end_lines
    
    if not shared_lines:
        return {
            "is_same_line": False,
            "message": "Stations are not on the same line"
        }
    
    # Get the first shared line
    line_name = list(shared_lines)[0]
    
    # Get line color
    colors = {
        "Red": "DA291C",
        "Orange": "ED8B00",
        "Blue": "003DA5",
        "Green": "00843D",
    }
    
    # Extract base line name - handle Green Line branches (B, C, D, E)
    if "Green" in line_name or line_name in ["B", "C", "D", "E"]:
        base_line = "Green"
    else:
        base_line = line_name.split()[0]  # e.g., "Red" from "Red Line"
    
    line_color = colors.get(base_line, "000000")
    
    # Calculate distance
    lat1 = start_node.get("latitude", 0)
    lng1 = start_node.get("longitude", 0)
    lat2 = end_node.get("latitude", 0)
    lng2 = end_node.get("longitude", 0)
    
    distance = haversine_distance(lat1, lng1, lat2, lng2)
    scheduled_time = (distance / 1000) / 40 * 60  # Assume 40 km/h average
    
    # If real-time API available, use it
    router = await get_realtime_router()
    if router:
        try:
            route = await router.get_same_line_route(
                station_id_1,
                station_id_2,
                num_trains
            )
            
            if route:
                path_coords = [
                    StationCoordinate(
                        station_id=coord["station_id"],
                        station_name=coord["station_name"],
                        latitude=coord["latitude"],
                        longitude=coord["longitude"]
                    )
                    for coord in route.path_coordinates
                ] if route.path_coordinates else []

                # Calculate geometry shape
                geometry = None
                try:
                    # Determine route ID based on base line
                    potential_route_ids = []
                    
                    # Handle Green Line
                    if "Green" in line_name or line_name in ["B", "C", "D", "E"]:
                         potential_route_ids = ["Green-B", "Green-C", "Green-D", "Green-E"]
                    
                    # Handle Commuter Rail
                    elif "Line" in line_name and "/" in line_name:
                         # e.g. "Framingham/Worcester Line" -> try CR-Worcester, CR-Framingham
                         # Also handle "Fall River/New Bedford Line" -> CR-NewBedford
                         parts = line_name.replace(" Line", "").split("/")
                         potential_route_ids = [f"CR-{p.strip().replace(' ', '')}" for p in parts]
                         # Also try generic CR- + first word
                         potential_route_ids.append(f"CR-{parts[-1].strip().replace(' ', '')}")
                    elif "Line" in line_name and " " not in line_name.replace(" Line", ""):
                         # Simple CR lines like "Lowell Line" -> CR-Lowell
                         base = line_name.replace(" Line", "").strip()
                         potential_route_ids.append(f"CR-{base}")
                    else:
                         # Handle multi-word simple lines like "Greenbush Line" or "Kingston Line" (CR-Greenbush, CR-Kingston)
                         # Or "Fairmount Line" -> CR-Fairmount
                         # Or complex "Fall River/New Bedford" if it didn't catch above
                         base = line_name.replace(" Line", "").strip().replace(' ', '')
                         potential_route_ids.append(f"CR-{base}")
                    
                    # Explicit Needham fix
                    if "Needham" in line_name:
                         potential_route_ids.append("CR-Needham")
                    
                    # Fallback to simple split logic
                    base_simple = line_name.split()[0]
                    potential_route_ids.append(base_simple)
                    
                    print(f"DEBUG: Looking for geometry for {station_id_1} -> {station_id_2} on {line_name}")
                    print(f"DEBUG: Potential route IDs: {potential_route_ids}")

                    target_route_id = None
                    start_idx = None
                    end_idx = None

                    for rid in potential_route_ids:
                         idx_map = STATION_SHAPE_INDICES.get(rid, {})
                         start_mappings = idx_map.get(station_id_1, [])
                         end_mappings = idx_map.get(station_id_2, [])
                         
                         print(f"DEBUG: Checking route {rid}")
                         print(f"DEBUG: Start mappings: {start_mappings}")
                         print(f"DEBUG: End mappings: {end_mappings}")

                         # constant time intersection to find common shape
                         # start_mappings is list of (shape_idx, pt_idx)
                         
                         for (s_shape_idx, s_pt_idx) in start_mappings:
                             for (e_shape_idx, e_pt_idx) in end_mappings:
                                 if s_shape_idx == e_shape_idx:
                                     # Found a shape connecting both!
                                     target_route_id = rid
                                     start_idx = s_pt_idx
                                     end_idx = e_pt_idx
                                     found_shape_idx = s_shape_idx
                                     break
                             if target_route_id:
                                 break
                         
                         if target_route_id:
                             break
                    
                    if target_route_id:
                         all_shapes = ROUTE_SHAPES.get(target_route_id)
                         if all_shapes and found_shape_idx < len(all_shapes):
                             full_shape = all_shapes[found_shape_idx]
                             print(f"DEBUG: Found shape on {target_route_id} (idx {found_shape_idx}) with {len(full_shape)} points")
                             if start_idx <= end_idx:
                                 geometry = full_shape[start_idx:end_idx+1]
                             else:
                                 geometry = full_shape[end_idx:start_idx+1][::-1]
                             print(f"DEBUG: Sliced geometry has {len(geometry)} points")
                         else:
                             print("DEBUG: Shape lookup failed despite indices found (invalid shape index)")
                    else:
                        print("DEBUG: No matching route shape found connecting these stations")

                except Exception as e:
                    print(f"Error calculating same-line geometry: {e}")

                return SameLineRouteResponse(
                    line_name=route.line_name,
                    line_color=route.line_color,
                    from_station_name=route.from_station_name,
                    to_station_name=route.to_station_name,
                    direction_name=route.direction_name,
                    scheduled_time_minutes=route.scheduled_time_minutes,
                    distance_meters=route.distance_meters,
                    next_trains=route.next_trains,
                    is_same_line=True,
                    path_coordinates=path_coords,
                    geometry_coordinates=geometry
                )
        except Exception as e:
            print(f"Real-time API error: {e}")
    
    # Fallback: return basic same-line info without real-time data
    from datetime import datetime, timedelta
    now = datetime.now()

    # Get basic path (straight line between stations)
    path_coords = [
        StationCoordinate(
            station_id=station_id_1,
            station_name=start_node.get("name", station_id_1),
            latitude=start_node.get("latitude", 0),
            longitude=start_node.get("longitude", 0)
        ),
        StationCoordinate(
            station_id=station_id_2,
            station_name=end_node.get("name", station_id_2),
            latitude=end_node.get("latitude", 0),
            longitude=end_node.get("longitude", 0)
        )
    ]

    
    # Calculate geometry shape for fallback
    geometry = None
    try:
        # Determine route ID based on base line
        potential_route_ids = []
        
        # Handle Green Line
        if "Green" in line_name or line_name in ["B", "C", "D", "E"]:
             potential_route_ids = ["Green-B", "Green-C", "Green-D", "Green-E"]
        
        # Handle Commuter Rail
        elif "Line" in line_name and "/" in line_name:
             # e.g. "Framingham/Worcester Line" -> try CR-Worcester, CR-Framingham
             parts = line_name.replace(" Line", "").split("/")
             potential_route_ids = [f"CR-{p.strip().replace(' ', '')}" for p in parts]
             # Also try generic CR- + first word
             potential_route_ids.append(f"CR-{parts[-1].strip().replace(' ', '')}")
        elif "Line" in line_name and " " not in line_name.replace(" Line", ""):
             # Simple CR lines like "Lowell Line" -> CR-Lowell
             base = line_name.replace(" Line", "").strip()
             potential_route_ids.append(f"CR-{base}")
        else:
             base = line_name.replace(" Line", "").strip().replace(' ', '')
             potential_route_ids.append(f"CR-{base}")
        
        # Explicit Needham fix
        if "Needham" in line_name:
             potential_route_ids.append("CR-Needham")
        
        # Fallback to simple split logic
        base_simple = line_name.split()[0]
        potential_route_ids.append(base_simple)
        
        target_route_id = None
        start_idx = None
        end_idx = None
        found_shape_idx = None

        for rid in potential_route_ids:
             idx_map = STATION_SHAPE_INDICES.get(rid, {})
             start_mappings = idx_map.get(station_id_1, [])
             end_mappings = idx_map.get(station_id_2, [])

             for (s_shape_idx, s_pt_idx) in start_mappings:
                 for (e_shape_idx, e_pt_idx) in end_mappings:
                     if s_shape_idx == e_shape_idx:
                         target_route_id = rid
                         start_idx = s_pt_idx
                         end_idx = e_pt_idx
                         found_shape_idx = s_shape_idx
                         break
                 if target_route_id:
                     break
             if target_route_id:
                 break
        
        if target_route_id:
             all_shapes = ROUTE_SHAPES.get(target_route_id)
             if all_shapes and found_shape_idx < len(all_shapes):
                 full_shape = all_shapes[found_shape_idx]
                 if start_idx <= end_idx:
                     geometry = full_shape[start_idx:end_idx+1]
                 else:
                     geometry = full_shape[end_idx:start_idx+1][::-1]
    except Exception as e:
        print(f"Error calculating fallback geometry: {e}")

    return {
        "is_same_line": True,
        "line_name": line_name,
        "line_color": line_color,
        "from_station_name": start_node.get("name", station_id_1),
        "to_station_name": end_node.get("name", station_id_2),
        "direction_name": "Via " + line_name,
        "scheduled_time_minutes": scheduled_time,
        "distance_meters": distance,
        "next_trains": [
            {
                "departure_time": (now + timedelta(minutes=i*5+2)).isoformat(),
                "arrival_time": (now + timedelta(minutes=i*5+2+scheduled_time)).isoformat(),
                "minutes_until_departure": i*5+2,
                "total_trip_minutes": round(scheduled_time, 1),
                "status": "Estimated",
                "vehicle_id": None,
                "countdown_text": f"{i*5+2} min" if i > 0 else "Arriving"
            }
            for i in range(num_trains)
        ],
        "path_coordinates": path_coords,
        "geometry_coordinates": geometry
    }




@app.on_event("startup")
async def load_mbta_data():
    global MBTA_DATA
    try:
        data_file = os.path.join(os.path.dirname(__file__), "data", "mbta_stations.json")
        with open(data_file, "r") as f:
            MBTA_DATA = json.load(f)
        print(f"✓ Loaded {MBTA_DATA['metadata']['total_stations']} MBTA stations")
        print(f"  Downloaded: {MBTA_DATA['metadata']['downloaded_at']}")
    except FileNotFoundError:
        print("ERROR: mbta_stations.json not found!")
        print("Please run: python download_mbta_data.py")
        MBTA_DATA = {"routes": {}, "stations": [], "metadata": {}}

class StationInfo(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    lines: List[str]
    municipality: str
    wheelchair_boarding: int

class WalkingTimeRequest(BaseModel):
    station_id_1: str
    station_id_2: str
    walking_speed_kmh: float = 5.0
    
    @field_validator('walking_speed_kmh')
    @classmethod
    def validate_speed(cls, v):
        if not 0 < v <= 15:
            raise ValueError('Walking speed must be between 0 and 15 km/h')
        return v

class WalkingTimeResponse(BaseModel):
    duration_minutes: int
    duration_seconds: float
    distance_meters: float
    distance_km: float
    walking_speed_kmh: float
    station_1: StationInfo
    station_2: StationInfo
    geometry_coordinates: Optional[List[List[float]]] = None

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

# Add this endpoint with your other endpoints
@app.get("/api/stations/nearest")
async def get_nearest_station(lat: float, lng: float, limit: int = 5):
    """Find nearest stations to a coordinate"""
    stations = MBTA_DATA.get("stations", [])
    
    # Calculate distance to each station
    stations_with_distance = []
    for station in stations:
        distance = haversine_distance(lat, lng, station["latitude"], station["longitude"])
        stations_with_distance.append({
            "id": station["id"],
            "name": station["name"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "lines": station["lines"],
            "municipality": station.get("municipality", ""),
            "wheelchair_boarding": station.get("wheelchair_boarding", 0),
            "distance_meters": round(distance, 1)
        })
    
    # Sort by distance
    stations_with_distance.sort(key=lambda s: s["distance_meters"])
    
    return stations_with_distance[:limit]



def get_station_by_id(station_id: str) -> Optional[dict]:
    """Find station by ID"""
    for station in MBTA_DATA.get("stations", []):
        if station["id"] == station_id:
            return station
    return None

@app.get("/")
async def root():
    return {
        "message": "MBTA Walking Time API",
        "stations_loaded": len(MBTA_DATA.get("stations", [])),
        "routes_loaded": len(MBTA_DATA.get("routes", {})),
        "data_version": MBTA_DATA.get("metadata", {}).get("downloaded_at", "unknown")
    }

@app.get("/api/stations", response_model=List[StationInfo])
async def get_all_stations():
    """Get all MBTA stations"""
    return [
        StationInfo(
            id=s["id"],
            name=s["name"],
            latitude=s["latitude"],
            longitude=s["longitude"],
            lines=s["lines"],
            municipality=s.get("municipality", ""),
            wheelchair_boarding=s.get("wheelchair_boarding", 0)
        )
        for s in MBTA_DATA.get("stations", [])
    ]
    return results[:limit]

@app.get("/api/stations/search")
async def search_stations(query: str, limit: int = 20):
    """Search stations by name"""
    query_lower = query.lower()
    results = [
        StationInfo(
            id=s["id"],
            name=s["name"],
            latitude=s["latitude"],
            longitude=s["longitude"],
            lines=s["lines"],
            municipality=s.get("municipality", ""),
            wheelchair_boarding=s.get("wheelchair_boarding", 0)
        )
        for s in MBTA_DATA.get("stations", [])
        if query_lower in s["name"].lower()
    ]
    return results[:limit]

@app.get("/api/stations/{station_id}", response_model=StationInfo)
async def get_station(station_id: str):
    """Get a specific station by ID"""
    station = get_station_by_id(station_id)
    if not station:
        raise HTTPException(status_code=404, detail=f"Station not found: {station_id}")
    return StationInfo(
        id=station["id"],
        name=station["name"],
        latitude=station["latitude"],
        longitude=station["longitude"],
        lines=station["lines"],
        municipality=station.get("municipality", ""),
        wheelchair_boarding=station.get("wheelchair_boarding", 0)
    )

@app.get("/api/routes")
async def get_all_routes():
    """Get all routes/lines"""
    return MBTA_DATA.get("routes", {})

@app.post("/api/walking-time", response_model=WalkingTimeResponse)
async def get_walking_time(request: WalkingTimeRequest):
    """
    Calculate walking time between two MBTA stations using OSRM routing.
    """
    
    # Validate that both stations exist
    station1 = get_station_by_id(request.station_id_1)
    station2 = get_station_by_id(request.station_id_2)
    
    if not station1:
        raise HTTPException(
            status_code=404,
            detail=f"Station not found: {request.station_id_1}"
        )
    
    if not station2:
        raise HTTPException(
            status_code=404,
            detail=f"Station not found: {request.station_id_2}"
        )
    
    # Check if same station
    if request.station_id_1 == request.station_id_2:
        return WalkingTimeResponse(
            duration_minutes=0,
            duration_seconds=0.0,
            distance_meters=0.0,
            distance_km=0.0,
            walking_speed_kmh=request.walking_speed_kmh,
            station_1=StationInfo(
                id=station1["id"],
                name=station1["name"],
                latitude=station1["latitude"],
                longitude=station1["longitude"],
                lines=station1["lines"],
                municipality=station1.get("municipality", ""),
                wheelchair_boarding=station1.get("wheelchair_boarding", 0)
            ),
            station_2=StationInfo(
                id=station2["id"],
                name=station2["name"],
                latitude=station2["latitude"],
                longitude=station2["longitude"],
                lines=station2["lines"],
                municipality=station2.get("municipality", ""),
                wheelchair_boarding=station2.get("wheelchair_boarding", 0)
            )
        )
    
    try:
        # Get coordinates from stations
        lat1, lng1 = station1["latitude"], station1["longitude"]
        lat2, lng2 = station2["latitude"], station2["longitude"]
        
        # Get walking route from OSRM with geometry
        url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{lng1},{lat1};{lng2},{lat2}?overview=full"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        
        if data.get("code") != "Ok" or not data.get("routes"):
            raise HTTPException(
                status_code=404,
                detail=f"No walking route found between {station1['name']} and {station2['name']}"
            )
        
        # Get distance and calculate time
        route = data["routes"][0]
        distance_meters = route["distance"]
        
        # Calculate walking time based on user's speed
        speed_ms = request.walking_speed_kmh * 1000 / 3600
        duration_seconds = distance_meters / speed_ms
        duration_minutes = math.ceil(duration_seconds / 60)
        
        # Extract geometry if available
        geometry_coordinates = None
        if route.get("geometry"):
            # Decode polyline geometry (latitude, longitude pairs)
            geom = route["geometry"]
            if isinstance(geom, str):
                # Polyline-encoded format (default for OSRM)
                try:
                    decoded = polyline.decode(geom)
                    geometry_coordinates = [[lat, lng] for lat, lng in decoded]
                except Exception as e:
                    print(f"Error decoding polyline: {e}")
            elif isinstance(geom, dict) and geom.get("coordinates"):
                # GeoJSON format
                geometry_coordinates = [[lat, lng] for lng, lat in geom["coordinates"]]
            elif isinstance(geom, list):
                # Already a list of [lng, lat]
                geometry_coordinates = [[lat, lng] for lng, lat in geom]
        
        return WalkingTimeResponse(
            duration_minutes=duration_minutes,
            duration_seconds=round(duration_seconds, 1),
            distance_meters=round(distance_meters, 1),
            distance_km=round(distance_meters / 1000, 3),
            walking_speed_kmh=request.walking_speed_kmh,
            station_1=StationInfo(
                id=station1["id"],
                name=station1["name"],
                latitude=station1["latitude"],
                longitude=station1["longitude"],
                lines=station1["lines"],
                municipality=station1.get("municipality", ""),
                wheelchair_boarding=station1.get("wheelchair_boarding", 0)
            ),
            station_2=StationInfo(
                id=station2["id"],
                name=station2["name"],
                latitude=station2["latitude"],
                longitude=station2["longitude"],
                lines=station2["lines"],
                municipality=station2.get("municipality", ""),
                wheelchair_boarding=station2.get("wheelchair_boarding", 0)
            ),
            geometry_coordinates=geometry_coordinates
        )
    
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Routing service timed out"
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Routing service error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )

# Shape processing logic
ROUTE_SHAPES = {}  # route_id -> list of (list of coordinates)
STATION_SHAPE_INDICES = {}  # route_id -> {station_id -> list of (shape_idx, point_idx)}

def get_haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c * 1000  # meters

@app.on_event("startup")
async def process_route_shapes():
    """Map stations to indices on route shapes for accurate drawing"""
    global ROUTE_SHAPES, STATION_SHAPE_INDICES
    
    print("Processing route shapes...")
    raw_shapes = MBTA_DATA.get("shapes", {})
    stations = MBTA_DATA.get("stations", [])
    
    for route_id, shapes_list in raw_shapes.items():
        # Store ALL valid shapes, not just the longest one
        valid_shapes = []
        
        for shape in shapes_list:
            if "polyline" in shape:
                try:
                    coords = decode_polyline(shape["polyline"])
                    if len(coords) > 10: # Only store reasonably sized shapes
                        valid_shapes.append(coords)
                except:
                    pass
        
        if valid_shapes:
            ROUTE_SHAPES[route_id] = valid_shapes
            STATION_SHAPE_INDICES[route_id] = {}
            
            # Find all stations on this route
            route_stations = []
            for s in stations:
                if route_id in s["route_ids"]:
                    route_stations.append(s)
            
            # Map each station to ALL shapes it is close to
            for station in route_stations:
                st_lat, st_lon = station["latitude"], station["longitude"]
                
                # Check against every shape
                mappings = []
                for shape_idx, shape_coords in enumerate(valid_shapes):
                    min_dist = float('inf')
                    closest_idx = -1
                    
                    for pt_idx, (pt_lat, pt_lon) in enumerate(shape_coords):
                        dist = get_haversine_distance(st_lat, st_lon, pt_lat, pt_lon)
                        if dist < min_dist:
                            min_dist = dist
                            closest_idx = pt_idx
                    
                    # Only link if reasonably close (e.g. < 2000m) 
                    if min_dist < 2000: 
                        mappings.append((shape_idx, closest_idx))
                
                if mappings:
                    STATION_SHAPE_INDICES[route_id][station["id"]] = mappings

    print(f"✓ Processed shapes for {len(ROUTE_SHAPES)} routes (multi-shape supported)")

# Load transit graph on startup
TRANSIT_GRAPH = None

@app.on_event("startup")
async def load_transit_graph():
    global TRANSIT_GRAPH, DIJKSTRA_ROUTER
    try:
        graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
        TRANSIT_GRAPH = TransitGraph(graph_file)
        print(f"✓ Loaded transit graph with {len(TRANSIT_GRAPH.nodes)} stations")

        # Initialize Dijkstra router with same graph data
        with open(graph_file, 'r') as f:
            graph_data = json.load(f)
        DIJKSTRA_ROUTER = DijkstraRouter(graph_data['graph'])
        print(f"✓ Dijkstra router initialized")
    except Exception as e:
        print(f"Warning: Could not load transit graph: {e}")

class RouteSegmentResponse(BaseModel):
    from_station_id: str
    from_station_name: str
    to_station_id: str
    to_station_name: str
    type: str
    line: Optional[str]
    route_id: Optional[str]
    time_seconds: float
    time_minutes: float
    distance_meters: float
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    status: Optional[str] = None
    geometry_coordinates: Optional[List[List[float]]] = None
    transfer_rating: Optional[str] = None  # "likely", "risky", or "unlikely"
    slack_time_seconds: Optional[float] = None  # Slack time for transfers
    buffer_seconds: Optional[int] = None  # Required buffer time for transfers

class RouteResponse(BaseModel):
    segments: List[RouteSegmentResponse]
    total_time_seconds: float
    total_time_minutes: float
    total_distance_meters: float
    total_distance_km: float
    num_transfers: int
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    has_risky_transfers: bool = False  # True if any transfer is risky/unlikely
    alternatives: List['RouteResponse'] = []  # Alternative safer routes

class RouteRequest(BaseModel):
    station_id_1: str
    station_id_2: str
    prefer_fewer_transfers: bool = True
    departure_time: Optional[str] = None
    use_realtime: bool = True

@app.post("/api/route", response_model=RouteResponse)
async def find_route(
    request: RouteRequest
):
    """
    Find best route between two stations.
    Tries time-aware routing (MBTA API) first, falls back to static graph.
    """
    station_id_1 = request.station_id_1
    station_id_2 = request.station_id_2
    prefer_fewer_transfers = request.prefer_fewer_transfers
    departure_time = request.departure_time
    use_realtime = request.use_realtime
    
    if not TRANSIT_GRAPH:
        raise HTTPException(
            status_code=503,
            detail="Transit graph not loaded. Please run build_transit_graph.py first."
        )
    
    # Parse departure time
    dep_time = None
    if departure_time:
        try:
            dep_time = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
        except:
             raise HTTPException(
                status_code=400,
                detail="Invalid timestamp format"
             )
    else:
        dep_time = datetime.now(timezone.utc)
    
    # Use Dijkstra-based routing (fast, accurate)
    mbta_client = await get_mbta_client()
    route = None

    if not DIJKSTRA_ROUTER:
        raise HTTPException(
            status_code=503,
            detail="Dijkstra router not initialized. Please restart the server."
        )

    try:
        # NEW APPROACH: Use Dijkstra router (2-phase: pathfinding + real-time)
        route = await DIJKSTRA_ROUTER.find_route(
            start_station_id=station_id_1,
            end_station_id=station_id_2,
            departure_time=dep_time,
            mbta_client=mbta_client if use_realtime else None,
            debug=False
        )
    except Exception as e:
        print(f"Error in Dijkstra routing: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to old method
        if mbta_client and use_realtime:
            try:
                route = await TRANSIT_GRAPH.find_time_aware_path(
                    start_station_id=station_id_1,
                    end_station_id=station_id_2,
                    departure_time=dep_time,
                    mbta_client=mbta_client,
                    prefer_fewer_transfers=prefer_fewer_transfers,
                    max_transfers=3,
                    debug=False
                )
            except:
                pass

        # Final fallback to static routing
        if not route:
            route = TRANSIT_GRAPH.find_shortest_path(
                station_id_1,
                station_id_2,
                prefer_fewer_transfers
            )
    
    if not route:
        # Get station names for better error message
        start_name = TRANSIT_GRAPH.get_station_name(station_id_1)
        end_name = TRANSIT_GRAPH.get_station_name(station_id_2)
        print(f"WARNING: No route found between {start_name} ({station_id_1}) and {end_name} ({station_id_2})")
        raise HTTPException(
            status_code=404,
            detail=f"No route found between {start_name} and {end_name}"
        )

    # Check if route has risky transfers and suggest alternatives if needed
    has_risky_transfers = any(
        seg.transfer_rating in ["risky", "unlikely"]
        for seg in route.segments
        if seg.transfer_rating is not None
    )

    alternative_routes = []
    if has_risky_transfers and use_realtime and mbta_client:
        try:
            # Get 1 alternative route with safer transfers (only if primary route is risky)
            alt_routes = await DIJKSTRA_ROUTER.suggest_alternatives(
                primary_route=route,
                start_station_id=station_id_1,
                end_station_id=station_id_2,
                mbta_client=mbta_client,
                max_alternatives=1,  # Only return 1 safer alternative
                debug=False
            )
            alternative_routes = alt_routes[:1]  # Ensure only 1 alternative is included
        except Exception as e:
            print(f"Error finding alternative routes: {e}")
    # If primary route is safe (no risky transfers), alternatives array remains empty

    segments = []
    for seg in route.segments:
        seg_response = RouteSegmentResponse(
            from_station_id=seg.from_station,
            from_station_name=TRANSIT_GRAPH.get_station_name(seg.from_station) or "Unknown Station",
            to_station_id=seg.to_station,
            to_station_name=TRANSIT_GRAPH.get_station_name(seg.to_station) or "Unknown Station",
            type=seg.type,
            line=seg.line,
            route_id=seg.route_id,
            time_seconds=seg.time_seconds,
            time_minutes=round(seg.time_seconds / 60, 1),
            distance_meters=seg.distance_meters,
            departure_time=seg.departure_time.isoformat() if seg.departure_time else None,
            arrival_time=seg.arrival_time.isoformat() if seg.arrival_time else None,
            status=seg.status,
            geometry_coordinates=None, # Initialize as None, will be filled if applicable
            transfer_rating=seg.transfer_rating,
            slack_time_seconds=seg.slack_time_seconds,
            buffer_seconds=seg.buffer_seconds
        )
        
        if seg_response.type == "train" and seg_response.route_id:
             try:
                 # Attempt to find geometry
                 idx_map = STATION_SHAPE_INDICES.get(seg_response.route_id, {})
                 start_mappings = idx_map.get(seg_response.from_station_id, [])
                 end_mappings = idx_map.get(seg_response.to_station_id, [])
                 
                 target_shape = None
                 s_idx = None
                 e_idx = None
                 
                 # Find common shape
                 for (s_shape_idx, s_pt_idx) in start_mappings:
                     for (e_shape_idx, e_pt_idx) in end_mappings:
                         if s_shape_idx == e_shape_idx:
                             # Found match
                             all_shapes = ROUTE_SHAPES.get(seg_response.route_id, [])
                             if s_shape_idx < len(all_shapes):
                                 target_shape = all_shapes[s_shape_idx]
                                 s_idx = s_pt_idx
                                 e_idx = e_pt_idx
                             break
                     if target_shape:
                         break
                         
                 if target_shape:
                     if s_idx <= e_idx:
                         seg_response.geometry_coordinates = target_shape[s_idx:e_idx+1]
                     else:
                         seg_response.geometry_coordinates = target_shape[e_idx:s_idx+1][::-1]
             except Exception as e:
                 print(f"Error calculating geometry for segment: {e}")
        
        segments.append(seg_response)

    # Convert alternative routes to responses
    alternatives_response = []
    for alt_route in alternative_routes:
        alt_segments = []
        for seg in alt_route.segments:
            alt_seg = RouteSegmentResponse(
                from_station_id=seg.from_station,
                from_station_name=TRANSIT_GRAPH.get_station_name(seg.from_station) or "Unknown Station",
                to_station_id=seg.to_station,
                to_station_name=TRANSIT_GRAPH.get_station_name(seg.to_station) or "Unknown Station",
                type=seg.type,
                line=seg.line,
                route_id=seg.route_id,
                time_seconds=seg.time_seconds,
                time_minutes=round(seg.time_seconds / 60, 1),
                distance_meters=seg.distance_meters,
                departure_time=seg.departure_time.isoformat() if seg.departure_time else None,
                arrival_time=seg.arrival_time.isoformat() if seg.arrival_time else None,
                status=seg.status,
                geometry_coordinates=None,
                transfer_rating=seg.transfer_rating,
                slack_time_seconds=seg.slack_time_seconds,
                buffer_seconds=seg.buffer_seconds
            )
            alt_segments.append(alt_seg)

        alt_response = RouteResponse(
            segments=alt_segments,
            total_time_seconds=alt_route.total_time_seconds,
            total_time_minutes=round(alt_route.total_time_seconds / 60, 1),
            total_distance_meters=alt_route.total_distance_meters,
            total_distance_km=round(alt_route.total_distance_meters / 1000, 2),
            num_transfers=alt_route.num_transfers,
            departure_time=alt_route.departure_time.isoformat() if alt_route.departure_time else None,
            arrival_time=alt_route.arrival_time.isoformat() if alt_route.arrival_time else None,
            has_risky_transfers=False,
            alternatives=[]
        )
        alternatives_response.append(alt_response)
    
    return RouteResponse(
        segments=segments,
        total_time_seconds=route.total_time_seconds,
        total_time_minutes=round(route.total_time_seconds / 60, 1),
        total_distance_meters=route.total_distance_meters,
        total_distance_km=round(route.total_distance_meters / 1000, 2),
        num_transfers=route.num_transfers,
        departure_time=route.departure_time.isoformat() if route.departure_time else None,
        arrival_time=route.arrival_time.isoformat() if route.arrival_time else None,
        has_risky_transfers=has_risky_transfers,
        alternatives=alternatives_response
    )

@app.post("/api/route/alternatives", response_model=List[RouteResponse])
async def get_additional_alternatives(
    request: RouteRequest
):
    """
    Fetch additional alternative routes (2 more routes) when user clicks "Show More Options".
    Uses real-time MBTA API to find next available routes.
    """
    station_id_1 = request.station_id_1
    station_id_2 = request.station_id_2
    prefer_fewer_transfers = request.prefer_fewer_transfers
    departure_time = request.departure_time
    use_realtime = request.use_realtime
    
    if not TRANSIT_GRAPH:
        raise HTTPException(
            status_code=503,
            detail="Transit graph not loaded"
        )
    
    # Parse departure time
    dep_time = None
    if departure_time:
        try:
            dep_time = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
        except:
            raise HTTPException(status_code=400, detail="Invalid timestamp format")
    else:
        dep_time = datetime.now(timezone.utc)
    
    mbta_client = await get_mbta_client()
    
    if not DIJKSTRA_ROUTER:
        raise HTTPException(status_code=503, detail="Dijkstra router not initialized")
    
    # First, get the primary route to use as reference
    primary_route = None
    try:
        primary_route = await DIJKSTRA_ROUTER.find_route(
            start_station_id=station_id_1,
            end_station_id=station_id_2,
            departure_time=dep_time,
            mbta_client=mbta_client if use_realtime else None,
            debug=False
        )
    except Exception as e:
        print(f"Error getting primary route: {e}")
        raise HTTPException(status_code=500, detail=f"Error finding routes: {str(e)}")
    
    if not primary_route:
        raise HTTPException(status_code=404, detail="No route found")
    
    # Fetch additional alternatives (2 more routes)
    additional_alternatives = []
    if use_realtime and mbta_client:
        try:
            alt_routes = await DIJKSTRA_ROUTER.suggest_alternatives(
                primary_route=primary_route,
                start_station_id=station_id_1,
                end_station_id=station_id_2,
                mbta_client=mbta_client,
                max_alternatives=5,  # Fetch more to ensure we get 2 good alternatives
                debug=False
            )
            # Skip the first one (likely already shown) and take next 2
            additional_alternatives = alt_routes[1:3] if len(alt_routes) > 1 else alt_routes[:2]
        except Exception as e:
            print(f"Error finding additional alternatives: {e}")
    
    # Convert to response format
    alternatives_response = []
    for alt_route in additional_alternatives:
        alt_segments = []
        for seg in alt_route.segments:
            alt_seg = RouteSegmentResponse(
                from_station_id=seg.from_station,
                from_station_name=TRANSIT_GRAPH.get_station_name(seg.from_station) or "Unknown Station",
                to_station_id=seg.to_station,
                to_station_name=TRANSIT_GRAPH.get_station_name(seg.to_station) or "Unknown Station",
                type=seg.type,
                line=seg.line,
                route_id=seg.route_id,
                time_seconds=seg.time_seconds,
                time_minutes=round(seg.time_seconds / 60, 1),
                distance_meters=seg.distance_meters,
                departure_time=seg.departure_time.isoformat() if seg.departure_time else None,
                arrival_time=seg.arrival_time.isoformat() if seg.arrival_time else None,
                status=seg.status,
                geometry_coordinates=None,
                transfer_rating=seg.transfer_rating,
                slack_time_seconds=seg.slack_time_seconds,
                buffer_seconds=seg.buffer_seconds
            )
            
            # Calculate geometry for train segments
            if alt_seg.type == "train" and alt_seg.route_id:
                try:
                    idx_map = STATION_SHAPE_INDICES.get(alt_seg.route_id, {})
                    start_mappings = idx_map.get(alt_seg.from_station_id, [])
                    end_mappings = idx_map.get(alt_seg.to_station_id, [])
                    
                    target_shape = None
                    s_idx = None
                    e_idx = None
                    
                    for (s_shape_idx, s_pt_idx) in start_mappings:
                        for (e_shape_idx, e_pt_idx) in end_mappings:
                            if s_shape_idx == e_shape_idx:
                                all_shapes = ROUTE_SHAPES.get(alt_seg.route_id, [])
                                if s_shape_idx < len(all_shapes):
                                    target_shape = all_shapes[s_shape_idx]
                                    s_idx = s_pt_idx
                                    e_idx = e_pt_idx
                                break
                        if target_shape:
                            break
                    
                    if target_shape:
                        if s_idx <= e_idx:
                            alt_seg.geometry_coordinates = target_shape[s_idx:e_idx+1]
                        else:
                            alt_seg.geometry_coordinates = target_shape[e_idx:s_idx+1][::-1]
                except Exception as e:
                    print(f"Error calculating geometry for alternative segment: {e}")
            
            alt_segments.append(alt_seg)
        
        # Check if this alternative has risky transfers
        has_risky = any(
            seg.transfer_rating in ["risky", "unlikely"]
            for seg in alt_route.segments
            if seg.transfer_rating is not None
        )
        
        alt_response = RouteResponse(
            segments=alt_segments,
            total_time_seconds=alt_route.total_time_seconds,
            total_time_minutes=round(alt_route.total_time_seconds / 60, 1),
            total_distance_meters=alt_route.total_distance_meters,
            total_distance_km=round(alt_route.total_distance_meters / 1000, 2),
            num_transfers=alt_route.num_transfers,
            departure_time=alt_route.departure_time.isoformat() if alt_route.departure_time else None,
            arrival_time=alt_route.arrival_time.isoformat() if alt_route.arrival_time else None,
            has_risky_transfers=has_risky,
            alternatives=[]
        )
        alternatives_response.append(alt_response)
    
    return alternatives_response

@app.get("/api/route/realtime", response_model=RouteResponse)
async def find_realtime_route(
    station_id_1: str,
    station_id_2: str,
    prefer_fewer_transfers: bool = True,
    departure_time: Optional[str] = None
):
    """
    Find route using real-time MBTA predictions (always uses real-time data).
    Similar to /api/route but always uses real-time predictions.
    """
    return await find_route(
        station_id_1=station_id_1,
        station_id_2=station_id_2,
        prefer_fewer_transfers=prefer_fewer_transfers,
        departure_time=departure_time,
        use_realtime=True
    )



@app.get("/api/shapes")
async def get_shapes():
    """Get all route shapes"""
    raw_shapes = MBTA_DATA.get("shapes", {})
    
    # Process and decode polylines
    processed_shapes = {}
    
    for route_id, shapes_list in raw_shapes.items():
        # Filter out Silver Line routes (tunnel/bridge routes)
        # IDs: 741(SL1), 742(SL2), 743(SL3), 746(SL4), 749(SL5), 751(SL5)
        # Also check for "Silver" in name if available, but ID is safer.
        if route_id in ["741", "742", "743", "746", "749", "751"]:
            continue
            
        processed_shapes[route_id] = []
        for shape in shapes_list:
            if "polyline" in shape:
                try:
                    coords = decode_polyline(shape["polyline"])
                    processed_shapes[route_id].append({
                        "id": shape["id"],
                        "coordinates": coords,
                        "name": shape.get("name"),
                        "direction_id": shape.get("direction_id")
                    })
                except Exception as e:
                    print(f"Error decoding shape {shape['id']}: {e}")
    
    return processed_shapes

def decode_polyline(polyline_str):
    """Decodes a Polyline string into a list of lat/lng dicts."""
    index, lat, lng = 0, 0, 0
    coordinates = []
    changes = {'latitude': 0, 'longitude': 0}

    while index < len(polyline_str):
        for unit in ['latitude', 'longitude']:
            shift, result = 0, 0

            while True:
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20:
                    break

            if (result & 1):
                changes[unit] = ~(result >> 1)
            else:
                changes[unit] = (result >> 1)

        lat += changes['latitude']
        lng += changes['longitude']

        coordinates.append([lat / 100000.0, lng / 100000.0])

    return coordinates

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)