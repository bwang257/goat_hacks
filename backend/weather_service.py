"""
Weather Service for MBTA Route Finder

Fetches current weather conditions from Weather.gov API (no key required)
and calculates adjustment multipliers for walking time based on weather conditions.
"""

import httpx
from typing import Dict, Optional
from datetime import datetime, timezone
import math


class WeatherService:
    """Service for fetching weather and calculating walking time adjustments."""
    
    def __init__(self):
        self.base_url = "https://api.weather.gov"
        self.boston_lat = 42.3601
        self.boston_lng = -71.0589
        self._cache: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 900  # 15 minutes cache
        
    async def _get_grid_point(self) -> Optional[Dict]:
        """Get the grid point for Boston coordinates."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First, get the grid endpoint URL
                url = f"{self.base_url}/points/{self.boston_lat},{self.boston_lng}"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                return data.get("properties", {})
        except Exception as e:
            print(f"Error fetching grid point: {e}")
            return None
    
    async def get_current_weather(self) -> Optional[Dict]:
        """Fetch current weather conditions for Boston area."""
        # Check cache first
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_time:
            cache_age = (now - self._cache_time).total_seconds()
            if cache_age < self._cache_ttl_seconds:
                return self._cache
        
        try:
            grid_props = await self._get_grid_point()
            if not grid_props:
                return None
            
            grid_id = grid_props.get("gridId")
            grid_x = grid_props.get("gridX")
            grid_y = grid_props.get("gridY")
            
            if not all([grid_id, grid_x, grid_y]):
                return None
            
            # Get current observations
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/gridpoints/{grid_id}/{grid_x},{grid_y}/observations/latest"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                properties = data.get("properties", {})
                weather_data = {
                    "temperature": properties.get("temperature", {}).get("value"),
                    "dewpoint": properties.get("dewpoint", {}).get("value"),
                    "wind_speed": properties.get("windSpeed", {}).get("value"),
                    "wind_direction": properties.get("windDirection", {}).get("value"),
                    "barometric_pressure": properties.get("barometricPressure", {}).get("value"),
                    "visibility": properties.get("visibility", {}).get("value"),
                    "text_description": properties.get("textDescription", ""),
                    "precipitation_last_hour": properties.get("precipitationLastHour", {}).get("value"),
                    "timestamp": properties.get("timestamp"),
                }
                
                # Cache the result
                self._cache = weather_data
                self._cache_time = now
                
                return weather_data
                
        except Exception as e:
            print(f"Error fetching weather: {e}")
            return None
    
    def calculate_weather_adjustment(self, weather_data: Optional[Dict]) -> float:
        """
        Calculate walking time adjustment multiplier based on weather conditions.
        
        Returns:
            float: Multiplier (1.0 = no adjustment, 1.1 = +10%, 1.2 = +20%, etc.)
        """
        if not weather_data:
            return 1.0
        
        adjustment = 1.0
        
        # Convert temperature from Celsius to Fahrenheit if needed
        temp_c = weather_data.get("temperature")
        temp_f = None
        if temp_c is not None:
            # Weather.gov provides temperature in Celsius
            temp_f = (temp_c * 9/5) + 32
        
        # Check precipitation (in millimeters)
        precipitation = weather_data.get("precipitation_last_hour")
        text_desc = weather_data.get("text_description", "").lower()
        
        # Heavy rain/snow detection
        if precipitation is not None and precipitation > 2.5:  # > 2.5mm = heavy
            adjustment = 1.2  # +20%
        elif precipitation is not None and precipitation > 0.5:  # 0.5-2.5mm = light
            adjustment = 1.1  # +10%
        elif any(word in text_desc for word in ["heavy", "rain", "snow", "thunderstorm", "blizzard"]):
            adjustment = 1.2  # +20%
        elif any(word in text_desc for word in ["light rain", "drizzle", "snow", "sleet"]):
            adjustment = 1.1  # +10%
        
        # Temperature extremes (only apply if no precipitation adjustment)
        if adjustment == 1.0 and temp_f is not None:
            if temp_f < 20:  # Extreme cold
                adjustment = 1.05  # +5%
            elif temp_f > 90:  # Extreme heat
                adjustment = 1.05  # +5%
        
        return adjustment
    
    async def get_weather_adjustment(self) -> float:
        """Get current weather and return adjustment multiplier."""
        weather_data = await self.get_current_weather()
        return self.calculate_weather_adjustment(weather_data)


# Singleton instance
_weather_service: Optional[WeatherService] = None

async def get_weather_service() -> WeatherService:
    """Get or create weather service singleton."""
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service
