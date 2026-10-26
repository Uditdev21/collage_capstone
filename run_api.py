#!/usr/bin/env python3
"""
Launcher for SmartDev Tasmota REST API Adapter.
Runs Uvicorn server serving app.main:app.
"""

import sys
from pathlib import Path

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"Starting Tasmota MQTT REST API Adapter...")
    print(f"Server URL: http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"Interactive Swagger Docs: http://127.0.0.1:{settings.API_PORT}/docs")
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
