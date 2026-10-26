#!/usr/bin/env python3
"""
MQTT Subscriber for Tasmota Device (tasmota_0C3249)
Listens to topic pattern: +/tasmota_0C3249/#
"""

import argparse
import json
import sys
from datetime import datetime
import paho.mqtt.client as mqtt

DEFAULT_BROKER = "127.0.0.1"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "+/tasmota_0C3249/#"


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected successfully to MQTT broker!", flush=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribing to topic: {userdata['topic']}", flush=True)
        client.subscribe(userdata["topic"])
        print("-" * 65, flush=True)
        print(f"Listening for messages... (Press Ctrl+C to stop)", flush=True)
        print("-" * 65, flush=True)
    else:
        print(f"Failed to connect. Return code: {rc}", file=sys.stderr, flush=True)


def on_message(client, userdata, msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_payload = msg.payload.decode("utf-8", errors="replace")

    print(f"\n[{timestamp}] Topic: \033[1;36m{msg.topic}\033[0m (QoS: {msg.qos}, Retained: {msg.retain})", flush=True)

    # Try pretty-printing JSON if payload is valid JSON (e.g. tele/.../STATE or SENSOR)
    try:
        data = json.loads(raw_payload)
        formatted_json = json.dumps(data, indent=2)
        print(f"Payload (JSON):\n\033[32m{formatted_json}\033[0m", flush=True)
    except (json.JSONDecodeError, TypeError):
        # Plain text payload (e.g. stat/.../POWER -> ON/OFF)
        print(f"Payload: \033[33m{raw_payload}\033[0m", flush=True)


def on_disconnect(client, userdata, flags_or_rc, rc=None, properties=None):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Disconnected from broker.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Subscribe to Tasmota MQTT topics")
    parser.add_argument("--host", default=DEFAULT_BROKER, help=f"MQTT broker address (default: {DEFAULT_BROKER})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"MQTT broker port (default: {DEFAULT_PORT})")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help=f"Topic pattern to subscribe to (default: {DEFAULT_TOPIC})")
    parser.add_argument("--username", default=None, help="Optional username")
    parser.add_argument("--password", default=None, help="Optional password")
    args = parser.parse_args()

    # Support paho-mqtt v2 and v1
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={"topic": args.topic})
    except AttributeError:
        client = mqtt.Client(userdata={"topic": args.topic})

    if args.username and args.password:
        client.username_pw_set(args.username, args.password)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"Connecting to broker at {args.host}:{args.port}...", flush=True)
    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopping subscriber...", flush=True)
        client.disconnect()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
