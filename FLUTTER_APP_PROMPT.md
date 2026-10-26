# Flutter SmartDev IoT Client - Master Generation Prompt

Use the following detailed prompt with an AI assistant or development team to generate the complete Flutter mobile application for this IoT backend.

---

```markdown
# Goal: Build a Production-Ready Flutter IoT App for Tasmota SmartDev Backend

You are an expert Flutter & Dart mobile developer. Build a clean, modern, and cross-platform Flutter application (iOS & Android) that connects to the SmartDev Tasmota MQTT REST API.

---

## 1. Core UX Flow & Requirements

### Flow 1: First Launch & Configuration Screen (Server Setup)
- When the app launches for the first time, it checks if `apiUrl` and `apiKey` are saved in local storage (`shared_preferences`).
- If **not configured**, open the **Connection Settings Screen**:
  - **Input 1:** API Server Host/IP & Port (e.g. `http://192.168.1.146:8000` or `http://localhost:8000`). Automatically normalize leading `http://` or trailing slashes.
    - *Tip/Presets buttons:* Provide quick chips:
      - `10.0.2.2:8000` (Android Emulator default)
      - `localhost:8000` (iOS Simulator default)
      - `192.168.1.146:8000` (Physical Device on Local WiFi)
  - **Input 2:** API Key (e.g. `udit`). Supports obscure/reveal toggle.
  - **Action:** "Test & Save Connection" button.
    1. Sends a ping to `GET {baseUrl}/api/system/health`.
    2. Sends an authenticated request to `GET {baseUrl}/api/devices` with header `X-API-Key: {apiKey}`.
    3. If valid, saves to `shared_preferences` and navigates to the **Devices Screen**.
    4. If invalid, displays a clear snackbar/dialog explaining the failure (e.g., "Network Unreachable" or "Invalid API Key").
- Users can revisit this screen anytime via a Settings icon (⚙️) on the Home AppBar.

---

### Flow 2: Screen 1 - Discovered Devices List (Home)
- **AppBar:** App title ("SmartDev IoT"), Online status indicator, and Settings icon.
- **Data Source:** Calls `GET {baseUrl}/api/devices` with `X-API-Key: {apiKey}`.
- **UI Design:**
  - Pull-to-refresh (`RefreshIndicator`).
  - Search/filter bar by device name or ID.
  - Cards for each discovered device:
    - Status badge: 🟢 `Online` / 🔴 `Offline`.
    - Device ID (e.g. `tasmota_0C3249`).
    - Hardware tag (e.g. `ESP8266EX`) or IP address if present.
    - Last Seen timestamp.
    - Tap on device card &rarr; Navigates to **Device Details Screen**.
  - Empty state with "No devices discovered yet" and a refresh button.

---

### Flow 3: Screen 2 - Device Details & Dynamic Controls
- **AppBar:** Device ID + Live Refresh button (calls live sync).
- **Data Source:** Calls `GET {baseUrl}/api/devices/{device_id}/modules` with `X-API-Key: {apiKey}`.
- **Header Info Card:**
  - Device IP, Firmware version, Uptime, and WiFi RSSI signal strength (with signal bar icon).
- **Dynamic Controls Section:**
  The backend dynamically returns a list of controls in `data['controls']`. Render UI elements dynamically based on each control's `type`:
  
  1. **`type: "switch"` (Relays, Power, LEDs):**
     - Title: `control.name` (e.g. "Relay 1", "Relay 2", "Relay 3").
     - Subtitle: `control.command` (e.g. "POWER1") and GPIO pin (`control.gpio`).
     - Widget: Modern Cupertino/Material Switch + "TOGGLE" quick-tap card.
     - Action: When toggled, immediately updates UI optimistically and calls:
       `POST {baseUrl}/api/devices/{device_id}/control`
       Payload: `{"target": control.id, "value": "TOGGLE"}` (or "ON"/"OFF").
  
  2. **`type: "button"` (Buzzer, Triggers, Alarms):**
     - Title: `control.name` (e.g. "Buzzer").
     - Subtitle: `control.command` ("Buzzer") & GPIO pin.
     - Widget: Action Button with haptic feedback (e.g. "Beep", "Activate").
     - Action: When pressed, calls:
       `POST {baseUrl}/api/devices/{device_id}/control`
       Payload: `{"target": control.id, "value": "BEEP"}` (or "1").
  
  3. **`type: "slider"` (Dimmers, PWM, Brightness):**
     - Title: `control.name` (e.g. "Brightness" or "Channel 1").
     - Widget: Slider with min/max (0 to 100) and numeric badge.
     - Action: On slider release (`onChangeEnd`), calls:
       `POST {baseUrl}/api/devices/{device_id}/control`
       Payload: `{"target": control.id, "value": sliderValue}`.

