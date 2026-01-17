import google.generativeai as genai
import os
import json
import asyncio
import time
from typing import Dict

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Cache for responses (60-second TTL)
_cache: Dict[str, tuple] = {}
CACHE_TTL = 60


async def analyze_transfer_risk(
    station_name: str,
    math_confidence: str,
    current_time: str
) -> Dict:
    """
    Use Gemini to enhance confidence score with contextual analysis.
    """
    # Check cache
    cache_key = f"{station_name}:{math_confidence}:{current_time[:13]}"  # Cache by hour
    if cache_key in _cache:
        cached_result, cached_time = _cache[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            return cached_result
    
    prompt = f"""You are a Boston MBTA transit expert. Analyze this transfer scenario:

Station: {station_name}
Time: {current_time}
Base Math Confidence: {math_confidence}

Consider:
1. Historical crowding patterns at this hour
2. Station complexity (Park St is confusing, South Station is straightforward)
3. Typical delays on this route at this time

Return ONLY valid JSON (no markdown):
{{
  "adjusted_confidence": "LIKELY" | "RISKY" | "UNLIKELY",
  "reason": "brief explanation under 50 words",
  "pro_tip": "actionable advice under 30 words"
}}"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Run in executor to make it async and add timeout
        loop = asyncio.get_event_loop()
        
        def sync_generate():
            return model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0,
                    max_output_tokens=200
                )
            )
        
        response = await asyncio.wait_for(
            loop.run_in_executor(None, sync_generate),
            timeout=3.0
        )
        
        text = response.text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(text)
        
        # Cache the result
        _cache[cache_key] = (result, time.time())
        
        return result
    
    except asyncio.TimeoutError:
        # Fallback to base confidence
        return {
            "adjusted_confidence": math_confidence,
            "reason": "AI analysis timed out",
            "pro_tip": "Trust the math!"
        }
    except Exception as e:
        # Fallback to base confidence
        print(f"Gemini API error: {e}")
        return {
            "adjusted_confidence": math_confidence,
            "reason": "AI analysis unavailable",
            "pro_tip": "Trust the math!"
        }
