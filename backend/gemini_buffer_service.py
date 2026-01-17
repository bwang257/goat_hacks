from google import genai
import os

# The client gets the API key from the environment variable `GEMINI_API_KEY`. 

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key = api_key)

def processRequest(client, from_station, to_station, walking_speed, departure_time):
    # Early exit saves API calls (and money/quota)
    prompt = f"MBTA: {from_station}->{to_station} @ {departure_time}. Walking speed: {walking_speed}. Reply with a single integer value for conservative buffer for transfer/walking."

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        
        # Simple extraction
        buffer = int(response.text)
        return buffer
        
    except Exception as e:
        # Check specifically for rate limits
        if "429" in str(e):
            print("Rate limit hit - using fallback")
        else: print("Error:", str(e))
        return 7

# Tests
print(processRequest(client, "Kendall/MIT", "Mansfield", "average", "16:45"))
print(processRequest(client, "Kendall/MIT", "Mansfield", "fast", "16:45"))
print(processRequest(client, "Medford/Tufs", "Mansfield", "slow", "16:45"))

