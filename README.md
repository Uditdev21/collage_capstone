# SmartDev 2.0 • Intelligent AI IoT Hub & Tasmota Adapter

A state-of-the-art, feature-packed IoT platform that bridges physical **Tasmota (ESP8266 / ESP32)** hardware with modern Mobile (Flutter) and Web clients. Features a **Multi-Provider AI Copilot (Llama 3.2 / Groq / SmartDev Cortex)**, **Real-Time WebSocket Streaming**, **Predictive Telemetry Diagnostics & Health Scoring**, **Automation Rule Engine**, and an embedded **Dark Glassmorphic Web Dashboard**.

---

## 1. Upgraded System Architecture

```
smartdev_backend/
├── backend/
│   └── app/
│       ├── config.py              # Extended App & AI settings (Llama, Groq, DB)
│       ├── models.py              # Pydantic schemas (Devices, Telemetry, AI, Automations)
│       ├── auth.py                # Constant-time API Key authentication (X-API-Key)
│       ├── event_bus.py           # Real-time WebSocket connection manager & broadcast hub
│       ├── database/              # Async SQLite persistence layer (aiosqlite)
│       │   ├── db.py              # WAL-mode database initialization & schema
│       │   └── repository.py      # Repositories for telemetry, devices, rules, audit logs
│       ├── ai/                    # Multi-Model AI Engine ("SmartDev Sentinel & Copilot")
│       │   ├── client.py          # Unified AI Client (Ollama / Llama, Groq, Built-in Fallback)
│       │   ├── copilot.py         # Natural Language IoT Commander (converts text/speech to MQTT)
│       │   ├── diagnostics.py     # Predictive Telemetry Diagnostics (0-100 Health Score)
│       │   └── automation_ai.py   # AI Natural Language to Automation Rule generator
│       ├── engine/                # Automation & Rule Execution Engine
│       │   └── rule_engine.py     # Background worker evaluating schedules & metric thresholds
│       ├── web/                   # Embedded Next-Gen Web Dashboard
│       │   └── dashboard.html     # Dark Glassmorphism Web App with live WebSockets
│       ├── routers/
│       │   ├── devices.py         # /api/devices (CRUD, controls, modules, metadata)
│       │   ├── ai.py              # /api/ai (Copilot chat, diagnostics, rule generation)
│       │   ├── automations.py     # /api/automations (Scenes, trigger rules, enable/disable)
│       │   ├── telemetry.py       # /api/telemetry (Time-series history, statistics)
│       │   ├── ws.py              # /api/ws/live (Bidirectional WebSockets)
│       │   └── system.py          # /api/system (Health, broker status, audit logs)
│       └── main.py                # FastAPI app with CORS, Lifespan, and Dashboard route
├── mosquitto/                     # Mosquitto Docker configuration & storage
├── docker-compose.yml             # Mosquitto MQTT broker container
├── publisher.py                   # Standalone CLI/Interactive MQTT publisher
├── subscriber.py                  # Standalone CLI MQTT subscriber/logger
├── run_api.py                     # REST API server launcher
└── requirements.txt               # Python dependencies
```

---

## 2. Key Features

### 🧠 Multi-Provider AI Copilot & Sentinel (Llama / Groq / Offline)
- **Natural Language Hardware Control**: Say *"Turn on Relay 1"*, *"Turn off all relays"*, or *"How is my WiFi and health?"*. The AI translates intent into concrete Tasmota MQTT commands, executes them safely, and responds naturally.
- **Supported AI Models**:
  - **Local Ollama (Llama 3.2, Mistral)**: 100% free, private, local, zero-cloud dependency.
  - **Groq Free Cloud Tier**: Ultra-fast inference with `llama-3.3-70b-versatile`.
  - **SmartDev Built-in Cognitive Engine**: High-speed, zero-dependency offline semantic parser and heuristics engine that functions even with zero internet or external keys.
- **Predictive Health Scoring (0–100)**: Evaluates WiFi RSSI, signal attenuation, heap memory degradation, boot restart causes, and load average to assign health scores and actionable maintenance tips.

### ⚡ Real-Time Streaming Event Bus (WebSockets)
- `/api/ws/live`: Bidirectional WebSockets broadcast state updates, switch toggles, telemetry points, and AI interactions in real-time with **0ms latency** without polling.

### 💾 Persistent Async SQLite Database
- Time-series telemetry tracking (`rssi`, `heap`, `load_avg`, `power_states`).
- Complete system audit logs tracking every user toggle, AI command, and rule trigger.
- Custom device metadata (rooms, custom labels, icons, favorites).

### ⚙️ Automation & Scene Engine
- Pre-configured instant scenes: **All Relays ON**, **Full Power Down**, **Eco Mode**, and **Audio Beacon**.
- Background Rule Engine evaluating cron time schedules and telemetry threshold alarms (e.g. WiFi RSSI watchdog).

---

## 3. Quick Start

### Step 1: Start the MQTT Broker
```bash
docker compose up -d
```

### Step 2: Start the REST API & Dashboard
```bash
source venv/bin/activate
fastapi dev backend/app/main.py
```

- **Interactive Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Embedded Web Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

---

## 4. API Endpoints Reference

### AI Endpoints (`/api/ai`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ai/copilot` | Natural language voice/text command execution & conversational response |
| `GET` | `/api/ai/diagnostics/{device_id}` | Predictive telemetry diagnostics, 0-100 health score & anomaly alerts |
| `POST` | `/api/ai/generate-rule` | Converts natural language requests into structured automation rules |
| `GET` | `/api/ai/providers` | Status of Ollama (Llama), Groq, and offline cognitive engine |
| `GET` | `/api/ai/history` | Historical AI conversations and executed hardware commands |

### Automations & Scenes (`/api/automations`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/automations` | List all automation rules |
| `POST` | `/api/automations` | Create or update an automation rule |
| `POST` | `/api/automations/{rule_id}/toggle` | Enable or disable a rule |
| `GET` | `/api/automations/scenes` | List available smart hardware scenes |
| `POST` | `/api/automations/scenes/{scene_id}/trigger` | Trigger a smart scene (e.g. `all_on`, `all_off`, `eco_mode`) |

### Devices (`/api/devices`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/devices` | List discovered and simulated devices |
| `GET` | `/api/devices/{device_id}` | Full device status, online state & telemetry |
| `GET` | `/api/devices/{device_id}/modules` | Connected modules, GPIO pin assignments & dynamic UI controls |
| `POST` | `/api/devices/{device_id}/control` | Universal controller for any module/switch/buzzer/slider |
| `PATCH` | `/api/devices/{device_id}/metadata` | Update custom device name, room, icon, and favorite status |

### Real-time WebSockets & Telemetry
| Protocol | Endpoint | Description |
|---|---|---|
| `WS` | `/api/ws/live` | Real-time WebSocket streaming feed for UI synchronization |
| `GET` | `/api/telemetry/{device_id}/history` | Historical time-series telemetry points for chart rendering |
| `GET` | `/api/system/audit-logs` | Comprehensive system action audit logs |
