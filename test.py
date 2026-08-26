import subprocess
import json
import re
import sys
import time
import threading
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"


def parse_line(line):
    line = line.rstrip()

    # NEW
    m = re.match(
        r"^\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )
    if m:
        return {
            "event": "NEW",
            "address": m.group(1),
            "data": m.group(2)
        }

    # CHG
    m = re.match(
        r"^\[CHG\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.+)$",
        line
    )
    if m:
        address = m.group(1)
        change = m.group(2)

        if ":" in change:
            key, value = change.split(":", 1)
            key = key.strip()
            value = value.strip()

            if key.upper() == "RSSI":
                try:
                    value = int(value)
                except ValueError:
                    pass

            data = {
                key: value
            }
        else:
            data = {
                "raw": change
            }

        return {
            "event": "CHG",
            "address": address,
            "data": data
        }

    # DEL
    m = re.match(
        r"^\[DEL\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )
    if m:
        return {
            "event": "DEL",
            "address": m.group(1),
            "data": m.group(2)
        }

    return None


def send_batch(batch):
    if not batch:
        return

    payload = {
        "ble": batch
    }

    try:
        response = requests.post(
            API_URL,
            headers={
                "token": TOKEN,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=5
        )

        print(
            f"[API] Sent {len(batch)} events | "
            f"HTTP {response.status_code}",
            flush=True
        )

    except requests.RequestException as e:
        print(f"[API ERROR] {e}", flush=True)


def main():

    print("Starting bluetoothctl...", flush=True)

    process = subprocess.Popen(
        [
            "stdbuf",
            "-oL",
            "-eL",
            "bluetoothctl"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    process.stdin.write("power on\n")
    process.stdin.flush()

    process.stdin.write("scan on\n")
    process.stdin.flush()

    print("Bluetooth scanning...", flush=True)

    # Events collected during the current 1-second window
    batch = []

    # Next API send time
    next_send = time.monotonic() + 1.0

    try:

        while True:

            # bluetoothctl readline() can block.
            # Use a short timeout by checking with select.
            import select

            ready, _, _ = select.select(
                [process.stdout],
                [],
                [],
                0.1
            )

            if ready:

                line = process.stdout.readline()

                if not line:
                    break

                # ALWAYS print original bluetoothctl output
                print(line.rstrip(), flush=True)

                parsed = parse_line(line)

                if parsed:

                    event = parsed["event"]

                    output = {
                        "ble": {
                            event: parsed
                        }
                    }

                    # Print individual JSON event
                    print(
                        json.dumps(
                            output,
                            separators=(",", ":")
                        ),
                        flush=True
                    )

                    # Add to 1-second batch
                    batch.append(parsed)

            # Send every 1 second
            now = time.monotonic()

            if now >= next_send:

                if batch:
                    send_batch(batch)
                    batch = []

                # Keep timing stable
                next_send += 1.0

                # Prevent accumulated delay
                if now >= next_send:
                    next_send = now + 1.0

    except KeyboardInterrupt:

        print("\nStopping...", flush=True)

    finally:

        # Send remaining events before shutting down
        if batch:
            send_batch(batch)

        try:
            process.stdin.write("scan off\n")
            process.stdin.flush()

            process.stdin.write("quit\n")
            process.stdin.flush()

        except Exception:
            pass

        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            process.kill()


if __name__ == "__main__":
    main()