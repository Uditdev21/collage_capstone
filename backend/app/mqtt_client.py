import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional
import paho.mqtt.client as mqtt

# Ensure parent directory (backend/) is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.database.repository import repo
from app.event_bus import event_bus
from app.models import DeviceState, ModuleControl

logger = logging.getLogger("mqtt_adapter")


class MQTTService:
    def __init__(self):
        self.connected = False
        self._lock = Lock()
        self._waiters: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
        self._gpio_waiters: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
        self._state_waiters: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
        self._status_waiters: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
        self._cmd_waiters: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Future]]] = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        self.devices: dict[str, DeviceState] = {
            settings.DEFAULT_DEVICE_ID: DeviceState(
                device_id=settings.DEFAULT_DEVICE_ID,
                online=True,
                power=None,
                powers={},
                controls=[],
                state=None,
                module=None,
                sensors=None,
                gpio=None,
                hardware=None,
                telemetry=None,
                raw_details=None,
                last_seen=None,
            )
        }

        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            self.client = mqtt.Client()

        if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
            self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    def get_default_device_id(self) -> str:
        return settings.DEFAULT_DEVICE_ID

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT Broker (%s:%s)", settings.MQTT_HOST, settings.MQTT_PORT)
            topics = [
                ("stat/+/#", 0),
                ("tele/+/#", 0),
                (f"+/{settings.DEFAULT_DEVICE_ID}/#", 0),
            ]
            client.subscribe(topics)
            logger.info("Subscribed to Tasmota topics: %s", topics)
        else:
            self.connected = False
            logger.error("Failed to connect to MQTT broker. Code: %s", rc)

    def _on_disconnect(self, client, userdata, flags_or_rc, rc=None, properties=None):
        self.connected = False
        logger.warning("Disconnected from MQTT Broker")

    def _record_telemetry_async(self, device_id: str, payload: dict, device: DeviceState):
        if self._main_loop and self._main_loop.is_running():
            wifi = payload.get("Wifi", {}) if isinstance(payload.get("Wifi"), dict) else {}
            asyncio.run_coroutine_threadsafe(
                repo.record_telemetry(
                    device_id=device_id,
                    rssi=wifi.get("RSSI"),
                    signal=wifi.get("Signal"),
                    heap=payload.get("Heap"),
                    load_avg=payload.get("LoadAvg"),
                    uptime_sec=payload.get("UptimeSec"),
                    power_states=device.powers,
                    sensor_data=device.sensors,
                    raw_state=payload,
                ),
                self._main_loop,
            )

    def _extract_powers_from_dict(self, data: dict, target_powers: dict):
        for k, v in data.items():
            if k.upper().startswith("POWER") and isinstance(v, (str, int)):
                target_powers[k.upper()] = str(v).upper()

    def _build_device_controls(self, device: DeviceState) -> list[ModuleControl]:
        """
        Dynamically generate UI-ready control elements for any connected module
        (Relays, Buzzers, LEDs, PWM/Dimmers, Shutters, etc.) from detected GPIO pins and state.
        """
        controls: list[ModuleControl] = []
        seen_commands = set()

        # 1. Discover modules from GPIO configuration
        if device.gpio and isinstance(device.gpio, dict):
            for gpio_pin, pin_info in sorted(device.gpio.items()):
                if isinstance(pin_info, dict):
                    for func_name, code in pin_info.items():
                        func_lower = func_name.lower()
                        if func_lower == "none" or code == 0:
                            continue

                        # Relays
                        if "relay" in func_lower:
                            match = re.search(r"\d+", func_name)
                            idx = int(match.group()) if match else 1
                            cmd = f"POWER{idx}"
                            seen_commands.add(cmd)
                            curr_state = device.powers.get(cmd) or device.powers.get("POWER") or device.power
                            controls.append(
                                ModuleControl(
                                    id=f"relay_{idx}",
                                    name=f"Relay {idx}",
                                    type="switch",
                                    command=cmd,
                                    state=curr_state,
                                    gpio=gpio_pin,
                                    actions=["ON", "OFF", "TOGGLE"],
                                )
                            )

                        # Buzzer
                        elif "buzzer" in func_lower:
                            match = re.search(r"\d+", func_name)
                            idx = int(match.group()) if match else None
                            ctrl_id = f"buzzer_{idx}" if idx else "buzzer"
                            cmd = f"Buzzer{idx}" if (idx and idx > 1) else "Buzzer"
                            seen_commands.add(cmd)
                            controls.append(
                                ModuleControl(
                                    id=ctrl_id,
                                    name=f"Buzzer {idx}" if idx else "Buzzer",
                                    type="button",
                                    command=cmd,
                                    state="READY",
                                    gpio=gpio_pin,
                                    actions=["BEEP", "1", "2", "0"],
                                )
                            )

                        # LEDs
                        elif "led" in func_lower:
                            match = re.search(r"\d+", func_name)
                            idx = int(match.group()) if match else 1
                            cmd = f"LedPower{idx}" if idx else "LedPower"
                            seen_commands.add(cmd)
                            controls.append(
                                ModuleControl(
                                    id=f"led_{idx}",
                                    name=f"LED {idx}",
                                    type="switch",
                                    command=cmd,
                                    state=device.powers.get(cmd, "ON"),
                                    gpio=gpio_pin,
                                    actions=["ON", "OFF", "TOGGLE"],
                                )
                            )

                        # PWM (Dimmer channel)
                        elif "pwm" in func_lower:
                            match = re.search(r"\d+", func_name)
                            idx = int(match.group()) if match else 1
                            cmd = f"Channel{idx}"
                            seen_commands.add(cmd)
                            controls.append(
                                ModuleControl(
                                    id=f"pwm_{idx}",
                                    name=f"PWM {idx}",
                                    type="slider",
                                    command=cmd,
                                    state=0,
                                    gpio=gpio_pin,
                                    actions=None,
                                    min=0,
                                    max=100,
                                )
                            )

        # 2. Discover Relays from active powers if not already mapped by GPIO
        if device.powers:
            for p_key in sorted(device.powers.keys()):
                match = re.search(r"^POWER(\d+)$", p_key, re.IGNORECASE)
                if match:
                    cmd = p_key.upper()
                    if cmd not in seen_commands:
                        idx = int(match.group(1))
                        seen_commands.add(cmd)
                        controls.append(
                            ModuleControl(
                                id=f"relay_{idx}",
                                name=f"Relay {idx}",
                                type="switch",
                                command=cmd,
                                state=device.powers.get(cmd),
                                gpio=None,
                                actions=["ON", "OFF", "TOGGLE"],
                            )
                        )

        # 3. Check for Dimmer control
        raw = device.raw_details or {}
        dimmer_val = None
        for source in (device.state, device.telemetry, raw.get("STATUS", {}).get("Status")):
            if isinstance(source, dict) and "Dimmer" in source:
                dimmer_val = source["Dimmer"]
                break

        if dimmer_val is not None or "Dimmer" in seen_commands:
            controls.append(
                ModuleControl(
                    id="dimmer",
                    name="Brightness",
                    type="slider",
                    command="Dimmer",
                    state=dimmer_val,
                    actions=None,
                    min=0,
                    max=100,
                )
            )

        # 4. Fallback default single power switch if no controls mapped
        if not controls:
            controls.append(
                ModuleControl(
                    id="power",
                    name="Power Switch",
                    type="switch",
                    command="POWER",
                    state=device.power,
                    gpio=None,
                    actions=["ON", "OFF", "TOGGLE"],
                )
            )

        device.controls = controls
        return controls

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        raw_payload = msg.payload.decode("utf-8", errors="replace")
        now_str = datetime.now().isoformat()

        parts = topic.split("/")
        if len(parts) >= 3:
            prefix, device_id, action = parts[0], parts[1], "/".join(parts[2:])
        elif len(parts) == 2:
            prefix, device_id, action = parts[0], parts[1], ""
        else:
            return

        with self._lock:
            if device_id not in self.devices:
                self.devices[device_id] = DeviceState(device_id=device_id)

            device = self.devices[device_id]
            device.last_seen = now_str
            if device.raw_details is None:
                device.raw_details = {}

            # Parse LWT
            if action.upper() == "LWT":
                device.online = (raw_payload.strip().lower() == "online")

            # Parse direct power status on stat/.../POWER or POWER1, POWER2, etc.
            elif action.upper().startswith("POWER"):
                state_clean = raw_payload.strip().upper()
                device.power = state_clean
                device.powers[action.upper()] = state_clean

            parsed_payload: Any = raw_payload

            # Attempt JSON parsing
            try:
                payload_json = json.loads(raw_payload)
                if isinstance(payload_json, dict):
                    parsed_payload = payload_json
                    action_key = action.upper()
                    device.raw_details[action_key] = payload_json

                    # Check for direct POWER keys in JSON
                    self._extract_powers_from_dict(payload_json, device.powers)

                    # Extract Module info
                    if "Module" in payload_json:
                        device.module = payload_json["Module"]
                    elif "Status" in payload_json and isinstance(payload_json["Status"], dict):
                        st = payload_json["Status"]
                        device.module = {
                            "id": st.get("Module"),
                            "name": st.get("DeviceName", "Tasmota"),
                        }
                        self._extract_powers_from_dict(st, device.powers)

                    # Check nested StatusSTS
                    if "StatusSTS" in payload_json and isinstance(payload_json["StatusSTS"], dict):
                        device.state = payload_json["StatusSTS"]
                        self._extract_powers_from_dict(payload_json["StatusSTS"], device.powers)
                        self._record_telemetry_async(device_id, payload_json["StatusSTS"], device)
                        if device_id in self._state_waiters:
                            s_loop, s_event = self._state_waiters[device_id]
                            s_loop.call_soon_threadsafe(s_event.set)

                    # Extract Hardware / Firmware
                    if "StatusFWR" in payload_json:
                        device.hardware = payload_json["StatusFWR"]

                    # Extract Connected Sensors
                    if "StatusSNS" in payload_json:
                        device.sensors = payload_json["StatusSNS"]
                    elif action_key == "SENSOR":
                        device.sensors = payload_json

                    # Extract GPIO configuration
                    gpios = {k: v for k, v in payload_json.items() if k.upper().startswith("GPIO")}
                    if gpios:
                        if device.gpio is None:
                            device.gpio = {}
                        device.gpio.update(gpios)
                        if device_id in self._gpio_waiters:
                            g_loop, g_event = self._gpio_waiters[device_id]
                            g_loop.call_soon_threadsafe(g_event.set)

                    # Extract Telemetry State
                    if action_key == "STATE":
                        device.state = payload_json
                        if device.telemetry is None:
                            device.telemetry = {}
                        device.telemetry.update(payload_json)
                        self._extract_powers_from_dict(payload_json, device.powers)
                        self._record_telemetry_async(device_id, payload_json, device)

                        if device_id in self._state_waiters:
                            s_loop, s_event = self._state_waiters[device_id]
                            s_loop.call_soon_threadsafe(s_event.set)

                    # Notify status waiters
                    if action_key.startswith("STATUS") and device_id in self._status_waiters:
                        st_loop, st_event = self._status_waiters[device_id]
                        st_loop.call_soon_threadsafe(st_event.set)

            except json.JSONDecodeError:
                if device.telemetry is None:
                    device.telemetry = {}
                device.telemetry[action] = raw_payload

            # Build UI controls dynamically for any module
            self._build_device_controls(device)

            # Broadcast device update live via WebSocket
            event_bus.broadcast_threadsafe(
                "device_update",
                {
                    "device_id": device_id,
                    "online": device.online,
                    "powers": device.powers,
                    "controls": [c.model_dump() for c in device.controls],
                    "state": device.state,
                    "sensors": device.sensors,
                    "last_seen": device.last_seen,
                },
                device_id=device_id,
            )

            # Forward response to any pending command waiter
            if prefix.lower() == "stat" and device_id in self._cmd_waiters:
                waiters = self._cmd_waiters.pop(device_id, [])
                for c_loop, c_fut in waiters:
                    if not c_fut.done():
                        c_loop.call_soon_threadsafe(
                            c_fut.set_result,
                            {
                                "topic": topic,
                                "action": action,
                                "data": parsed_payload,
                            },
                        )

            # Notify any general query waiter
            if device_id in self._waiters:
                loop, event = self._waiters[device_id]
                loop.call_soon_threadsafe(event.set)

    def start(self):
        try:
            logger.info("Connecting to MQTT broker at %s:%s...", settings.MQTT_HOST, settings.MQTT_PORT)
            self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=settings.MQTT_KEEPALIVE)
            self.client.loop_start()
        except Exception as e:
            logger.error("Could not connect to MQTT broker on startup: %s", e)

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
        except Exception as e:
            logger.error("Error stopping MQTT client: %s", e)

    def is_connected(self) -> bool:
        return self.connected

    def get_all_devices(self) -> list[DeviceState]:
        all_devs: list[DeviceState] = []
        with self._lock:
            for dev in self.devices.values():
                self._build_device_controls(dev)
                all_devs.append(dev)
        return all_devs

    def get_device(self, device_id: str) -> DeviceState:
        with self._lock:
            if device_id in self.devices:
                dev = self.devices[device_id]
                self._build_device_controls(dev)
                return dev
            new_device = DeviceState(device_id=device_id)
            self._build_device_controls(new_device)
            self.devices[device_id] = new_device
            return new_device

    def send_command(self, device_id: str, command: str, payload: str = "") -> dict[str, Any]:
        cmd_clean = command.strip()
        topic = f"cmnd/{device_id}/{cmd_clean}"
        res = self.client.publish(topic, str(payload), qos=1)
        success = (res.rc == mqtt.MQTT_ERR_SUCCESS)
        return {
            "success": success,
            "device_id": device_id,
            "command": cmd_clean,
            "payload": str(payload),
            "topic": topic,
            "message": "Command dispatched successfully" if success else f"Failed with code {res.rc}",
        }

    async def execute_command(
        self, device_id: str, command: str, payload: str = "", timeout: float = 1.8
    ) -> dict[str, Any]:
        cmd_clean = command.strip()
        topic = f"cmnd/{device_id}/{cmd_clean}"

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        with self._lock:
            if device_id not in self._cmd_waiters:
                self._cmd_waiters[device_id] = []
            self._cmd_waiters[device_id].append((loop, fut))

        res = self.client.publish(topic, str(payload), qos=1)
        if res.rc != mqtt.MQTT_ERR_SUCCESS:
            with self._lock:
                if device_id in self._cmd_waiters and (loop, fut) in self._cmd_waiters[device_id]:
                    self._cmd_waiters[device_id].remove((loop, fut))
            return {
                "success": False,
                "device_id": device_id,
                "command": cmd_clean,
                "payload": str(payload),
                "topic": topic,
                "response": None,
                "response_topic": None,
                "message": f"Failed to publish MQTT message: code {res.rc}",
            }

        response_data = None
        try:
            response_data = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            logger.info("Device %s did not reply to command %s within %ss", device_id, cmd_clean, timeout)
        finally:
            with self._lock:
                if device_id in self._cmd_waiters and (loop, fut) in self._cmd_waiters[device_id]:
                    self._cmd_waiters[device_id].remove((loop, fut))

        return {
            "success": True if response_data is not None else False,
            "device_id": device_id,
            "command": cmd_clean,
            "payload": str(payload),
            "topic": topic,
            "response": response_data["data"] if response_data else None,
            "response_topic": response_data["topic"] if response_data else None,
            "message": "Response received from device" if response_data else "Command dispatched, but no reply within timeout",
        }

    async def apply_control(
        self, device_id: str, target: str, value: Any, timeout: float = 1.8
    ) -> dict[str, Any]:
        """
        General control endpoint logic. Resolves target (control ID or command name),
        executes command, captures live response, and returns new state.
        """
        device = self.get_device(device_id)
        target_clean = target.strip()
        command = target_clean

        # Check if target matches any registered control ID (e.g. relay_1, buzzer, etc.)
        for ctrl in device.controls:
            if ctrl.id.lower() == target_clean.lower() or ctrl.command.lower() == target_clean.lower():
                command = ctrl.command
                break

        # Handle buzzer action aliases
        payload_val = value
        if command.lower().startswith("buzzer"):
            val_str = str(value).strip().upper()
            if val_str in ("BEEP", "ON", "TOGGLE"):
                payload_val = "1"
            elif val_str == "OFF":
                payload_val = "0"

        exec_res = await self.execute_command(device_id, command, str(payload_val), timeout=timeout)

        # Extract new state from live response if present
        new_state = None
        resp = exec_res.get("response")
        if isinstance(resp, dict):
            if command in resp:
                new_state = resp[command]
            elif "POWER" in resp:
                new_state = resp["POWER"]
        elif isinstance(resp, str):
            new_state = resp

        if new_state is None and str(value).upper() in ("ON", "OFF"):
            new_state = str(value).upper()

        with self._lock:
            if new_state is not None and command.upper().startswith("POWER"):
                device.powers[command.upper()] = str(new_state)
            self._build_device_controls(device)

        # Broadcast update to WebSockets
        event_bus.broadcast_threadsafe(
            "control_applied",
            {
                "device_id": device_id,
                "target": target_clean,
                "command": command,
                "new_state": new_state,
            },
            device_id=device_id,
        )

        return {
            "success": exec_res["success"],
            "device_id": device_id,
            "target": target_clean,
            "command": command,
            "value": value,
            "new_state": new_state or (resp if isinstance(resp, (str, int)) else "DONE"),
            "response": exec_res.get("response"),
            "response_topic": exec_res.get("response_topic"),
            "message": "Control applied successfully" if exec_res["success"] else exec_res["message"],
        }

    async def query_device_status(self, device_id: str, index: int = 0, timeout: float = 1.8) -> dict[str, Any]:
        result = await self.execute_command(device_id, "STATUS", str(index), timeout=timeout)
        if result.get("response") is not None:
            resp_data = result["response"]
            if isinstance(resp_data, dict):
                target_key = f"STATUS{index}"
                if target_key in resp_data:
                    return resp_data[target_key]
                return resp_data

        device = self.get_device(device_id)
        raw = device.raw_details or {}
        if index != 0:
            target_key = f"STATUS{index}"
            if target_key in raw:
                return raw[target_key]

        statuses = {k: v for k, v in raw.items() if k.startswith("STATUS")}
        return statuses or raw

    async def query_device_state(self, device_id: str, timeout: float = 1.8) -> dict[str, Any]:
        result = await self.execute_command(device_id, "STATUS", "11", timeout=timeout)
        if result.get("response") is not None and isinstance(result["response"], dict):
            return result["response"].get("StatusSTS", result["response"])

        device = self.get_device(device_id)
        return device.state or {}

    async def query_device_gpio(self, device_id: str, timeout: float = 1.8) -> dict[str, Any]:
        result = await self.execute_command(device_id, "GPIO", "", timeout=timeout)
        if result.get("response") is not None and isinstance(result["response"], dict):
            gpios = {k: v for k, v in result["response"].items() if k.upper().startswith("GPIO")}
            if gpios:
                return gpios

        device = self.get_device(device_id)
        return device.gpio or {}

    async def query_device_modules(self, device_id: str, timeout: float = 1.8) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        event = asyncio.Event()

        with self._lock:
            self._waiters[device_id] = (loop, event)

        self.send_command(device_id, "GPIO", "")
        self.send_command(device_id, "MODULE", "")
        self.send_command(device_id, "STATUS", "0")

        refreshed = False
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            await asyncio.sleep(0.5)
            refreshed = True
        except asyncio.TimeoutError:
            logger.info("Device %s did not respond to module query within %ss", device_id, timeout)
        finally:
            with self._lock:
                self._waiters.pop(device_id, None)

        device = self.get_device(device_id)
        controls = self._build_device_controls(device)

        return {
            "device_id": device_id,
            "online": device.online,
            "custom_name": device.custom_name,
            "room": device.room,
            "module": device.module,
            "controls": controls,
            "gpio": device.gpio,
            "sensors": device.sensors,
            "hardware": device.hardware,
            "raw_details": device.raw_details,
            "refreshed": refreshed,
            "message": "Module details refreshed from device" if refreshed else "Returned cached module details",
        }


mqtt_service = MQTTService()
