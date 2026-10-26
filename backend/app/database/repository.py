import json
import logging
from datetime import datetime
from typing import Any, Optional
import aiosqlite
from app.database.db import get_db_connection

logger = logging.getLogger("repository")


class Repository:
    # ------------------ Device Metadata ------------------
    @staticmethod
    async def get_device_meta(device_id: str) -> Optional[dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def upsert_device_meta(
        device_id: str,
        custom_name: Optional[str] = None,
        room: Optional[str] = None,
        device_type: Optional[str] = None,
        icon: Optional[str] = None,
        is_favorite: Optional[bool] = None,
    ):
        async with get_db_connection() as db:
            cursor = await db.execute("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
            exists = await cursor.fetchone()
            if exists:
                fields = []
                vals = []
                if custom_name is not None:
                    fields.append("custom_name = ?")
                    vals.append(custom_name)
                if room is not None:
                    fields.append("room = ?")
                    vals.append(room)
                if device_type is not None:
                    fields.append("device_type = ?")
                    vals.append(device_type)
                if icon is not None:
                    fields.append("icon = ?")
                    vals.append(icon)
                if is_favorite is not None:
                    fields.append("is_favorite = ?")
                    vals.append(1 if is_favorite else 0)
                if fields:
                    fields.append("updated_at = CURRENT_TIMESTAMP")
                    vals.append(device_id)
                    await db.execute(f"UPDATE devices SET {', '.join(fields)} WHERE device_id = ?", vals)
            else:
                await db.execute(
                    """
                    INSERT INTO devices (device_id, custom_name, room, device_type, icon, is_favorite)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        custom_name or device_id,
                        room or "General",
                        device_type or "tasmota_switch",
                        icon or "hub",
                        1 if is_favorite else 0,
                    ),
                )
            await db.commit()

    @staticmethod
    async def get_all_device_meta() -> dict[str, dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM devices")
            rows = await cursor.fetchall()
            return {r["device_id"]: dict(r) for r in rows}

    # ------------------ Telemetry Time-Series ------------------
    @staticmethod
    async def record_telemetry(
        device_id: str,
        rssi: Optional[int] = None,
        signal: Optional[int] = None,
        heap: Optional[int] = None,
        load_avg: Optional[int] = None,
        uptime_sec: Optional[int] = None,
        power_states: Optional[dict[str, Any]] = None,
        sensor_data: Optional[dict[str, Any]] = None,
        raw_state: Optional[dict[str, Any]] = None,
    ):
        try:
            async with get_db_connection() as db:
                await db.execute(
                    """
                    INSERT INTO telemetry_history (
                        device_id, rssi, signal, heap, load_avg, uptime_sec,
                        power_states, sensor_data, raw_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        rssi,
                        signal,
                        heap,
                        load_avg,
                        uptime_sec,
                        json.dumps(power_states) if power_states else None,
                        json.dumps(sensor_data) if sensor_data else None,
                        json.dumps(raw_state) if raw_state else None,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.error("Failed to record telemetry for %s: %s", device_id, e)

    @staticmethod
    async def get_recent_telemetry(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, device_id, rssi, signal, heap, load_avg, uptime_sec,
                       power_states, sensor_data, timestamp
                FROM telemetry_history
                WHERE device_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (device_id, limit),
            )
            rows = await cursor.fetchall()
            res = []
            for r in reversed(rows):
                item = dict(r)
                if item.get("power_states"):
                    try:
                        item["power_states"] = json.loads(item["power_states"])
                    except Exception:
                        pass
                if item.get("sensor_data"):
                    try:
                        item["sensor_data"] = json.loads(item["sensor_data"])
                    except Exception:
                        pass
                res.append(item)
            return res

    # ------------------ Audit Logs ------------------
    @staticmethod
    async def log_audit(
        device_id: Optional[str],
        action: str,
        target: Optional[str] = None,
        value: Optional[str] = None,
        source: str = "api",
        status: str = "SUCCESS",
        details: Optional[str] = None,
    ):
        try:
            async with get_db_connection() as db:
                await db.execute(
                    """
                    INSERT INTO audit_logs (device_id, action, target, value, source, status, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, action, target, str(value) if value is not None else None, source, status, details),
                )
                await db.commit()
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    @staticmethod
    async def get_audit_logs(limit: int = 50, device_id: Optional[str] = None) -> list[dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            if device_id:
                cursor = await db.execute(
                    "SELECT * FROM audit_logs WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (device_id, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ------------------ Automations ------------------
    @staticmethod
    async def get_automations(only_enabled: bool = False) -> list[dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM automations" + (" WHERE enabled = 1" if only_enabled else "") + " ORDER BY created_at DESC"
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["trigger_config"] = json.loads(item["trigger_config"])
                except Exception:
                    pass
                try:
                    item["action_config"] = json.loads(item["action_config"])
                except Exception:
                    pass
                results.append(item)
            return results

    @staticmethod
    async def upsert_automation(
        rule_id: str,
        name: str,
        description: str,
        trigger_type: str,
        trigger_config: dict[str, Any] | str,
        action_config: list[dict[str, Any]] | str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        trig_str = json.dumps(trigger_config) if isinstance(trigger_config, (dict, list)) else trigger_config
        act_str = json.dumps(action_config) if isinstance(action_config, (dict, list)) else action_config

        async with get_db_connection() as db:
            await db.execute(
                """
                INSERT INTO automations (id, name, description, trigger_type, trigger_config, action_config, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    trigger_type = excluded.trigger_type,
                    trigger_config = excluded.trigger_config,
                    action_config = excluded.action_config,
                    enabled = excluded.enabled
                """,
                (rule_id, name, description, trigger_type, trig_str, act_str, 1 if enabled else 0),
            )
            await db.commit()
            return {
                "id": rule_id,
                "name": name,
                "description": description,
                "trigger_type": trigger_type,
                "trigger_config": trigger_config,
                "action_config": action_config,
                "enabled": enabled,
            }

    @staticmethod
    async def toggle_automation(rule_id: str, enabled: bool):
        async with get_db_connection() as db:
            await db.execute(
                "UPDATE automations SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, rule_id),
            )
            await db.commit()

    @staticmethod
    async def delete_automation(rule_id: str):
        async with get_db_connection() as db:
            await db.execute("DELETE FROM automations WHERE id = ?", (rule_id,))
            await db.commit()

    @staticmethod
    async def update_automation_last_triggered(rule_id: str):
        async with get_db_connection() as db:
            await db.execute(
                "UPDATE automations SET last_triggered = CURRENT_TIMESTAMP WHERE id = ?",
                (rule_id,),
            )
            await db.commit()

    # ------------------ AI Conversations ------------------
    @staticmethod
    async def log_ai_conversation(
        device_id: Optional[str],
        user_message: str,
        ai_response: str,
        model_used: str,
        actions_executed: Optional[list[dict[str, Any]]] = None,
    ):
        try:
            async with get_db_connection() as db:
                await db.execute(
                    """
                    INSERT INTO ai_conversations (device_id, user_message, ai_response, model_used, actions_executed)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        user_message,
                        ai_response,
                        model_used,
                        json.dumps(actions_executed) if actions_executed else None,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.error("Failed to log AI conversation: %s", e)

    @staticmethod
    async def get_recent_ai_conversations(limit: int = 20, device_id: Optional[str] = None) -> list[dict[str, Any]]:
        async with get_db_connection() as db:
            db.row_factory = aiosqlite.Row
            if device_id:
                cursor = await db.execute(
                    "SELECT * FROM ai_conversations WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (device_id, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM ai_conversations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            items = []
            for r in reversed(rows):
                entry = dict(r)
                if entry.get("actions_executed"):
                    try:
                        entry["actions_executed"] = json.loads(entry["actions_executed"])
                    except Exception:
                        pass
                items.append(entry)
            return items


repo = Repository()