---

## 2. API Contract & Schemas

### Headers Required
Every authenticated request MUST include:
```http
X-API-Key: <your_api_key>
Content-Type: application/json
```

### Endpoints
1. **Health Check (Public):**
   - `GET /api/system/health`
   - Response: `{"status": "ok", "mqtt_connected": true}`

2. **List Devices (Protected):**
   - `GET /api/devices`
   - Response: Array of Device objects:
     ```json
     [
       {
         "device_id": "tasmota_0C3249",
         "online": true,
         "power": "ON",
         "controls": [...],
         "last_seen": "2026-09-14T00:29:19.050426"
       }
     ]
     ```

3. **Get Modules & UI Controls (Protected):**
   - `GET /api/devices/{device_id}/modules?refresh=true`
   - Response:
     ```json
     {
       "device_id": "tasmota_0C3249",
       "online": true,
       "module": { "id": 18, "name": "Tasmota" },
       "controls": [
         {
           "id": "relay_1",
           "name": "Relay 1",
           "type": "switch",
           "command": "POWER1",
           "state": "ON",
           "gpio": "GPIO0",
           "actions": ["ON", "OFF", "TOGGLE"]
         },
         {
           "id": "buzzer",
           "name": "Buzzer",
           "type": "button",
           "command": "Buzzer",
           "state": "READY",
           "gpio": "GPIO3",
           "actions": ["BEEP", "1", "2", "0"]
         }
       ],
       "gpio": { "GPIO0": { "Relay1": 224 }, "GPIO3": { "Buzzer": 480 } },
       "sensors": { "Time": "2026-09-13T19:56:14" },
       "hardware": {
         "Hardware": "ESP8266EX",
         "Version": "15.6.0.1",
         "IPAddress": "192.168.1.151"
       }
     }
     ```

4. **Universal Control Action (Protected):**
   - `POST /api/devices/{device_id}/control`
   - Request Body:
     ```json
     {
       "target": "relay_1",
       "value": "TOGGLE"
     }
     ```
   - Response:
     ```json
     {
       "success": true,
       "device_id": "tasmota_0C3249",
       "target": "relay_1",
       "command": "POWER1",
       "value": "TOGGLE",
       "new_state": "ON",
       "response": { "POWER1": "ON" },
       "message": "Control applied successfully"
     }
     ```

5. **Device Status & Telemetry (Protected):**
   - `GET /api/devices/{device_id}/status?index=11`
   - Response: Live StatusSTS (WiFi RSSI, IP, Uptime, Heap).

---

## 3. Recommended Project Structure (Clean Architecture)

```text
lib/
├── core/
│   ├── api/
│   │   ├── api_client.dart       # Dio/Http client with interceptors for X-API-Key
│   │   └── api_endpoints.dart    # URL builder
│   ├── theme/
│   │   └── app_theme.dart        # Sleek dark/light theme, modern typography
│   └── storage/
│       └── preferences_service.dart # Saves apiUrl & apiKey
├── models/
│   ├── device_model.dart
│   ├── control_model.dart
│   └── module_info_model.dart
├── providers/ / controllers/     # Riverpod, Bloc, or Provider
│   ├── settings_controller.dart
│   ├── devices_controller.dart
│   └── device_detail_controller.dart
└── screens/
    ├── settings_screen.dart      # Server IP + Port + API Key setup
    ├── devices_screen.dart       # Screen 1: Discovered devices
    └── device_detail_screen.dart # Screen 2: Dynamic switches/buzzers/sliders
```

---

## 4. Technical Constraints & Design Principles
- **State Management:** Use `flutter_riverpod` or `provider`.
- **Networking:** Use `dio` or `http` with automated timeout handling (5 seconds) and graceful error alerts.
- **Local Storage:** Use `shared_preferences`.
- **Visual Design:**
  - Modern card-based dashboard with rounded corners (`16px`).
  - Distinct colors: Electric Cyan / Indigo accent, Emerald Green for `Online` / `ON`, Rose for `Offline` / `OFF`.
  - Haptic feedback (`HapticFeedback.lightImpact()`) when toggling relays or tapping buzzers.
  - Smooth loading spinners and pull-to-refresh on all screens.
```
