from typing import Any, Optional
from fastapi import APIRouter, Query
from app.config import settings
from app.database.repository import repo
from app.models import BrokerStatus
from app.mqtt_client import mqtt_service

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/health", summary="Health check endpoint")
def health_check():
    """Returns REST API health and MQTT broker connection status."""
    return {
        "status": "ok",
        "mqtt_connected": mqtt_service.is_connected(),
        "version": settings.APP_VERSION,
    }


@router.get("/broker", response_model=BrokerStatus, summary="MQTT broker status")
def broker_status():
    """Returns active broker connection parameters and list of tracked devices."""
    devices = mqtt_service.get_all_devices()
    return BrokerStatus(
        connected=mqtt_service.is_connected(),
        host=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        tracked_devices_count=len(devices),
        devices=[d.device_id for d in devices],
    )


@router.get("/audit-logs", summary="Get system audit log")
async def get_audit_logs(
    limit: int = Query(default=50, ge=5, le=200),
    device_id: Optional[str] = Query(default=None),
):
    """Returns recent command executions, automation triggers, and user actions."""
    logs = await repo.get_audit_logs(limit=limit, device_id=device_id)
    return {"count": len(logs), "logs": logs}
