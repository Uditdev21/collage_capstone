#!/usr/bin/env python3
"""
MQTT Publisher for Tasmota Device (tasmota_0C3249)
Sends commands to topic pattern: cmnd/tasmota_0C3249/<COMMAND>
"""

import argparse
import sys
from datetime import datetime
import paho.mqtt.client as mqtt

DEFAULT_BROKER = "127.0.0.1"
DEFAULT_PORT = 1883
DEVICE_TOPIC = "tasmota_0C3249"


def publish_message(client, topic: str, payload: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = client.publish(topic, payload, qos=1)
    status = result.rc
    if status == mqtt.MQTT_ERR_SUCCESS:
        print(f"[{timestamp}] \033[32mPublished successfully\033[0m -> Topic: \033[1;36m{topic}\033[0m | Payload: \033[33m{payload}\033[0m")
    else:
        print(f"[{timestamp}] \033[31mFailed to send message\033[0m. Error code: {status}", file=sys.stderr)


def interactive_menu(client, device: str):
    print("\n" + "=" * 50)
    print(f"  Interactive MQTT Controller for {device}")
    print("=" * 50)
    print("  1. Toggle Power       (cmnd/.../POWER TOGGLE)")
    print("  2. Turn Power ON      (cmnd/.../POWER ON)")
    print("  3. Turn Power OFF     (cmnd/.../POWER OFF)")
    print("  4. Request Status     (cmnd/.../STATUS 0)")
    print("  5. Custom Command")
    print("  6. Exit")
    print("=" * 50)

    while True:
        try:
            choice = input("\nEnter choice [1-6]: ").strip()
            if choice == "1":
                publish_message(client, f"cmnd/{device}/POWER", "TOGGLE")
            elif choice == "2":
                publish_message(client, f"cmnd/{device}/POWER", "ON")
            elif choice == "3":
                publish_message(client, f"cmnd/{device}/POWER", "OFF")
            elif choice == "4":
                publish_message(client, f"cmnd/{device}/STATUS", "0")
            elif choice == "5":
                cmd = input("Enter command (e.g. POWER, Dimmer, STATUS, LedPower): ").strip()
                payload = input("Enter payload: ").strip()
                if cmd:
                    publish_message(client, f"cmnd/{device}/{cmd}", payload)
            elif choice in ("6", "q", "exit"):
                print("Exiting interactive mode.")
                break
            else:
                print("Invalid choice. Please choose 1-6.")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive mode.")
            break


def main():
    parser = argparse.ArgumentParser(description="Publish MQTT commands to Tasmota")
    parser.add_argument("--host", default=DEFAULT_BROKER, help=f"MQTT broker address (default: {DEFAULT_BROKER})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"MQTT broker port (default: {DEFAULT_PORT})")
    parser.add_argument("--device", default=DEVICE_TOPIC, help=f"Tasmota device name (default: {DEVICE_TOPIC})")
    parser.add_argument("--cmd", default=None, help="Tasmota command (e.g. POWER, STATUS)")
    parser.add_argument("--payload", default="", help="Command payload (e.g. ON, OFF, TOGGLE, 0)")
    parser.add_argument("--topic", default=None, help="Full custom topic (overrides --cmd and --device)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive control menu")
    parser.add_argument("--username", default=None, help="Optional username")
    parser.add_argument("--password", default=None, help="Optional password")
    args = parser.parse_args()

    # Support paho-mqtt v2 and v1
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    if args.username and args.password:
        client.username_pw_set(args.username, args.password)

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"Failed to connect to broker {args.host}:{args.port}: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine execution mode
    if args.topic:
        publish_message(client, args.topic, args.payload)
    elif args.cmd:
        full_topic = f"cmnd/{args.device}/{args.cmd}"
        publish_message(client, full_topic, args.payload)
    else:
        # Default to interactive mode if no command was specified
        interactive_menu(client, args.device)

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
