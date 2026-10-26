import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Ensure parent directory (backend/) is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ai.copilot import ai_copilot
from app.auth import verify_api_key
from app.config import settings
from app.database.db import init_db
from app.engine.rule_engine import rule_engine
from app.event_bus import event_bus
from app.mqtt_client import mqtt_service
from app.routers import ai, automations, devices, system, telemetry, ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    loop = asyncio.get_running_loop()
    event_bus.set_loop(loop)
    mqtt_service.set_loop(loop)
    rule_engine.set_mqtt_service(mqtt_service)
    ai_copilot.set_mqtt_service(mqtt_service)

    # 1. Initialize SQLite persistence
    logger.info("Initializing SQLite persistence layer...")
    await init_db()

    # 2. Connect to MQTT broker
    logger.info("Connecting to MQTT broker (%s:%s)...", settings.MQTT_HOST, settings.MQTT_PORT)
    mqtt_service.start()

    # 3. Start background Automation Rule Engine
    logger.info("Starting Automation Rule Engine...")
    rule_engine.start()

    yield

    # Shutdown:
    logger.info("Shutting down SmartDev IoT backend...")
    rule_engine.stop()
    mqtt_service.stop()


app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for mobile and web frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under /api
app.include_router(
    devices.router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    ai.router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    automations.router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    telemetry.router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    system.router,
    prefix="/api",
)
app.include_router(
    ws.router,
    prefix="/api",
)


# Embedded Web Dashboard
@app.api_route("/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Dashboard"])
def get_dashboard():
    dashboard_file = Path(__file__).resolve().parent / "web" / "dashboard.html"
    if dashboard_file.exists():
        return HTMLResponse(content=dashboard_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard loading...</h1>")


@app.api_route("/", methods=["GET", "HEAD"], tags=["Root"])
def root():
    return {
        "name": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "dashboard_url": "/dashboard",
        "docs_url": "/docs",
        "auth_header": settings.API_KEY_HEADER,
        "endpoints": {
            "web_dashboard": "/dashboard",
            "websocket_live": "/api/ws/live",
            "list_devices": "/api/devices",
            "device_status": f"/api/devices/{settings.DEFAULT_DEVICE_ID}",
            "device_modules_and_controls": f"/api/devices/{settings.DEFAULT_DEVICE_ID}/modules",
            "control_device": f"/api/devices/{settings.DEFAULT_DEVICE_ID}/control",
            "ai_copilot": "/api/ai/copilot",
            "ai_diagnostics": f"/api/ai/diagnostics/{settings.DEFAULT_DEVICE_ID}",
            "ai_generate_rule": "/api/ai/generate-rule",
            "automations": "/api/automations",
            "scenes": "/api/automations/scenes",
            "telemetry_history": f"/api/telemetry/{settings.DEFAULT_DEVICE_ID}/history",
            "health": "/api/system/health",
            "broker": "/api/system/broker",
            "audit_logs": "/api/system/audit-logs",
        },
    }
