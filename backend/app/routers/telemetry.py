from typing import Any
from fastapi import APIRouter, Path, Query
from app.database.repository import repo
from app.mqtt_client import mqtt_service

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Analytics"])


@router.get("/{device_id}/history", summary="Get historical telemetry time-series")
async def get_device_telemetry_history(
    device_id: str = Path(..., description="Device identifier"),
    limit: int = Query(default=60, ge=5, le=500, description="Number of historical samples"),
):
    """
    Returns time-series telemetry points (RSSI, Heap, LoadAvg, Power states)
    for rendering telemetry and energy analytics graphs.
    """
    history = await repo.get_recent_telemetry(device_id, limit=limit)
    return {
        "device_id": device_id,
        "count": len(history),
        "data": history,
    }


@router.get("/{device_id}/stats", summary="Get aggregated metrics and uptime stats")
async def get_device_telemetry_stats(
    device_id: str = Path(..., description="Device identifier")
):
    """
    Returns statistical aggregates (avg/min/max RSSI, average heap memory, total samples).
    """
    history = await repo.get_recent_telemetry(device_id, limit=100)
    if not history:
        device = mqtt_service.get_device(device_id)
        curr_rssi = device.state.get("Wifi", {}).get("RSSI") if device.state else None
        curr_heap = device.state.get("Heap") if device.state else None
        return {
            "device_id": device_id,
            "samples": 0,
            "current": {"rssi": curr_rssi, "heap": curr_heap},
            "averages": {"rssi": curr_rssi, "heap": curr_heap},
        }

    rssi_vals = [h["rssi"] for h in history if h.get("rssi") is not None]
    heap_vals = [h["heap"] for h in history if h.get("heap") is not None]

    return {
        "device_id": device_id,
        "samples": len(history),
        "rssi": {
            "current": rssi_vals[-1] if rssi_vals else None,
            "average": round(sum(rssi_vals) / len(rssi_vals), 1) if rssi_vals else None,
            "min": min(rssi_vals) if rssi_vals else None,
            "max": max(rssi_vals) if rssi_vals else None,
        },
        "heap_kb": {
            "current": heap_vals[-1] if heap_vals else None,
            "average": round(sum(heap_vals) / len(heap_vals), 1) if heap_vals else None,
            "min": min(heap_vals) if heap_vals else None,
            "max": max(heap_vals) if heap_vals else None,
        },
    }
