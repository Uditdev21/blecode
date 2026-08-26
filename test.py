import subprocess
import json
import re
import time
import threading
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"


# Shared event buffer
batch = []
batch_lock = threading.Lock()

running = True


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


def send_batch():

    global batch

    while running:

        # Wait exactly 1 second
        time.sleep(1)

        # Take current batch
        with batch_lock:

            if not batch:
                continue

            current_batch = batch
            batch = []

        payload = {
            "ble": current_batch
        }

        print(
            f"[API] Sending {len(current_batch)} events...",
            flush=True
        )

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
                f"[API] HTTP {response.status_code}",
                flush=True
            )

            print(
                f"[API] Response: {response.text}",
                flush=True
            )

        except requests.RequestException as e:

            print(
                f"[API ERROR] {e}",
                flush=True
            )


def read_bluetooth(process):

    global running

    while running:

        line = process.stdout.readline()

        if not line:
            break

        # Print ORIGINAL bluetoothctl output
        print(
            line.rstrip(),
            flush=True
        )

        # Parse BLE event
        parsed = parse_line(line)

        if parsed:

            # Print parsed JSON
            output = {
                "ble": {
                    parsed["event"]: parsed
                }
            }

            print(
                json.dumps(
                    output,
                    separators=(",", ":")
                ),
                flush=True
            )

            # Add event to batch
            with batch_lock:
                batch.append(parsed)

    running = False


def main():

    global running

    print(
        "Starting bluetoothctl...",
        flush=True
    )

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

    # Power on
    process.stdin.write("power on\n")
    process.stdin.flush()

    time.sleep(1)

    # Start scanning
    process.stdin.write("scan on\n")
    process.stdin.flush()

    print(
        "Bluetooth scanning...",
        flush=True
    )

    # Bluetooth reader thread
    reader_thread = threading.Thread(
        target=read_bluetooth,
        args=(process,),
        daemon=True
    )

    reader_thread.start()

    # API sender thread
    api_thread = threading.Thread(
        target=send_batch,
        daemon=True
    )

    api_thread.start()

    try:

        while running:
            time.sleep(0.5)

    except KeyboardInterrupt:

        print(
            "\nStopping...",
            flush=True
        )

    finally:

        running = False

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

            try:
                process.kill()
            except Exception:
                pass

        # Send remaining events
        with batch_lock:
            remaining = batch.copy()
            batch.clear()

        if remaining:

            print(
                f"[API] Sending final {len(remaining)} events...",
                flush=True
            )

            try:

                response = requests.post(
                    API_URL,
                    headers={
                        "token": TOKEN,
                        "Content-Type": "application/json"
                    },
                    json={
                        "ble": remaining
                    },
                    timeout=5
                )

                print(
                    f"[API] Final HTTP {response.status_code}",
                    flush=True
                )

            except requests.RequestException as e:

                print(
                    f"[API ERROR] {e}",
                    flush=True
                )


if __name__ == "__main__":
    main()