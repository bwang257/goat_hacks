from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from route_planner import TransitGraph, Route
from realtime_same_line import RealtimeSameLineRouter

from typing import List
import httpx
import math
import json
import os
from typing import List, Optional

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

@app.on_event("startup")
async def load_realtime_same_line():
    """Initialize realtime router at startup"""
    await get_realtime_router()

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
                    path_coordinates=path_coords
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
        "path_coordinates": path_coords
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
        
        # Get walking route from OSRM
        url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{lng1},{lat1};{lng2},{lat2}?overview=false"
        
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
            )
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

# Load transit graph on startup
TRANSIT_GRAPH = None

@app.on_event("startup")
async def load_transit_graph():
    global TRANSIT_GRAPH
    try:
        graph_file = os.path.join(os.path.dirname(__file__), "data", "mbta_transit_graph.json")
        TRANSIT_GRAPH = TransitGraph(graph_file)
        print(f"✓ Loaded transit graph with {len(TRANSIT_GRAPH.nodes)} stations")
    except Exception as e:
        print(f"Warning: Could not load transit graph: {e}")

class RouteSegmentResponse(BaseModel):
    from_station_id: str
    from_station_name: str
    to_station_id: str
    to_station_name: str
    type: str
    line: Optional[str]
    time_seconds: float
    time_minutes: float
    distance_meters: float

class RouteResponse(BaseModel):
    segments: List[RouteSegmentResponse]
    total_time_seconds: float
    total_time_minutes: float
    total_distance_meters: float
    total_distance_km: float
    num_transfers: int

@app.post("/api/route", response_model=RouteResponse)
async def find_route(
    station_id_1: str,
    station_id_2: str,
    prefer_fewer_transfers: bool = True
):
    """
    Find the fastest route between two stations using trains and walking.
    """
    if not TRANSIT_GRAPH:
        raise HTTPException(
            status_code=503,
            detail="Transit graph not loaded. Please run build_transit_graph.py first."
        )
    
    route = TRANSIT_GRAPH.find_shortest_path(
        station_id_1,
        station_id_2,
        prefer_fewer_transfers
    )
    
    if not route:
        raise HTTPException(
            status_code=404,
            detail=f"No route found between stations"
        )
    
    segments = [
        RouteSegmentResponse(
            from_station_id=seg.from_station,
            from_station_name=TRANSIT_GRAPH.get_station_name(seg.from_station),
            to_station_id=seg.to_station,
            to_station_name=TRANSIT_GRAPH.get_station_name(seg.to_station),
            type=seg.type,
            line=seg.line,
            time_seconds=seg.time_seconds,
            time_minutes=round(seg.time_seconds / 60, 1),
            distance_meters=seg.distance_meters
        )
        for seg in route.segments
    ]
    
    return RouteResponse(
        segments=segments,
        total_time_seconds=route.total_time_seconds,
        total_time_minutes=round(route.total_time_seconds / 60, 1),
        total_distance_meters=route.total_distance_meters,
        total_distance_km=round(route.total_distance_meters / 1000, 2),
        num_transfers=route.num_transfers
    )




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)