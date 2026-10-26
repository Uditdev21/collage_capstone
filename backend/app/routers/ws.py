import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.event_bus import event_bus
from app.mqtt_client import mqtt_service

logger = logging.getLogger("ws_router")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/live")
async def live_websocket_endpoint(websocket: WebSocket):
    """
    Real-time streaming WebSocket endpoint.
    Broadcasts live device telemetry, switch state changes, AI events, and automation triggers.
    """
    await event_bus.connect(websocket)
    try:
        # Send initial handshake with current devices state
        devices = mqtt_service.get_all_devices()
        await websocket.send_json({
            "event": "handshake",
            "message": "Connected to SmartDev Live WebSocket Bus",
            "broker_connected": mqtt_service.is_connected(),
            "devices": [
                {
                    "device_id": d.device_id,
                    "online": d.online,
                    "custom_name": d.custom_name,
                    "powers": d.powers,
                    "controls": [c.model_dump() for c in d.controls],
                    "state": d.state,
                }
                for d in devices
            ],
        })

        # Keep connection open and listen for any incoming client messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Handle client ping
                if msg.get("action") == "ping":
                    await websocket.send_json({"event": "pong", "time": msg.get("time")})
            except Exception:
                pass

    except WebSocketDisconnect:
        event_bus.disconnect(websocket)
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
        event_bus.disconnect(websocket)
