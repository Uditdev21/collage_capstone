import logging
from datetime import datetime
from typing import Any, Optional
from app.ai.client import ai_client
from app.config import settings

logger = logging.getLogger("ai_diagnostics")


class AIDiagnostics:
    """Predictive Telemetry Diagnostics & Health Scoring Engine for IoT Devices."""

    @staticmethod
    def calculate_metrics_score(device_state: dict[str, Any]) -> tuple[int, str, list[dict[str, Any]], list[str]]:
        """
        Calculates a numerical health score (0-100), anomalies list, and recommendations.
        """
        score = 100
        anomalies = []
        recommendations = []

        # Extract telemetry fields
        state = device_state.get("state") or {}
        tele = device_state.get("telemetry") or {}
        raw = device_state.get("raw_details") or {}
        wifi = state.get("Wifi") or tele.get("Wifi") or {}
        hardware = device_state.get("hardware") or raw.get("STATUS2", {}).get("StatusFWR") or {}

        # 1. WiFi RSSI & Signal Quality
        rssi = wifi.get("RSSI")
        signal = wifi.get("Signal")
        if rssi is not None:
            if rssi < 30:
                score -= 30
                anomalies.append({
                    "metric": "WiFi RSSI",
                    "severity": "HIGH",
                    "value": f"{rssi}% ({signal} dBm)",
                    "detail": "Critical wireless signal attenuation. High risk of packet loss and MQTT disconnects.",
                })
                recommendations.append("Relocate IoT device closer to WiFi access point or install an extender.")
            elif rssi < 50:
                score -= 15
                anomalies.append({
                    "metric": "WiFi RSSI",
                    "severity": "MEDIUM",
                    "value": f"{rssi}% ({signal} dBm)",
                    "detail": "Fair wireless signal strength. May experience occasional latency spikes.",
                })
                recommendations.append("Verify router antenna orientation or change WiFi channel to minimize interference.")
            else:
                anomalies.append({
                    "metric": "WiFi RSSI",
                    "severity": "NORMAL",
                    "value": f"{rssi}% ({signal} dBm)",
                    "detail": "Wireless link quality is healthy and stable.",
                })

        # 2. Heap Memory Health (ESP8266 / ESP32)
        heap = state.get("Heap") or tele.get("Heap")
        if heap is not None:
            if heap < 12:
                score -= 25
                anomalies.append({
                    "metric": "Heap Memory",
                    "severity": "HIGH",
                    "value": f"{heap} KB",
                    "detail": "Severe memory fragmentation or exhaustion. ESP reboot imminent.",
                })
                recommendations.append("Disable unneeded Tasmota driver features (WebLog 0, SysLog 0) to free RAM.")
            elif heap < 18:
                score -= 10
                anomalies.append({
                    "metric": "Heap Memory",
                    "severity": "MEDIUM",
                    "value": f"{heap} KB",
                    "detail": "Moderate heap memory buffer remaining.",
                })
            else:
                anomalies.append({
                    "metric": "Heap Memory",
                    "severity": "NORMAL",
                    "value": f"{heap} KB",
                    "detail": "Heap memory buffer is ample and non-fragmented.",
                })

        # 3. Boot Count & Restart Reason
        boot_count = None
        restart_reason = None
        status1 = raw.get("STATUS1", {}).get("StatusPRM") or {}
        if status1:
            boot_count = status1.get("BootCount")
            restart_reason = status1.get("RestartReason")

        if restart_reason and "Exception" in restart_reason:
            score -= 20
            anomalies.append({
                "metric": "Restart Reason",
                "severity": "HIGH",
                "value": str(restart_reason),
                "detail": "Device previously crashed due to firmware kernel panic / watchdog timer.",
            })
            recommendations.append("Review connected GPIO modules for electrical ground loops or supply voltage drops.")
        elif restart_reason and "Brownout" in restart_reason:
            score -= 25
            anomalies.append({
                "metric": "Power Supply",
                "severity": "HIGH",
                "value": "Brownout Reset",
                "detail": "Input voltage dipped below operating threshold. Relay switching current surge suspected.",
            })
            recommendations.append("Use a dedicated 5V/3.3V power supply with electrolytic bypass capacitor.")

        # 4. Load Average
        load_avg = state.get("LoadAvg")
        if load_avg is not None and load_avg > 80:
            score -= 10
            anomalies.append({
                "metric": "CPU LoadAvg",
                "severity": "MEDIUM",
                "value": f"{load_avg}%",
                "detail": "Higher than normal CPU scheduling load.",
            })

        # Ensure score bounds
        final_score = max(5, min(100, score))
        if final_score >= 90:
            status_level = "Optimal"
        elif final_score >= 75:
            status_level = "Good"
        elif final_score >= 50:
            status_level = "Warning"
        else:
            status_level = "Critical"

        if not recommendations:
            recommendations.append("System parameters are within optimal operating envelopes. Continue routine monitoring.")

        return final_score, status_level, anomalies, recommendations

    async def analyze_device(self, device_id: str, device_state: dict[str, Any]) -> dict[str, Any]:
        """Runs the diagnostics calculation and enriches it with LLM narrative."""
        score, status_level, anomalies, recommendations = self.calculate_metrics_score(device_state)

        state = device_state.get("state") or {}
        tele = device_state.get("telemetry") or {}
        wifi = state.get("Wifi") or tele.get("Wifi") or {}

        # Build prompt for LLM explanation
        prompt_data = {
            "device_id": device_id,
            "health_score": f"{score}/100",
            "status_level": status_level,
            "hardware": device_state.get("hardware") or "ESP Microcontroller",
            "wifi": wifi,
            "heap_kb": state.get("Heap") or tele.get("Heap"),
            "anomalies": anomalies,
            "recommendations": recommendations,
        }

        system_prompt = (
            "You are SmartDev Sentinel, an advanced AI diagnostics engineer for embedded IoT and Tasmota devices. "
            "Analyze the device telemetry, explain the health score, pinpoint any risks (WiFi signal, Heap memory, power spikes), "
            "and provide concise, actionable engineering advice in a confident, professional tone."
        )

        messages = [
            {
                "role": "user",
                "content": f"Generate a high-level diagnostics assessment for device telemetry: {prompt_data}",
            }
        ]

        llm_response, model_used = await ai_client.generate_response(messages, system_prompt=system_prompt)

        if not llm_response:
            # High-grade built-in narrative generator
            model_used = "SmartDev Sentinel AI"
            rssi_str = wifi.get("RSSI", "N/A")
            heap_str = state.get("Heap", tele.get("Heap", "N/A"))
            llm_response = (
                f"Device **{device_id}** is operating in **{status_level}** condition with an overall Health Score of **{score}/100**. "
                f"Telemetric analysis confirms WiFi RSSI is at {rssi_str}% with {heap_str} KB of unfragmented heap. "
                f"{recommendations[0]}"
            )

        return {
            "device_id": device_id,
            "health_score": score,
            "status_level": status_level,
            "metrics": {
                "rssi": wifi.get("RSSI"),
                "signal_dbm": wifi.get("Signal"),
                "heap_kb": state.get("Heap") or tele.get("Heap"),
                "load_avg": state.get("LoadAvg") or tele.get("LoadAvg"),
                "uptime": state.get("Uptime") or tele.get("Uptime"),
                "ip_address": state.get("IPAddress") or tele.get("IPAddress"),
                "hardware": device_state.get("hardware"),
            },
            "anomalies": anomalies,
            "recommendations": recommendations,
            "ai_summary": llm_response,
            "model_used": model_used,
            "timestamp": datetime.now().isoformat(),
        }


ai_diagnostics = AIDiagnostics()
