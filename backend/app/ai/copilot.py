import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from app.ai.client import ai_client
from app.database.repository import repo
from app.event_bus import event_bus

logger = logging.getLogger("ai_copilot")


class AICopilot:
    """
    Intelligent Natural Language Copilot for SmartDev IoT.
    Translates English/speech instructions into safe, executable Tasmota MQTT actions.
    """

    def __init__(self, mqtt_service=None):
        self.mqtt_service = mqtt_service

    def set_mqtt_service(self, service):
        self.mqtt_service = service

    def _parse_offline_intent(self, prompt: str, device: Any) -> tuple[str, list[dict[str, Any]], list[str]]:
        """
        Robust, zero-dependency offline semantic intent parser.
        Guarantees instant, accurate execution even without external LLMs.
        """
        p_lower = prompt.lower().strip()
        actions = []
        explanation = ""
        suggestions = ["Turn off all relays", "Check system health", "What is my WiFi signal?"]
        device_id = device.device_id

        # 1. Turn on / off all
        if any(w in p_lower for w in ["all on", "turn on everything", "turn everything on", "all relays on", "activate all"]):
            for ctrl in device.controls:
                if ctrl.type == "switch":
                    actions.append({"device_id": device_id, "target": ctrl.id, "value": "ON"})
            explanation = f"Turning ON all {len(actions)} available modules on {device_id}."
            return explanation, actions, ["Turn off all relays", "Run diagnostics"]

        if any(w in p_lower for w in ["all off", "turn off everything", "turn everything off", "all relays off", "deactivate all"]):
            for ctrl in device.controls:
                if ctrl.type == "switch":
                    actions.append({"device_id": device_id, "target": ctrl.id, "value": "OFF"})
            explanation = f"Turning OFF all {len(actions)} modules on {device_id} to save energy."
            return explanation, actions, ["Turn on Relay 1", "Check system health"]

        # 2. Specific relay controls (e.g. "turn on relay 1", "toggle switch 2", "relay 3 off")
        for num in range(1, 9):
            if f"relay {num}" in p_lower or f"relay{num}" in p_lower or f"switch {num}" in p_lower or f"light {num}" in p_lower or f"channel {num}" in p_lower:
                target_id = f"relay_{num}"
                val = "TOGGLE"
                if any(w in p_lower for w in ["on", "activate", "start", "enable"]):
                    val = "ON"
                elif any(w in p_lower for w in ["off", "deactivate", "stop", "kill"]):
                    val = "OFF"
                elif "toggle" in p_lower:
                    val = "TOGGLE"

                actions.append({"device_id": device_id, "target": target_id, "value": val})
                explanation = f"Applied **{val}** to {target_id.replace('_', ' ').title()} on {device_id}."
                return explanation, actions, [f"Turn off Relay {num}", "Check device telemetry"]

        # 3. Buzzer / Alarm
        if "buzzer" in p_lower or "beep" in p_lower or "alarm" in p_lower:
            actions.append({"device_id": device_id, "target": "buzzer", "value": "BEEP"})
            explanation = f"Triggered acoustic buzzer beacon on {device_id}."
            return explanation, actions, ["Check device status", "Turn off all relays"]

        # 4. Status / Health / Diagnostics query
        if any(w in p_lower for w in ["health", "diagnostic", "status", "wifi", "signal", "rssi", "heap", "uptime", "temp"]):
            rssi = device.state.get("Wifi", {}).get("RSSI", "N/A") if device.state else "N/A"
            heap = device.state.get("Heap", "N/A") if device.state else "N/A"
            uptime = device.state.get("Uptime", "N/A") if device.state else "N/A"
            ip = device.state.get("IPAddress", "N/A") if device.state else "N/A"
            active_powers = [k for k, v in device.powers.items() if v == "ON"]
            explanation = (
                f"**Device Overview ({device_id}):**\n"
                f"- **Online Status:** {'🟢 Online' if device.online else '🔴 Offline'}\n"
                f"- **IP Address:** `{ip}`\n"
                f"- **WiFi Quality:** `{rssi}%`\n"
                f"- **Heap Memory:** `{heap} KB`\n"
                f"- **System Uptime:** `{uptime}`\n"
                f"- **Active Relays:** `{', '.join(active_powers) if active_powers else 'None'}`"
            )
            return explanation, [], ["Run full AI diagnostics", "Turn on all relays", "Test buzzer"]

        # 5. Fallback help
        explanation = (
            f"Hello! I am your SmartDev IoT Assistant. I can control your relays, check telemetry, or run diagnostics. "
            f"Try asking:\n"
            f"• *'Turn on Relay 1'*\n"
            f"• *'Turn off all relays'*\n"
            f"• *'How is my WiFi and health?'*\n"
            f"• *'Beep buzzer'*"
        )
        return explanation, [], ["Turn on Relay 1", "Turn off all relays", "Check health"]

    async def execute_prompt(
        self,
        prompt: str,
        target_device_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Executes a natural language prompt:
        - Consults LLM (Ollama / Groq) or Built-in Semantic Parser
        - Executes physical MQTT commands safely
        - Logs audit trail and returns structured output
        """
        if not self.mqtt_service:
            from app.mqtt_client import mqtt_service
            self.mqtt_service = mqtt_service

        dev_id = target_device_id or self.mqtt_service.get_default_device_id()
        device = self.mqtt_service.get_device(dev_id)

        # Build context for LLM
        controls_summary = [
            {"id": c.id, "name": c.name, "type": c.type, "state": c.state, "command": c.command}
            for c in device.controls
        ]
        context_data = {
            "device_id": dev_id,
            "online": device.online,
            "controls": controls_summary,
            "powers": device.powers,
            "wifi_rssi": device.state.get("Wifi", {}).get("RSSI") if device.state else None,
            "heap_kb": device.state.get("Heap") if device.state else None,
        }

        system_prompt = (
            "You are SmartDev Llama Copilot, an intelligent IoT voice/chat controller. "
            "You control embedded hardware via MQTT. "
            "Given the user request and device context, reply with a JSON object ONLY with the following schema:\n"
            "{\n"
            '  "explanation": "Friendly natural language reply to user",\n'
            '  "actions": [{"device_id": "string", "target": "string", "value": "ON"|"OFF"|"TOGGLE"|"BEEP"}],\n'
            '  "suggested_prompts": ["string", "string"]\n'
            "}\n"
            "Rules:\n"
            "- Only generate actions for controls that exist in context.\n"
            "- If user asks a question, set actions to empty list [].\n"
            "- Output valid JSON only, without markdown fences or extraneous text."
        )

        user_content = f"Device Context: {json.dumps(context_data)}\nUser Request: {prompt}"
        messages = [{"role": "user", "content": user_content}]

        llm_raw, model_used = await ai_client.generate_response(
            messages,
            system_prompt=system_prompt,
            temperature=0.1,
            force_provider=provider,
        )

        explanation = ""
        actions: list[dict[str, Any]] = []
        suggested_prompts: list[str] = []

        # Attempt to parse LLM JSON
        if llm_raw:
            try:
                # Strip possible markdown code blocks
                clean_json = re.sub(r"^```(?:json)?\s*", "", llm_raw.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                explanation = parsed.get("explanation", "")
                actions = parsed.get("actions", [])
                suggested_prompts = parsed.get("suggested_prompts", [])
            except Exception as e:
                logger.warning("Could not parse LLM output as JSON: %s. Output was: %s", e, llm_raw)

        # Fallback to Built-in Semantic Engine if LLM did not provide structured explanation
        if not explanation:
            model_used = "SmartDev Cognitive AI"
            explanation, actions, suggested_prompts = self._parse_offline_intent(prompt, device)

        # Execute physical actions over MQTT
        executed_actions = []
        for act in actions:
            t_dev = act.get("device_id") or dev_id
            target = act.get("target")
            value = act.get("value", "TOGGLE")
            if target:
                res = await self.mqtt_service.apply_control(t_dev, target, value)
                executed_actions.append({
                    "device_id": t_dev,
                    "target": target,
                    "value": value,
                    "success": res.get("success", False),
                    "new_state": res.get("new_state"),
                })
                # Log audit
                await repo.log_audit(
                    device_id=t_dev,
                    action="AI_COPILOT_CONTROL",
                    target=target,
                    value=str(value),
                    source="ai_copilot",
                    status="SUCCESS" if res.get("success") else "FAILED",
                    details=f"Prompt: {prompt}",
                )

        now_str = datetime.now().isoformat()

        # Log conversation in database
        await repo.log_ai_conversation(
            device_id=dev_id,
            user_message=prompt,
            ai_response=explanation,
            model_used=model_used,
            actions_executed=executed_actions,
        )

        # Broadcast via WebSocket
        event_bus.broadcast_threadsafe(
            "ai_interaction",
            {
                "prompt": prompt,
                "response": explanation,
                "actions": executed_actions,
                "model": model_used,
            },
            device_id=dev_id,
        )

        return {
            "response": explanation,
            "model": model_used,
            "device_id": dev_id,
            "actions_executed": executed_actions,
            "suggested_prompts": suggested_prompts,
            "timestamp": now_str,
        }


ai_copilot = AICopilot()
