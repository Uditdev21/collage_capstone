import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from app.database.repository import repo
from app.event_bus import event_bus

logger = logging.getLogger("rule_engine")


class RuleEngine:
    """Background engine evaluating automation rules (time schedules and telemetry thresholds)."""

    def __init__(self, mqtt_service=None):
        self.mqtt_service = mqtt_service
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_evaluated_minute: Optional[str] = None
        self._threshold_debounce: dict[str, datetime] = {}

    def set_mqtt_service(self, service):
        self.mqtt_service = service

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Automation Rule Engine started.")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Automation Rule Engine stopped.")

    async def _loop(self):
        while self._running:
            try:
                await self._evaluate_all_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in rule engine loop: %s", e)
            await asyncio.sleep(10)

    async def _evaluate_all_rules(self):
        rules = await repo.get_automations(only_enabled=True)
        if not rules or not self.mqtt_service:
            return

        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        for rule in rules:
            try:
                rule_id = rule["id"]
                trigger_type = rule.get("trigger_type")
                trigger_cfg = rule.get("trigger_config") or {}
                actions = rule.get("action_config") or []

                if not isinstance(actions, list):
                    continue

                should_trigger = False
                reason = ""

                # 1. Time-based trigger (HH:MM)
                if trigger_type == "time":
                    target_time = trigger_cfg.get("time")
                    if target_time == current_time_str:
                        # Ensure we don't trigger multiple times in the same minute
                        last_trig = rule.get("last_triggered")
                        if not last_trig or not str(last_trig).startswith(now.strftime("%Y-%m-%d %H:%M")):
                            should_trigger = True
                            reason = f"Time matched schedule: {target_time}"

                # 2. Telemetry threshold trigger
                elif trigger_type == "threshold":
                    metric = trigger_cfg.get("metric", "rssi").lower()
                    operator = trigger_cfg.get("operator", "<")
                    threshold_val = float(trigger_cfg.get("threshold", 0))

                    # Evaluate on active default device
                    dev_id = rule.get("device_id") or self.mqtt_service.get_default_device_id()
                    device = self.mqtt_service.get_device(dev_id)
                    curr_val = None

                    if metric == "rssi" and device.state and "Wifi" in device.state:
                        curr_val = device.state["Wifi"].get("RSSI")
                    elif metric == "heap" and device.state:
                        curr_val = device.state.get("Heap")
                    elif metric == "load_avg" and device.state:
                        curr_val = device.state.get("LoadAvg")

                    if curr_val is not None:
                        is_breached = False
                        if operator == "<" and curr_val < threshold_val:
                            is_breached = True
                        elif operator == ">" and curr_val > threshold_val:
                            is_breached = True
                        elif operator == "<=" and curr_val <= threshold_val:
                            is_breached = True
                        elif operator == ">=" and curr_val >= threshold_val:
                            is_breached = True

                        if is_breached:
                            # Debounce threshold to fire at most once every 5 minutes
                            last_fired = self._threshold_debounce.get(rule_id)
                            if not last_fired or (now - last_fired).total_seconds() > 300:
                                should_trigger = True
                                reason = f"Metric {metric} reached {curr_val} (condition: {operator} {threshold_val})"
                                self._threshold_debounce[rule_id] = now

                if should_trigger:
                    logger.info("Executing automation rule '%s': %s", rule["name"], reason)
                    await self._execute_actions(rule, actions, reason)
                    await repo.update_automation_last_triggered(rule_id)
                    event_bus.broadcast_threadsafe(
                        "automation_triggered",
                        {
                            "rule_id": rule_id,
                            "rule_name": rule["name"],
                            "reason": reason,
                            "actions": actions,
                        },
                    )
            except Exception as e:
                logger.error("Error evaluating rule %s: %s", rule.get("id"), e)

    async def _execute_actions(self, rule: dict[str, Any], actions: list[dict[str, Any]], reason: str):
        dev_id = rule.get("device_id") or self.mqtt_service.get_default_device_id()
        for act in actions:
            target = act.get("target")
            value = act.get("value", "TOGGLE")
            target_dev = act.get("device_id") or dev_id
            if target:
                res = await self.mqtt_service.apply_control(target_dev, target, value)
                await repo.log_audit(
                    device_id=target_dev,
                    action="AUTOMATION_EXECUTE",
                    target=target,
                    value=str(value),
                    source=f"rule:{rule['id']}",
                    status="SUCCESS" if res.get("success") else "FAILED",
                    details=reason,
                )


rule_engine = RuleEngine()
