from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import httpx
import math
import json
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

@app.on_event("startup")
async def load_mbta_data():
    global MBTA_DATA
    try:
        with open("data/mbta_stations.json", "r") as f:
            MBTA_DATA = json.load(f)
        print(f"✓ Loaded {MBTA_DATA['metadata']['total_stations']} MBTA stations")
        print(f"  Downloaded: {MBTA_DATA['metadata']['downloaded_at']}")
    except FileNotFoundError:
        print("ERROR: data/mbta_stations.json not found!")
        print("Please run: python download_data.py")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)