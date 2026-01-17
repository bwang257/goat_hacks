from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from .routers import transfers, gemini

load_dotenv()

app = FastAPI(title="MBTA Transfer Helper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transfers.router)
app.include_router(gemini.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mbta-transfer-helper"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
