#!/usr/bin/env python3
"""
Veloce Chrome/Firefox Native Messaging Host
Bridges browser extension commands directly to the local Veloce Engine via stdio.
"""

import sys
import json
import struct
import urllib.request

HOST_API = "http://127.0.0.1:9229/api"

def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    message_length = struct.unpack('@I', raw_length)[0]
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)

def send_message(message_content):
    encoded_content = json.dumps(message_content).encode('utf-8')
    encoded_length = struct.pack('@I', len(encoded_content))
    sys.stdout.buffer.write(encoded_length)
    sys.stdout.buffer.write(encoded_content)
    sys.stdout.buffer.flush()

def main():
    while True:
        try:
            msg = read_message()
            action = msg.get("action")

            if action == "PING":
                send_message({"status": "PONG", "message": "Veloce Native Host Active"})

            elif action == "DOWNLOAD":
                req = urllib.request.Request(
                    f"{HOST_API}/download",
                    data=json.dumps(msg.get("payload", {})).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        send_message({"success": True, "data": res})
                except Exception as e:
                    send_message({"success": False, "error": str(e)})

            else:
                send_message({"error": f"Unknown action: {action}"})

        except Exception as e:
            send_message({"error": str(e)})
            break

if __name__ == "__main__":
    main()
