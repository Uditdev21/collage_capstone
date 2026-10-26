import json
import logging
import re
import uuid
from typing import Any
from app.ai.client import ai_client

logger = logging.getLogger("automation_ai")


class AutomationAIGenerator:
    """Translates user natural language instructions into structured automation rules."""

    @staticmethod
    async def generate_rule(prompt: str, default_device_id: str = "tasmota_0C3249") -> dict[str, Any]:
        system_prompt = (
            "You are an IoT Automation Architect. Convert the user's natural language request into a structured automation rule. "
            "Output JSON ONLY with this schema:\n"
            "{\n"
            '  "name": "Short descriptive rule title",\n'
            '  "description": "Clear explanation of rule action",\n'
            '  "trigger_type": "time" | "threshold" | "state",\n'
            '  "trigger_config": {"time": "HH:MM"} OR {"metric": "rssi"|"heap", "operator": "<"|">", "threshold": number},\n'
            '  "action_config": [{"target": "POWER1"|"POWER2"|"POWER3"|"relay_1"|"buzzer", "value": "ON"|"OFF"|"BEEP"}],\n'
            '  "explanation": "Brief reasoning for this rule"\n'
            "}\n"
            "Output valid JSON only."
        )

        user_content = f"IoT Device ID: {default_device_id}\nCreate automation for: {prompt}"
        messages = [{"role": "user", "content": user_content}]

        llm_raw, model_used = await ai_client.generate_response(messages, system_prompt=system_prompt, temperature=0.1)

        rule_data = None
        explanation = ""
        if llm_raw:
            try:
                clean_json = re.sub(r"^```(?:json)?\s*", "", llm_raw.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                explanation = parsed.pop("explanation", "AI-generated automation rule.")
                rule_data = parsed
            except Exception as e:
                logger.warning("Failed to parse AI rule JSON: %s", e)

        if not rule_data:
            model_used = "SmartDev Rules Heuristic"
            rule_id = f"rule_{uuid.uuid4().hex[:8]}"
            # Heuristic rule generator
            p_lower = prompt.lower()
            if "night" in p_lower or "pm" in p_lower or "am" in p_lower or "time" in p_lower:
                time_match = re.search(r"(\d{1,2}):(\d{2})", prompt)
                target_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "23:00"
                rule_data = {
                    "id": rule_id,
                    "name": "Scheduled Power Down",
                    "description": f"Automatically turns off relays at {target_time}",
                    "trigger_type": "time",
                    "trigger_config": {"time": target_time},
                    "action_config": [{"target": "POWER1", "value": "OFF"}, {"target": "POWER2", "value": "OFF"}],
                    "enabled": True,
                }
                explanation = f"Created time-based rule triggering daily at {target_time}."
            else:
                rule_data = {
                    "id": rule_id,
                    "name": "Telemetry Sentinel Guard",
                    "description": "Monitors device signal and notifies on low link margin",
                    "trigger_type": "threshold",
                    "trigger_config": {"metric": "rssi", "operator": "<", "threshold": 40},
                    "action_config": [{"target": "buzzer", "value": "BEEP"}],
                    "enabled": True,
                }
                explanation = "Created threshold guard rule triggering acoustic buzzer when RSSI drops below 40%."

        if "id" not in rule_data:
            rule_data["id"] = f"rule_{uuid.uuid4().hex[:8]}"
        if "enabled" not in rule_data:
            rule_data["enabled"] = True

        return {
            "rule": rule_data,
            "explanation": explanation,
            "model_used": model_used,
        }


automation_ai = AutomationAIGenerator()
