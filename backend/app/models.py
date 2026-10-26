from typing import Any, Optional
from pydantic import BaseModel, Field


class ModuleControl(BaseModel):
    id: str = Field(..., description="Unique control ID for frontend, e.g. relay_1, relay_2, dimmer")
    name: str = Field(..., description="Display label, e.g. Relay 1, Relay 2, Dimmer")
    type: str = Field(default="switch", description="UI control type: 'switch', 'slider', 'button', 'color'")
    command: str = Field(..., description="Tasmota MQTT command, e.g. POWER1, POWER2, Dimmer")
    state: Any | None = Field(default=None, description="Current live state (e.g. 'ON', 'OFF', 50)")
    gpio: str | None = Field(default=None, description="Assigned hardware GPIO pin, e.g. GPIO0")
    actions: list[str] | None = Field(
        default=None,
        description="Permitted actions/values, e.g. ['ON', 'OFF', 'TOGGLE']",
    )
    min: float | None = Field(default=None, description="Minimum numeric value if type is slider")
    max: float | None = Field(default=None, description="Maximum numeric value if type is slider")


class GenericControlRequest(BaseModel):
    target: str = Field(
        ...,
        description="Control identifier (e.g. 'relay_1', 'relay_2') or direct command name (e.g. 'POWER1', 'Dimmer')",
        examples=["relay_1", "relay_2", "POWER1"],
    )
    value: Any = Field(
        default="TOGGLE",
        description="Value or action to apply (e.g. 'TOGGLE', 'ON', 'OFF', 50)",
        examples=["TOGGLE", "ON", "OFF"],
    )


class GenericControlResponse(BaseModel):
    success: bool
    device_id: str
    target: str
    command: str
    value: Any
    new_state: Any | None = None
    response: Any | None = None
    response_topic: str | None = None
    message: str


class CustomCommandRequest(BaseModel):
    command: str = Field(
        ...,
        description="Tasmota command name (e.g. POWER1, POWER2, STATUS, Dimmer, Module, Gpio)",
        examples=["POWER1", "POWER2", "STATUS", "Module", "Gpio"],
    )
    payload: str = Field(
        default="",
        description="Payload or argument for the command (e.g. '0', '1', 'ON', 'TOGGLE')",
        examples=["ON", "TOGGLE", "0"],
    )


class DeviceMetadataUpdate(BaseModel):
    custom_name: Optional[str] = None
    room: Optional[str] = None
    device_type: Optional[str] = None
    icon: Optional[str] = None
    is_favorite: Optional[bool] = None


class DeviceState(BaseModel):
    device_id: str
    online: bool = True
    custom_name: Optional[str] = None
    room: Optional[str] = "General"
    device_type: Optional[str] = "tasmota_switch"
    icon: Optional[str] = "hub"
    is_favorite: bool = False
    power: str | None = None
    powers: dict[str, str] = Field(
        default_factory=dict,
        description="Current power states for POWER, POWER1, POWER2, etc.",
    )
    controls: list[ModuleControl] = Field(
        default_factory=list,
        description="UI-ready controllable modules/relays",
    )
    state: dict[str, Any] | None = Field(
        default=None,
        description="Latest tele/STATE telemetry (Wifi, Uptime, IP, Heap, POWER1/2/3)",
    )
    module: dict[str, Any] | str | None = None
    sensors: dict[str, Any] | None = None
    gpio: dict[str, Any] | None = None
    hardware: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
    raw_details: dict[str, Any] | None = None
    last_seen: str | None = None


class ModuleInfoResponse(BaseModel):
    device_id: str
    online: bool = True
    custom_name: Optional[str] = None
    room: Optional[str] = "General"
    module: dict[str, Any] | str | None = Field(
        default=None,
        description="Active Tasmota module name/ID",
    )
    controls: list[ModuleControl] = Field(
        default_factory=list,
        description="UI-ready controls for all detected modules/switches/relays",
    )
    gpio: dict[str, Any] | None = Field(
        default=None,
        description="Configured GPIO pins and assigned modules (Relay1, Relay2, Button, etc.)",
    )
    sensors: dict[str, Any] | None = Field(
        default=None,
        description="Connected sensors and their latest readings",
    )
    hardware: dict[str, Any] | None = Field(
        default=None,
        description="Microcontroller chip, hardware type, and firmware information",
    )
    raw_details: dict[str, Any] | None = Field(
        default=None,
        description="Complete raw Tasmota STATUS responses",
    )
    refreshed: bool = Field(
        default=False,
        description="Whether data was freshly received from device in this request",
    )
    message: str = "Success"


class CommandResponse(BaseModel):
    success: bool
    device_id: str
    command: str
    payload: str
    topic: str
    response: Any | None = Field(
        default=None,
        description="The live response payload received from the device (e.g. StatusSTS, RESULT, POWER state)",
    )
    response_topic: str | None = Field(
        default=None,
        description="The MQTT topic on which the device replied (e.g. stat/.../STATUS11, stat/.../RESULT)",
    )
    message: str


class BrokerStatus(BaseModel):
    connected: bool
    host: str
    port: int
    tracked_devices_count: int
    devices: list[str]


# ------------------ AI & Copilot Models ------------------

class AIChatRequest(BaseModel):
    prompt: str = Field(..., description="User message or natural language voice/chat command")
    device_id: Optional[str] = Field(None, description="Optional target device ID, defaults to active device")
    provider: Optional[str] = Field(None, description="Optional override: 'ollama', 'groq', or 'builtin'")


class AIChatResponse(BaseModel):
    response: str
    model: str
    device_id: Optional[str] = None
    actions_executed: list[dict[str, Any]] = Field(default_factory=list)
    suggested_prompts: list[str] = Field(default_factory=list)
    timestamp: str


class AIDiagnosticsResponse(BaseModel):
    device_id: str
    health_score: int = Field(..., ge=0, le=100, description="Overall health score out of 100")
    status_level: str = Field(..., description="Rating: 'Optimal', 'Good', 'Warning', 'Critical'")
    metrics: dict[str, Any]
    anomalies: list[dict[str, Any]]
    recommendations: list[str]
    ai_summary: str
    model_used: str
    timestamp: str


class AIRuleGenerateRequest(BaseModel):
    prompt: str = Field(..., description="Natural language description of desired automation")


class AIRuleGenerateResponse(BaseModel):
    rule: dict[str, Any]
    explanation: str
    model_used: str


# ------------------ Automations & Scenes ------------------

class AutomationRuleModel(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    trigger_type: str = Field(..., description="'time', 'threshold', or 'device_state'")
    trigger_config: dict[str, Any] | str
    action_config: list[dict[str, Any]] | str
    enabled: bool = True
    last_triggered: Optional[str] = None
    created_at: Optional[str] = None


class AutomationToggleRequest(BaseModel):
    enabled: bool


class SceneExecuteRequest(BaseModel):
    scene_id: str
    actions: Optional[list[dict[str, Any]]] = None
