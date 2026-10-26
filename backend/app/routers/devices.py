from typing import Any
from fastapi import APIRouter, Path, Query
from app.config import settings
from app.database.repository import repo
from app.models import (
    CommandResponse,
    CustomCommandRequest,
    DeviceMetadataUpdate,
    DeviceState,
    GenericControlRequest,
    GenericControlResponse,
    ModuleInfoResponse,
)
from app.mqtt_client import mqtt_service

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[DeviceState], summary="List all devices")
async def list_devices():
    """
    HomeScreen: List all discovered and simulated devices.
    Returns status, online state, hardware, room metadata, and dynamic controls.
    """
    devices = mqtt_service.get_all_devices()
    meta_map = await repo.get_all_device_meta()
    for d in devices:
        if d.device_id in meta_map:
            m = meta_map[d.device_id]
            d.custom_name = m.get("custom_name") or d.device_id
            d.room = m.get("room") or "General"
            d.device_type = m.get("device_type") or "tasmota_switch"
            d.icon = m.get("icon") or "hub"
            d.is_favorite = bool(m.get("is_favorite", 0))
    return devices


@router.get("/{device_id}", response_model=DeviceState, summary="Get device status")
async def get_device(
    device_id: str = Path(
        ...,
        description="Device identifier",
        examples=[settings.DEFAULT_DEVICE_ID],
    )
):
    """DeviceScreen: Retrieve full status, online state, controls, and telemetry."""
    device = mqtt_service.get_device(device_id)
    meta = await repo.get_device_meta(device_id)
    if meta:
        device.custom_name = meta.get("custom_name") or device_id
        device.room = meta.get("room") or "General"
        device.device_type = meta.get("device_type") or "tasmota_switch"
        device.icon = meta.get("icon") or "hub"
        device.is_favorite = bool(meta.get("is_favorite", 0))
    return device


@router.patch("/{device_id}/metadata", summary="Update device metadata (name, room, icon, favorite)")
async def update_device_metadata(
    body: DeviceMetadataUpdate,
    device_id: str = Path(..., description="Device identifier"),
):
    """Update custom room, nickname, icon, or favorite flag for a device."""
    await repo.upsert_device_meta(
        device_id=device_id,
        custom_name=body.custom_name,
        room=body.room,
        device_type=body.device_type,
        icon=body.icon,
        is_favorite=body.is_favorite,
    )
    return {"device_id": device_id, "updated": True, "metadata": body.model_dump()}


@router.get(
    "/{device_id}/modules",
    response_model=ModuleInfoResponse,
    summary="Get connected modules, hardware, and dynamic UI controls",
)
async def get_device_modules(
    device_id: str = Path(
        ...,
        description="Device identifier",
        examples=[settings.DEFAULT_DEVICE_ID],
    ),
    refresh: bool = Query(
        default=True,
        description="Whether to query the device over MQTT for live status",
    ),
):
    """
    HomeScreen -> Device Tap:
    Returns the connected module, GPIO assignments, hardware details,
    and the complete list of dynamic UI controls (switches, buttons, buzzers, sliders).
    """
    if refresh:
        result = await mqtt_service.query_device_modules(device_id)
    else:
        device = mqtt_service.get_device(device_id)
        result = {
            "device_id": device_id,
            "online": device.online,
            "custom_name": device.custom_name,
            "room": device.room,
            "module": device.module,
            "controls": device.controls,
            "gpio": device.gpio,
            "sensors": device.sensors,
            "hardware": device.hardware,
            "raw_details": device.raw_details,
            "refreshed": False,
            "message": "Returned cached module details",
        }
    return ModuleInfoResponse(**result)


@router.post(
    "/{device_id}/control",
    response_model=GenericControlResponse,
    summary="Control any module, switch, button, buzzer, or slider",
)
async def control_device_module(
    body: GenericControlRequest,
    device_id: str = Path(
        ...,
        description="Device identifier",
        examples=[settings.DEFAULT_DEVICE_ID],
    ),
):
    """
    Universal control endpoint for mobile and web apps.
    Accepts target (e.g. 'relay_1', 'relay_2', 'buzzer', 'dimmer', or 'POWER1')
    and value (e.g. 'TOGGLE', 'ON', 'OFF', 'BEEP', 50).
    Waits for the device's live MQTT response and returns the updated state.
    """
    result = await mqtt_service.apply_control(device_id, body.target, body.value)
    # Record in audit log
    await repo.log_audit(
        device_id=device_id,
        action="USER_CONTROL",
        target=body.target,
        value=str(body.value),
        source="api",
        status="SUCCESS" if result.get("success") else "FAILED",
        details=result.get("message"),
    )
    return GenericControlResponse(**result)


@router.get(
    "/{device_id}/status",
    response_model=dict[str, Any],
    summary="Get device status by index (0=All, 1=PRM, 2=FWR, 5=NET, 8=SNS, 11=STS)",
)
async def get_device_status(
    device_id: str = Path(
        ...,
        description="Device identifier",
        examples=[settings.DEFAULT_DEVICE_ID],
    ),
    index: int = Query(
        default=0,
        ge=0,
        le=11,
        description="Tasmota STATUS index: 0=All, 1=PRM, 2=FWR, 3=LOG, 4=MEM, 5=NET, 6=MQT, 7=TIM, 8=SNS, 11=STS",
    ),
    refresh: bool = Query(
        default=True,
        description="Whether to query the device live over MQTT",
    ),
):
    """
    Query Tasmota status by index.
    When refresh=True (default), sends STATUS <index> live over MQTT,
    waits for the incoming stat/<device>/STATUS... message, and returns the live response.
    """
    if refresh:
        return await mqtt_service.query_device_status(device_id, index=index)
    device = mqtt_service.get_device(device_id)
    raw = device.raw_details or {}
    if index != 0:
        return raw.get(f"STATUS{index}", {})
    return {k: v for k, v in raw.items() if k.startswith("STATUS")} or raw


@router.post(
    "/{device_id}/command",
    response_model=CommandResponse,
    summary="Send custom Tasmota command and forward the live response",
)
async def send_custom_command(
    body: CustomCommandRequest,
    device_id: str = Path(
        ...,
        description="Device identifier",
        examples=[settings.DEFAULT_DEVICE_ID],
    ),
):
    """
    Send any custom Tasmota command (e.g. POWER1, Dimmer, Restart, etc.),
    wait for the device's live MQTT reply on stat/<device>/..., and forward the response.
    """
    result = await mqtt_service.execute_command(device_id, body.command, body.payload)
    await repo.log_audit(
        device_id=device_id,
        action="CUSTOM_COMMAND",
        target=body.command,
        value=body.payload,
        source="api",
        status="SUCCESS" if result.get("success") else "FAILED",
        details=result.get("message"),
    )
    return CommandResponse(**result)
