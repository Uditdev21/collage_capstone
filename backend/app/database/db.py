import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger("database")

# Default database path in the smartdev_backend folder
DB_PATH = Path(__file__).resolve().parent.parent.parent / "smartdev.db"


def get_db_connection():
    """Returns an aiosqlite context manager for async with get_db_connection() as db:"""
    return aiosqlite.connect(str(DB_PATH))


async def init_db():
    """Initializes SQLite tables for devices, telemetry history, automations, audit logs, and AI chats."""
    logger.info("Initializing SQLite database at %s", DB_PATH)
    async with get_db_connection() as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        # 1. Device metadata table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                custom_name TEXT,
                room TEXT DEFAULT 'General',
                device_type TEXT DEFAULT 'tasmota_switch',
                icon TEXT DEFAULT 'hub',
                is_favorite INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 2. Telemetry History table (time-series for charts & predictive AI)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                rssi INTEGER,
                signal INTEGER,
                heap INTEGER,
                load_avg INTEGER,
                uptime_sec INTEGER,
                power_states TEXT,
                sensor_data TEXT,
                raw_state TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry_history (device_id, timestamp DESC)"
        )

        # 3. Audit Logs table (tracks every command, trigger, user action)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                action TEXT NOT NULL,
                target TEXT,
                value TEXT,
                source TEXT DEFAULT 'api',
                status TEXT DEFAULT 'SUCCESS',
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs (timestamp DESC)"
        )

        # 4. Automations & Rules table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                trigger_type TEXT NOT NULL,
                trigger_config TEXT NOT NULL,
                action_config TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_triggered TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 5. AI Conversation & Insights table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                model_used TEXT NOT NULL,
                actions_executed TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Seed sample automations if table is empty
        cursor = await db.execute("SELECT COUNT(*) FROM automations")
        count = (await cursor.fetchone())[0]
        if count == 0:
            sample_rules = [
                (
                    "rule_all_off_night",
                    "Eco Night Power-Down",
                    "Turns off all relays at 23:30 to conserve power",
                    "time",
                    '{"time": "23:30"}',
                    '[{"target": "POWER1", "value": "OFF"}, {"target": "POWER2", "value": "OFF"}, {"target": "POWER3", "value": "OFF"}]',
                    1,
                ),
                (
                    "rule_wifi_watchdog",
                    "WiFi Quality Sentinel",
                    "Logs warning if WiFi RSSI drops below 35%",
                    "threshold",
                    '{"metric": "rssi", "operator": "<", "threshold": 35}',
                    '[{"type": "alert", "message": "Low WiFi signal detected on IoT device"}]',
                    1,
                ),
            ]
            await db.executemany(
                """
                INSERT INTO automations (id, name, description, trigger_type, trigger_config, action_config, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                sample_rules,
            )

        await db.commit()
    logger.info("SQLite database tables verified and ready.")
