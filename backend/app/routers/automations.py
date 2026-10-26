from typing import Any
from fastapi import APIRouter, HTTPException, Path
from app.database.repository import repo
from app.models import AutomationRuleModel, AutomationToggleRequest
from app.mqtt_client import mqtt_service

router = APIRouter(prefix="/automations", tags=["Automations & Scenes"])

# Predefined Instant Scenes
STANDARD_SCENES = {
    "all_on": {
        "id": "all_on",
        "name": "All Modules Active",
        "description": "Powers ON all relays across all devices",
        "icon": "lightbulb",
        "actions": [{"target": "POWER1", "value": "ON"}, {"target": "POWER2", "value": "ON"}, {"target": "POWER3", "value": "ON"}],
    },
    "all_off": {
        "id": "all_off",
        "name": "Full Energy Shutdown",
        "description": "Powers OFF all relays to reduce standby draw",
        "icon": "power_off",
        "actions": [{"target": "POWER1", "value": "OFF"}, {"target": "POWER2", "value": "OFF"}, {"target": "POWER3", "value": "OFF"}],
    },
    "eco_mode": {
        "id": "eco_mode",
        "name": "Eco Preservation Mode",
        "description": "Keeps primary relay active and powers down peripherals",
        "icon": "eco",
        "actions": [{"target": "POWER1", "value": "ON"}, {"target": "POWER2", "value": "OFF"}, {"target": "POWER3", "value": "OFF"}],
    },
    "alert_chime": {
        "id": "alert_chime",
        "name": "Diagnostic Audio Beacon",
        "description": "Triggers acoustic buzzer pulse on IoT hardware",
        "icon": "volume_up",
        "actions": [{"target": "buzzer", "value": "BEEP"}],
    },
}


@router.get("", summary="List all automations")
async def list_automations():
    """Returns all configured automation and trigger rules."""
    return await repo.get_automations()


@router.post("", summary="Create or update automation rule")
async def save_automation(body: AutomationRuleModel):
    """Saves a new or existing automation rule to the database."""
    res = await repo.upsert_automation(
        rule_id=body.id,
        name=body.name,
        description=body.description or "",
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        action_config=body.action_config,
        enabled=body.enabled,
    )
    return res


@router.post("/{rule_id}/toggle", summary="Enable or disable an automation")
async def toggle_automation(
    body: AutomationToggleRequest,
    rule_id: str = Path(..., description="Automation rule ID"),
):
    await repo.toggle_automation(rule_id, body.enabled)
    return {"id": rule_id, "enabled": body.enabled, "message": "Updated rule state"}


@router.delete("/{rule_id}", summary="Delete an automation rule")
async def delete_automation(rule_id: str = Path(..., description="Automation rule ID")):
    await repo.delete_automation(rule_id)
    return {"id": rule_id, "message": "Automation deleted"}


@router.get("/scenes", summary="List available smart scenes")
def list_scenes():
    return list(STANDARD_SCENES.values())


@router.post("/scenes/{scene_id}/trigger", summary="Trigger a smart scene immediately")
async def trigger_scene(
    scene_id: str = Path(..., description="Scene identifier: all_on, all_off, eco_mode, alert_chime")
):
    scene = STANDARD_SCENES.get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")

    dev_id = mqtt_service.get_default_device_id()
    executed = []
    for act in scene["actions"]:
        target = act["target"]
        val = act["value"]
        res = await mqtt_service.apply_control(dev_id, target, val)
        executed.append({
            "target": target,
            "value": val,
            "success": res.get("success", False),
            "new_state": res.get("new_state"),
        })

    await repo.log_audit(
        device_id=dev_id,
        action="SCENE_TRIGGER",
        target=scene_id,
        value="ACTIVE",
        source="scenes",
        status="SUCCESS",
        details=f"Triggered scene: {scene['name']}",
    )

    return {
        "scene_id": scene_id,
        "name": scene["name"],
        "device_id": dev_id,
        "actions_executed": executed,
        "message": f"Scene '{scene['name']}' activated successfully",
    }
