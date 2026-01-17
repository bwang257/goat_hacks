from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import httpx
import math

app = FastAPI(title="MBTA Walking Time API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WalkingTimeRequest(BaseModel):
    lat1: float
    lng1: float
    lat2: float
    lng2: float
    walking_speed_kmh: float = 5.0  # Default walking speed
    
    @field_validator('lat1', 'lat2')
    @classmethod
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @field_validator('lng1', 'lng2')
    @classmethod
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v
    
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

@app.get("/")
async def root():
    return {"message": "MBTA Walking Time API - OSRM routing with custom walking speed"}

@app.post("/api/walking-time", response_model=WalkingTimeResponse)
async def get_walking_time(request: WalkingTimeRequest):
    """
    Calculate walking time between two points.
    
    Uses OSRM to get the actual walking route distance (accounting for streets,
    sidewalks, etc.), then calculates time based on your specified walking speed.
    
    Common walking speeds:
    - 3-4 km/h: Slow, leisurely pace
    - 5 km/h: Normal pace (default)
    - 6-7 km/h: Brisk, purposeful pace
    - 7-8 km/h: Fast walking
    """
    try:
        # Get route distance from OSRM
        # OSRM expects coordinates as: longitude,latitude
        url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{request.lng1},{request.lat1};{request.lng2},{request.lat2}?overview=false"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        
        # Check if route was found
        if data.get("code") != "Ok":
            raise HTTPException(
                status_code=404, 
                detail=f"No walking route found. OSRM error: {data.get('message', 'Unknown error')}"
            )
        
        if not data.get("routes") or len(data["routes"]) == 0:
            raise HTTPException(
                status_code=404,
                detail="No routes returned by OSRM"
            )
        
        # Get the route distance in meters
        route = data["routes"][0]
        distance_meters = route["distance"]
        
        # Calculate walking time based on user's speed
        # Convert speed from km/h to m/s: km/h × 1000 / 3600
        speed_ms = request.walking_speed_kmh * 1000 / 3600
        
        # Time = Distance / Speed
        duration_seconds = distance_meters / speed_ms
        
        # Round up to nearest minute
        duration_minutes = math.ceil(duration_seconds / 60)
        
        return WalkingTimeResponse(
            duration_minutes=duration_minutes,
            duration_seconds=round(duration_seconds, 1),
            distance_meters=round(distance_meters, 1),
            distance_km=round(distance_meters / 1000, 3),
            walking_speed_kmh=request.walking_speed_kmh
        )
    
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="OSRM routing service timed out. Please try again."
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"OSRM service error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)