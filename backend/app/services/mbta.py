import httpx
import os
from datetime import datetime
from typing import List, Dict
import asyncio

MBTA_API_KEY = os.getenv("MBTA_API_KEY")
BASE_URL = "https://api-v3.mbta.com"


async def get_predictions(stop_id: str, route_id: str) -> List[Dict]:
    """
    Fetch real-time predictions from MBTA V3 API.
    Returns next 3 predictions sorted by arrival time.
    """
    async with httpx.AsyncClient() as client:
        headers = {}
        if MBTA_API_KEY:
            headers["x-api-key"] = MBTA_API_KEY
        
        try:
            response = await client.get(
                f"{BASE_URL}/predictions",
                params={
                    "filter[stop]": stop_id,
                    "filter[route]": route_id,
                    "sort": "arrival_time",
                    "page[limit]": 3
                },
                headers=headers,
                timeout=5.0
            )
            
            if response.status_code != 200:
                raise Exception(f"MBTA API error: {response.status_code}")
            
            data = response.json()
            predictions = []
            
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                arrival = attrs.get("arrival_time")
                if not arrival:
                    continue
                
                predictions.append({
                    "route": route_id,
                    "direction": str(attrs.get("direction_id", "")),
                    "arrival_time": arrival,
                    "vehicle_id": attrs.get("vehicle", {}).get("id") if attrs.get("vehicle") else None
                })
            
            return predictions[:3]
        
        except httpx.TimeoutException:
            # Retry once on timeout
            await asyncio.sleep(0.5)
            return await get_predictions(stop_id, route_id)
        except Exception as e:
            print(f"Error fetching MBTA predictions: {e}")
            return []
